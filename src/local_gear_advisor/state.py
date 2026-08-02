from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import re
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_SCHEMA_VERSION = 2
_ALLOWED_REGIONS = frozenset({"us", "eu", "kr", "tw", "cn"})
_BASELINE_SLOTS = (
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
    "wrist",
    "hands",
    "waist",
    "legs",
    "feet",
    "finger1",
    "finger2",
    "trinket1",
    "trinket2",
    "main_hand",
    "off_hand",
)
_ALLOWED_TOP_KEYS = frozenset({"schemaVersion", "profiles"})
_ALLOWED_IDENTITY_KEYS = frozenset({"region", "realm", "name", "specId"})
_ALLOWED_PROFILE_KEYS = frozenset(
    {
        "identity",
        "class",
        "spec",
        "level",
        "race",
        "talents",
        "traitSystems",
        "baselineGear",
        "fightStyle",
        "baselineDps",
        "simcVersion",
        "simcRevision",
        "gameVersion",
        "dbcSource",
        "profileHash",
        "generatedAt",
        "items",
    }
)
_ALLOWED_ITEM_KEYS = frozenset(
    {
        "options",
        "itemId",
        "itemName",
        "fingerprint",
        "bestSlot",
        "candidateDps",
        "deltaPercent",
        "iterations",
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ITEM_OPTIONS_RE = re.compile(r"^,id=([1-9][0-9]*)(?:,[a-z_]+=[^,\r\n]+)*$")
_SIMC_REVISION_RE = re.compile(r"^[0-9a-f]{7,40}$")
_MAX_CHARACTER_LEVEL = 90
_MAX_SPEC_ID = 10_000
_MAX_ITEM_ID = 10_000_000
_MIN_ITERATIONS = 100
_MAX_ITERATIONS = 1_000_000
_MAX_EXACT_LUA_INTEGER = 9_007_199_254_740_991
_MAX_DPS = 1_000_000_000_000.0
_MAX_ABS_DELTA_PERCENT = 1_000_000.0
_MAX_STATE_BYTES = 32 * 1024 * 1024
_MAX_RESULTS_BYTES = 64 * 1024 * 1024
_MAX_JOURNAL_BYTES = 136 * 1024 * 1024
# Anything not alnum/%/+/./_/high-byte is stripped; must stay bit-for-bit
# identical to the addon's Lua Tokenize() (see Core.lua) so a realm computed
# here always matches what the addon computes at runtime from GetRealmName().
_TOKENIZE_STRIP_RE = re.compile(rb"[^a-z0-9%+._\x80-\xff]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


class StateError(RuntimeError):
    """Fail-closed: aggregate profile state is missing, malformed, or tampered."""


def _ascii_lower(value: str) -> str:
    """Lowercase only ASCII A-Z bytes, matching Lua's byte-wise (C-locale)
    string.lower() rather than Python's Unicode-aware str.lower()/casefold(),
    so identity comparisons agree with the addon's runtime Tokenize()/
    string.lower() byte for byte, including for accented characters."""
    data = value.encode("utf-8")
    lowered = bytes(b + 32 if 65 <= b <= 90 else b for b in data)
    return lowered.decode("utf-8")


def _wow_tokenize(value: str) -> str:
    """Python port of Core.lua's Tokenize(): ASCII-lowercase, spaces become
    underscores, everything except alnum/%/+/./_/high-bytes is stripped, then
    trailing underscores are stripped."""
    data = _ascii_lower(value).encode("utf-8")
    data = data.replace(b" ", b"_")
    data = _TOKENIZE_STRIP_RE.sub(b"", data)
    data = data.rstrip(b"_")
    return data.decode("utf-8")


@dataclass(frozen=True)
class ProfileIdentity:
    region: str
    realm: str
    name: str
    spec_id: int

    def sort_key(self) -> tuple[str, str, str, int]:
        return (self.region, self.realm, _ascii_lower(self.name), self.spec_id)


@dataclass(frozen=True)
class ProfileItem:
    options: str
    item_id: int
    item_name: str | None
    fingerprint: str
    best_slot: str
    candidate_dps: float
    delta_percent: float
    iterations: int


@dataclass(frozen=True)
class ProfileRecord:
    identity: ProfileIdentity
    character_class: str
    spec: str
    level: int
    race: str
    talents: str
    trait_systems: Mapping[str, str]
    baseline_gear: Mapping[str, str | None]
    fight_style: str
    baseline_dps: float
    simc_version: str
    simc_revision: str
    game_version: str
    dbc_source: str
    profile_hash: str
    generated_at: int
    items: tuple[ProfileItem, ...]


@dataclass(frozen=True)
class AggregateState:
    profiles: tuple[ProfileRecord, ...]


def normalize_identity(*, region: str, realm: str, name: str, spec_id: int) -> ProfileIdentity:
    if not region.strip() or not realm.strip() or not name.strip():
        raise StateError("profile identity requires non-empty region, realm, and name")
    if (
        not isinstance(spec_id, int)
        or isinstance(spec_id, bool)
        or spec_id <= 0
        or spec_id > _MAX_SPEC_ID
    ):
        raise StateError(f"profile identity requires a positive numeric specID: {spec_id!r}")
    for value, label in ((region, "region"), (realm, "realm"), (name, "name")):
        if _CONTROL_CHAR_RE.search(value):
            raise StateError(f"profile identity {label} contains a control character")
    normalized_region = _ascii_lower(region.strip())
    normalized_realm = _wow_tokenize(realm.strip())
    if normalized_region not in _ALLOWED_REGIONS:
        raise StateError(f"profile identity has an unsupported region: {region!r}")
    if not normalized_realm:
        raise StateError("profile identity realm is empty after WoW tokenization")
    return ProfileIdentity(
        region=normalized_region,
        realm=normalized_realm,
        name=name.strip(),
        spec_id=spec_id,
    )


def empty_state() -> AggregateState:
    return AggregateState(profiles=())


def merge_profile(state: AggregateState, record: ProfileRecord) -> AggregateState:
    by_key: dict[tuple[str, str, str, int], ProfileRecord] = {
        existing.identity.sort_key(): existing for existing in state.profiles
    }
    by_key[record.identity.sort_key()] = record
    ordered = tuple(sorted(by_key.values(), key=lambda r: r.identity.sort_key()))
    return AggregateState(profiles=ordered)


def _lua_string(value: str) -> str:
    escaped: list[str] = []
    for character in value:
        codepoint = ord(character)
        if character == "\\":
            escaped.append("\\\\")
        elif character == '"':
            escaped.append('\\"')
        elif codepoint < 32 or 127 <= codepoint <= 159:
            escaped.append(f"\\{codepoint:03d}")
        else:
            escaped.append(character)
    return '"' + "".join(escaped) + '"'


def _number(value: float) -> str:
    return format(value, ".12g")


def render_aggregate_lua(state: AggregateState) -> str:
    state = validate_state(state)
    lines = [
        "-- Generated by Local Gear Advisor. Do not edit while WoW is running.",
        "LocalGearAdvisorResults = {",
        f"  schemaVersion = {_SCHEMA_VERSION},",
        "  profiles = {",
    ]
    for record in state.profiles:
        lines.extend(
            [
                "    {",
                f"      region = {_lua_string(record.identity.region)},",
                f"      server = {_lua_string(record.identity.realm)},",
                f"      characterName = {_lua_string(record.identity.name)},",
                f"      specID = {record.identity.spec_id},",
                f"      class = {_lua_string(record.character_class)},",
                f"      spec = {_lua_string(record.spec)},",
                f"      level = {record.level},",
                f"      race = {_lua_string(record.race)},",
                f"      talents = {_lua_string(record.talents)},",
                f"      generatedAt = {record.generated_at},",
                f"      profileHash = {_lua_string(record.profile_hash)},",
                f"      simcVersion = {_lua_string(record.simc_version)},",
                f"      simcRevision = {_lua_string(record.simc_revision)},",
                f"      gameVersion = {_lua_string(record.game_version)},",
                f"      dbcSource = {_lua_string(record.dbc_source)},",
                f"      fightStyle = {_lua_string(record.fight_style)},",
                f"      baselineDps = {_number(record.baseline_dps)},",
                "      traitSystems = {",
            ]
        )
        for key, value in sorted(record.trait_systems.items()):
            lines.append(f"        {key} = {_lua_string(value)},")
        lines.extend(["      },", "      baselineGear = {"])
        for slot in _BASELINE_SLOTS:
            gear_value = record.baseline_gear.get(slot)
            rendered = _lua_string(gear_value) if gear_value is not None else "false"
            lines.append(f"        {slot} = {rendered},")
        lines.extend(["      },", "      items = {"])
        for item in sorted(record.items, key=lambda value: value.options):
            rendered_name = _lua_string(item.item_name) if item.item_name is not None else "false"
            lines.extend(
                [
                    f"        [{_lua_string(item.options)}] = {{",
                    f"          itemID = {item.item_id},",
                    f"          name = {rendered_name},",
                    f"          fingerprint = {_lua_string(item.fingerprint)},",
                    f"          bestSlot = {_lua_string(item.best_slot)},",
                    f"          candidateDps = {_number(item.candidate_dps)},",
                    f"          deltaPercent = {_number(item.delta_percent)},",
                    f"          iterations = {item.iterations},",
                    '          status = "simulated",',
                    "        },",
                ]
            )
        lines.extend(["      },", "    },"])
    lines.extend(["  },", "}", ""])
    return "\n".join(lines)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StateError(f"aggregate state has duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _require_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateError(f"aggregate state field {label!r} must be a non-empty string")
    if _CONTROL_CHAR_RE.search(value):
        raise StateError(f"aggregate state field {label!r} contains a control character")
    return value


def _require_finite(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise StateError(f"aggregate state field {label!r} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise StateError(f"aggregate state field {label!r} must be finite")
    return number


def _require_int(value: Any, label: str, *, positive: bool = False) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise StateError(f"aggregate state field {label!r} must be an integer")
    if positive and value <= 0:
        raise StateError(f"aggregate state field {label!r} must be positive")
    return value


def _parse_identity(raw: Any) -> ProfileIdentity:
    if not isinstance(raw, dict) or set(raw.keys()) != _ALLOWED_IDENTITY_KEYS:
        raise StateError(f"aggregate state has a malformed identity: {raw!r}")
    region = _require_str(raw.get("region"), "identity.region")
    realm = _require_str(raw.get("realm"), "identity.realm")
    name = _require_str(raw.get("name"), "identity.name")
    spec_id = _require_int(raw.get("specId"), "identity.specId", positive=True)
    identity = normalize_identity(region=region, realm=realm, name=name, spec_id=spec_id)
    if identity.region != region or identity.realm != realm or identity.name != name:
        raise StateError("aggregate state identity is not canonically normalized")
    return identity


def _parse_item(raw: Any) -> ProfileItem:
    if not isinstance(raw, dict) or set(raw.keys()) != _ALLOWED_ITEM_KEYS:
        raise StateError(f"aggregate state has a malformed item entry: {raw!r}")
    item_name = raw.get("itemName")
    if item_name is not None and (not isinstance(item_name, str) or not item_name.strip()):
        raise StateError("aggregate state item.itemName must be a string or null")
    if item_name is not None and _CONTROL_CHAR_RE.search(item_name):
        raise StateError("aggregate state item.itemName contains a control character")
    item_id = _require_int(raw.get("itemId"), "item.itemId", positive=True)
    fingerprint = _require_str(raw.get("fingerprint"), "item.fingerprint")
    iterations = _require_int(raw.get("iterations"), "item.iterations", positive=True)
    if item_id > _MAX_ITEM_ID:
        raise StateError("aggregate state item.itemId is out of range")
    if not _SHA256_RE.fullmatch(fingerprint):
        raise StateError("aggregate state item.fingerprint must be lowercase SHA-256")
    if not (_MIN_ITERATIONS <= iterations <= _MAX_ITERATIONS):
        raise StateError("aggregate state item.iterations is out of range")
    options = _require_str(raw.get("options"), "item.options")
    best_slot = _require_str(raw.get("bestSlot"), "item.bestSlot")
    candidate_dps = _require_finite(raw.get("candidateDps"), "item.candidateDps")
    delta_percent = _require_finite(raw.get("deltaPercent"), "item.deltaPercent")
    options_match = _ITEM_OPTIONS_RE.fullmatch(options)
    if not options_match:
        raise StateError("aggregate state item.options has an invalid canonical form")
    if int(options_match.group(1)) != item_id:
        raise StateError("aggregate state item.options item ID does not match item.itemId")
    option_keys = [segment.split("=", 1)[0] for segment in options[1:].split(",")]
    if len(option_keys) != len(set(option_keys)):
        raise StateError("aggregate state item.options contains duplicate option keys")
    if best_slot not in _BASELINE_SLOTS:
        raise StateError("aggregate state item.bestSlot is unsupported")
    if not (0 <= candidate_dps <= _MAX_DPS):
        raise StateError("aggregate state item.candidateDps is out of range")
    if abs(delta_percent) > _MAX_ABS_DELTA_PERCENT:
        raise StateError("aggregate state item.deltaPercent is out of range")
    return ProfileItem(
        options=options,
        item_id=item_id,
        item_name=item_name,
        fingerprint=fingerprint,
        best_slot=best_slot,
        candidate_dps=candidate_dps,
        delta_percent=delta_percent,
        iterations=iterations,
    )


def _parse_baseline_gear(raw: Any) -> dict[str, str | None]:
    if not isinstance(raw, dict) or set(raw.keys()) != set(_BASELINE_SLOTS):
        raise StateError(f"aggregate state has malformed baselineGear: {raw!r}")
    gear: dict[str, str | None] = {}
    for slot in _BASELINE_SLOTS:
        value = raw[slot]
        if value is not None and (not isinstance(value, str) or not value):
            raise StateError(f"aggregate state baselineGear.{slot} must be a string or null")
        if value is not None and _CONTROL_CHAR_RE.search(value):
            raise StateError(f"aggregate state baselineGear.{slot} contains a control character")
        gear[slot] = value
    return gear


def _parse_trait_systems(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict) or set(raw) != {"omnium_talents"}:
        raise StateError("aggregate state traitSystems must contain exactly omnium_talents")
    result: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise StateError("aggregate state traitSystems keys/values must be strings")
        if _CONTROL_CHAR_RE.search(key) or _CONTROL_CHAR_RE.search(value):
            raise StateError("aggregate state traitSystems contains a control character")
        result[key] = value
    return result


def _parse_profile(raw: Any) -> ProfileRecord:
    if not isinstance(raw, dict) or set(raw.keys()) != _ALLOWED_PROFILE_KEYS:
        raise StateError(f"aggregate state has a malformed profile: {raw!r}")
    items_raw = raw.get("items")
    if not isinstance(items_raw, list):
        raise StateError("aggregate state profile.items must be a list")
    if len(items_raw) > 100_000:
        raise StateError("aggregate state profile.items is too large")
    items = tuple(_parse_item(entry) for entry in items_raw)
    seen_options: set[str] = set()
    seen_fingerprints: set[str] = set()
    for item in items:
        if item.options in seen_options:
            raise StateError(f"aggregate state has a duplicate item option key: {item.options!r}")
        seen_options.add(item.options)
        if item.fingerprint in seen_fingerprints:
            raise StateError(
                f"aggregate state has a duplicate item fingerprint: {item.fingerprint!r}"
            )
        seen_fingerprints.add(item.fingerprint)
    profile_hash = _require_str(raw.get("profileHash"), "profile.profileHash")
    if not _SHA256_RE.fullmatch(profile_hash):
        raise StateError("aggregate state profile.profileHash must be lowercase SHA-256")
    level = _require_int(raw.get("level"), "profile.level", positive=True)
    if level > _MAX_CHARACTER_LEVEL:
        raise StateError("aggregate state profile.level is out of range")
    character_class = _require_str(raw.get("class"), "profile.class")
    spec = _require_str(raw.get("spec"), "profile.spec")
    race = _require_str(raw.get("race"), "profile.race")
    baseline_dps = _require_finite(raw.get("baselineDps"), "profile.baselineDps")
    simc_revision = _require_str(raw.get("simcRevision"), "profile.simcRevision")
    dbc_source = _require_str(raw.get("dbcSource"), "profile.dbcSource")
    if any(value != _ascii_lower(value) for value in (character_class, spec, race)):
        raise StateError("aggregate state class/spec/race tokens must be lowercase")
    if not (0 <= baseline_dps <= _MAX_DPS):
        raise StateError("aggregate state profile.baselineDps is out of range")
    if not _SIMC_REVISION_RE.fullmatch(simc_revision):
        raise StateError("aggregate state profile.simcRevision is malformed")
    if dbc_source != "Live":
        raise StateError("aggregate state profile.dbcSource must be Live")
    generated_at = _require_int(raw.get("generatedAt"), "profile.generatedAt", positive=True)
    if generated_at > _MAX_EXACT_LUA_INTEGER:
        raise StateError("aggregate state profile.generatedAt is out of range")
    return ProfileRecord(
        identity=_parse_identity(raw.get("identity")),
        character_class=character_class,
        spec=spec,
        level=level,
        race=race,
        talents=_require_str(raw.get("talents"), "profile.talents"),
        trait_systems=_parse_trait_systems(raw.get("traitSystems")),
        baseline_gear=_parse_baseline_gear(raw.get("baselineGear")),
        fight_style=_require_str(raw.get("fightStyle"), "profile.fightStyle"),
        baseline_dps=baseline_dps,
        simc_version=_require_str(raw.get("simcVersion"), "profile.simcVersion"),
        simc_revision=simc_revision,
        game_version=_require_str(raw.get("gameVersion"), "profile.gameVersion"),
        dbc_source=dbc_source,
        profile_hash=profile_hash,
        generated_at=generated_at,
        items=items,
    )


def _parse_state(raw: bytes) -> AggregateState:
    try:
        payload: Any = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                StateError(f"aggregate state contains non-finite JSON constant: {value}")
            ),
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateError(f"aggregate state is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict) or set(payload.keys()) != _ALLOWED_TOP_KEYS:
        raise StateError("aggregate state root has unexpected keys")
    if payload.get("schemaVersion") != _SCHEMA_VERSION:
        found = payload.get("schemaVersion")
        raise StateError(f"aggregate state schemaVersion must be {_SCHEMA_VERSION}: {found!r}")
    profiles_raw = payload.get("profiles")
    if not isinstance(profiles_raw, list):
        raise StateError("aggregate state profiles must be a list")
    if len(profiles_raw) > 10_000:
        raise StateError("aggregate state profiles is too large")
    profiles = tuple(_parse_profile(entry) for entry in profiles_raw)
    seen_keys: set[tuple[str, str, str, int]] = set()
    for record in profiles:
        key = record.identity.sort_key()
        if key in seen_keys:
            raise StateError(f"aggregate state has a duplicate profile identity: {key!r}")
        seen_keys.add(key)
    return AggregateState(profiles=tuple(sorted(profiles, key=lambda r: r.identity.sort_key())))


def load_state(path: Path) -> AggregateState:
    try:
        if path.stat().st_size > _MAX_STATE_BYTES:
            raise StateError("aggregate state exceeds the maximum size")
        raw = path.read_bytes()
    except FileNotFoundError:
        return empty_state()
    if len(raw) > _MAX_STATE_BYTES:
        raise StateError("aggregate state exceeds the maximum size")
    return _parse_state(raw)


def _dump_state_json(state: AggregateState) -> str:
    payload = {
        "schemaVersion": _SCHEMA_VERSION,
        "profiles": [
            {
                "identity": {
                    "region": record.identity.region,
                    "realm": record.identity.realm,
                    "name": record.identity.name,
                    "specId": record.identity.spec_id,
                },
                "class": record.character_class,
                "spec": record.spec,
                "level": record.level,
                "race": record.race,
                "talents": record.talents,
                "traitSystems": dict(sorted(record.trait_systems.items())),
                "baselineGear": {slot: record.baseline_gear.get(slot) for slot in _BASELINE_SLOTS},
                "fightStyle": record.fight_style,
                "baselineDps": record.baseline_dps,
                "simcVersion": record.simc_version,
                "simcRevision": record.simc_revision,
                "gameVersion": record.game_version,
                "dbcSource": record.dbc_source,
                "profileHash": record.profile_hash,
                "generatedAt": record.generated_at,
                "items": [
                    {
                        "options": item.options,
                        "itemId": item.item_id,
                        "itemName": item.item_name,
                        "fingerprint": item.fingerprint,
                        "bestSlot": item.best_slot,
                        "candidateDps": item.candidate_dps,
                        "deltaPercent": item.delta_percent,
                        "iterations": item.iterations,
                    }
                    for item in sorted(record.items, key=lambda value: value.options)
                ],
            }
            for record in sorted(state.profiles, key=lambda r: r.identity.sort_key())
        ],
    }
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if temporary.read_bytes() != data:
            raise StateError(f"temporary file verification failed: {path}")
        os.replace(temporary, path)
        if path.read_bytes() != data:
            raise StateError(f"atomic file readback verification failed: {path}")
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_text_writer(path: Path, content: str) -> None:
    _atomic_bytes(path, content.encode("utf-8"))


def save_state(path: Path, state: AggregateState) -> None:
    validated = validate_state(state)
    _atomic_text_writer(path, _dump_state_json(validated))


def validate_state(state: AggregateState) -> AggregateState:
    return _parse_state(_dump_state_json(state).encode("utf-8"))


def _restore_or_remove(path: Path, old_bytes: bytes | None) -> None:
    if old_bytes is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    _atomic_bytes(path, old_bytes)


def _matches_snapshot(path: Path, old_bytes: bytes | None) -> bool:
    if old_bytes is None:
        return not path.exists()
    return path.is_file() and path.read_bytes() == old_bytes


@contextmanager
def _exclusive_state_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    locked = False
    try:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise StateError(f"aggregate publication is already in progress: {path}") from exc
        locked = True
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _snapshot_payload(value: bytes | None) -> str | None:
    return None if value is None else base64.b64encode(value).decode("ascii")


def _decode_snapshot(value: object, label: str) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise StateError(f"aggregate publication journal {label} is malformed")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise StateError(f"aggregate publication journal {label} is malformed") from exc
    limit = _MAX_RESULTS_BYTES if label == "oldResults" else _MAX_STATE_BYTES
    if len(decoded) > limit:
        raise StateError(f"aggregate publication journal {label} is too large")
    return decoded


def _read_optional_bounded(path: Path, *, limit: int, label: str) -> bytes | None:
    try:
        if path.stat().st_size > limit:
            raise StateError(f"{label} exceeds the maximum size")
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    if len(data) > limit:
        raise StateError(f"{label} exceeds the maximum size")
    return data


def _write_journal(
    journal: Path,
    *,
    state_path: Path,
    results_path: Path,
    old_state: bytes | None,
    old_results: bytes | None,
    new_state: bytes,
    new_results: bytes,
) -> None:
    payload = {
        "version": 2,
        "statePath": str(state_path),
        "resultsPath": str(results_path),
        "oldState": _snapshot_payload(old_state),
        "oldResults": _snapshot_payload(old_results),
        "newStateSha256": hashlib.sha256(new_state).hexdigest(),
        "newResultsSha256": hashlib.sha256(new_results).hexdigest(),
    }
    data = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    if len(data) > _MAX_JOURNAL_BYTES:
        raise StateError("aggregate publication journal exceeds the maximum size")
    _atomic_bytes(journal, data)


def _recover_pending_publication(*, journal: Path, state_path: Path, results_path: Path) -> None:
    try:
        if journal.stat().st_size > _MAX_JOURNAL_BYTES:
            raise StateError("aggregate publication journal exceeds the maximum size")
        raw = journal.read_bytes()
    except FileNotFoundError:
        return
    if len(raw) > _MAX_JOURNAL_BYTES:
        raise StateError("aggregate publication journal exceeds the maximum size")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateError(f"aggregate publication journal is malformed: {exc}") from exc
    keys = {
        "version",
        "statePath",
        "resultsPath",
        "oldState",
        "oldResults",
        "newStateSha256",
        "newResultsSha256",
    }
    if not isinstance(payload, dict) or set(payload) != keys or payload["version"] != 2:
        raise StateError("aggregate publication journal has an invalid structure")
    if payload["statePath"] != str(state_path) or payload["resultsPath"] != str(results_path):
        raise StateError("aggregate publication journal path binding does not match")
    old_state = _decode_snapshot(payload["oldState"], "oldState")
    old_results = _decode_snapshot(payload["oldResults"], "oldResults")
    pairs = (
        (results_path, old_results, payload["newResultsSha256"]),
        (state_path, old_state, payload["newStateSha256"]),
    )
    for path, snapshot, new_hash in pairs:
        if not isinstance(new_hash, str) or not _SHA256_RE.fullmatch(new_hash):
            raise StateError("aggregate publication journal has an invalid generation hash")
        current = _read_optional_bounded(
            path,
            limit=_MAX_RESULTS_BYTES if path == results_path else _MAX_STATE_BYTES,
            label="Results.lua" if path == results_path else "aggregate state",
        )
        old_matches = current == snapshot
        new_matches = current is not None and hashlib.sha256(current).hexdigest() == new_hash
        if not (old_matches or new_matches):
            raise StateError(f"aggregate publication recovery refused a foreign generation: {path}")
    for path, snapshot, _ in pairs:
        _restore_or_remove(path, snapshot)
        if not _matches_snapshot(path, snapshot):
            raise StateError(f"aggregate publication recovery verification failed: {path}")
    journal.unlink()
    if journal.exists():
        raise StateError("aggregate publication journal cleanup failed")


def publish_profile_update(
    *,
    state_path: Path,
    results_path: Path,
    record: ProfileRecord,
    lua_writer: Callable[[Path, str], None] = _atomic_text_writer,
    state_writer: Callable[[Path, str], None] = _atomic_text_writer,
) -> AggregateState:
    """Publish JSON and Lua with one OS lock and a crash-recovery journal."""
    state_path = state_path.absolute()
    results_path = results_path.absolute()
    if state_path == results_path:
        raise StateError("canonical state and Results.lua must use different paths")
    state_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = state_path.with_name(state_path.name + ".publish.lock")
    journal = state_path.with_name(state_path.name + ".publish.pending.json")
    with _exclusive_state_lock(lock_path):
        _recover_pending_publication(
            journal=journal, state_path=state_path, results_path=results_path
        )
        old_state = _read_optional_bounded(
            state_path, limit=_MAX_STATE_BYTES, label="aggregate state"
        )
        old_results = _read_optional_bounded(
            results_path, limit=_MAX_RESULTS_BYTES, label="Results.lua"
        )
        new_state = validate_state(merge_profile(load_state(state_path), record))
        state_text = _dump_state_json(new_state)
        lua_text = render_aggregate_lua(new_state)
        if len(state_text.encode("utf-8")) > _MAX_STATE_BYTES:
            raise StateError("aggregate state exceeds the maximum size")
        if len(lua_text.encode("utf-8")) > _MAX_RESULTS_BYTES:
            raise StateError("Results.lua exceeds the maximum size")
        _write_journal(
            journal,
            state_path=state_path,
            results_path=results_path,
            old_state=old_state,
            old_results=old_results,
            new_state=state_text.encode("utf-8"),
            new_results=lua_text.encode("utf-8"),
        )
        try:
            state_writer(state_path, state_text)
            if state_path.read_bytes() != state_text.encode("utf-8"):
                raise StateError("canonical state readback verification failed")
            lua_writer(results_path, lua_text)
            if results_path.read_bytes() != lua_text.encode("utf-8"):
                raise StateError("Results.lua readback verification failed")
        except Exception as publication_error:
            try:
                _recover_pending_publication(
                    journal=journal,
                    state_path=state_path,
                    results_path=results_path,
                )
            except Exception as recovery_error:
                raise StateError(
                    "aggregate publication failed and journal recovery "
                    f"could not be verified: {recovery_error}"
                ) from publication_error
            raise
        journal.unlink()
        if journal.exists():
            raise StateError("aggregate publication journal cleanup failed")
        return new_state
