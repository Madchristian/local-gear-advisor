from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

EQUIPMENT_SLOTS = frozenset(
    {
        "head",
        "neck",
        "shoulder",
        "back",
        "chest",
        "shirt",
        "tabard",
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
        "ammo",
    }
)
_ITEM_RE = re.compile(r"^(?P<slot>[a-z0-9_]+)=(?P<options>.*)$")
_ITEM_ID_RE = re.compile(r"(?:^|,)id=(?P<item_id>\d+)(?:,|$)")
_ITEM_LEVEL_RE = re.compile(r"\((\d+)\)\s*$")
MIN_VALID_ITEM_LEVEL = 1
MAX_VALID_ITEM_LEVEL = 999
_ACTOR_RE = re.compile(r'^([a-z][a-z0-9_]*)="([^"]+)"$')
_WOW_CLASSES = frozenset(
    {
        "deathknight",
        "demonhunter",
        "druid",
        "evoker",
        "hunter",
        "mage",
        "monk",
        "paladin",
        "priest",
        "rogue",
        "shaman",
        "warlock",
        "warrior",
    }
)
_SAFE_PROFILE_OPTIONS = frozenset(
    {
        "level",
        "race",
        "region",
        "server",
        "role",
        "position",
        "professions",
        "spec",
        "talents",
        "omnium_talents",
        "zandalari_loa",
        "source",
    }
)
_UNSAFE_PROFILE_VALUE_RE = re.compile(r'[";\\|<>\x00-\x1f]')
_TOKEN_RE = re.compile(r"^[a-z0-9_]+$")
_SERVER_RE = re.compile(r"^[\w\u0080-\uffff.+%-]+$")
_CHARACTER_NAME_RE = re.compile(r"^[\w\u0080-\uffff'+.-]+$")
_TALENT_RE = re.compile(r"^[A-Za-z0-9+./=_-]+$")
_TRAIT_RE = re.compile(r"^(?:\d+:\d+(?:/\d+:\d+)*)?$")
_VALID_REGIONS = frozenset({"us", "eu", "kr", "tw", "cn"})
_MAX_EXPORT_BYTES = 2 * 1024 * 1024
_MAX_EXPORT_LINES = 20_000


@dataclass(frozen=True)
class ItemSpec:
    slot: str
    options: str
    item_id: int
    name: str | None
    item_level: int | None
    fingerprint: str


@dataclass(frozen=True)
class ParseWarning:
    line_number: int
    message: str
    line: str


@dataclass(frozen=True)
class SimcExport:
    character_class: str
    character_name: str
    spec: str
    level: int
    race: str
    region: str
    server: str
    talents: str
    trait_systems: dict[str, str]
    base_profile: str
    equipped: dict[str, ItemSpec]
    candidates: tuple[ItemSpec, ...]
    warnings: tuple[ParseWarning, ...]


def _parse_item(line: str, name: str | None) -> ItemSpec | None:
    match = _ITEM_RE.match(line)
    if not match or match.group("slot") not in EQUIPMENT_SLOTS:
        return None
    options = match.group("options")
    item_match = _ITEM_ID_RE.search(options)
    if not item_match:
        return None
    item_level = None
    if name is not None:
        level_match = _ITEM_LEVEL_RE.search(name)
        if level_match:
            item_level = int(level_match.group(1))
    return ItemSpec(
        slot=match.group("slot"),
        options=options,
        item_id=int(item_match.group("item_id")),
        name=name,
        item_level=item_level,
        fingerprint=hashlib.sha256(options.encode("utf-8")).hexdigest(),
    )


def parse_simc_export(text: str) -> SimcExport:
    """Parse the official addon's active profile and commented bag candidates."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(normalized.encode("utf-8")) > _MAX_EXPORT_BYTES:
        raise ValueError("SimC export exceeds the 2 MiB safety limit")
    lines = normalized.splitlines()
    if len(lines) > _MAX_EXPORT_LINES:
        raise ValueError("SimC export exceeds the 20,000-line safety limit")
    bag_marker = next((i for i, line in enumerate(lines) if line == "### Gear from Bags"), None)
    raw_base_lines = lines if bag_marker is None else lines[:bag_marker]
    base_lines: list[str] = []
    seen_directives: set[str] = set()
    actor = None
    for index, raw in enumerate(raw_base_lines, 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        actor_match = _ACTOR_RE.fullmatch(stripped)
        if actor_match and actor_match.group(1) in _WOW_CLASSES:
            if actor is not None:
                raise ValueError("SimC export contains more than one character actor")
            if not _CHARACTER_NAME_RE.fullmatch(actor_match.group(2)):
                raise ValueError("SimC export contains an invalid character name")
            actor = actor_match
            base_lines.append(stripped)
            continue
        if "=" not in stripped:
            raise ValueError(f"unsafe or unsupported SimC directive on line {index}: {stripped}")
        key, _, value = stripped.partition("=")
        if key in seen_directives:
            raise ValueError(f"duplicate SimC directive on line {index}: {key}")
        seen_directives.add(key)
        if (not value and key != "omnium_talents") or _UNSAFE_PROFILE_VALUE_RE.search(value):
            raise ValueError(f"unsafe or invalid SimC value on line {index}: {key}")
        if key in EQUIPMENT_SLOTS:
            if _parse_item(stripped, None) is None:
                raise ValueError(f"equipped item line {index} has no valid item id")
            base_lines.append(stripped)
            continue
        if key not in _SAFE_PROFILE_OPTIONS:
            raise ValueError(f"unsafe or unsupported SimC directive on line {index}: {key}")
        if key == "source" and value != "default":
            raise ValueError("only source=default is accepted; external imports are blocked")
        base_lines.append(stripped)
    base_profile = "\n".join(base_lines).rstrip() + "\n"

    if actor is None:
        raise ValueError("SimC export does not contain a character actor line")
    spec = next(
        (line.partition("=")[2].strip() for line in base_lines if line.strip().startswith("spec=")),
        "",
    )
    if not spec:
        raise ValueError("SimC export does not contain spec=")

    def base_option(name: str) -> str:
        prefix = name + "="
        return next(
            (line.partition("=")[2].strip() for line in base_lines if line.startswith(prefix)),
            "",
        )

    region = base_option("region")
    server = base_option("server")
    race = base_option("race")
    level_text = base_option("level")
    if region not in _VALID_REGIONS or not _SERVER_RE.fullmatch(server):
        raise ValueError("SimC export does not contain valid region= and server=")
    if not _TOKEN_RE.fullmatch(race) or not level_text.isdigit() or not 1 <= int(level_text) <= 90:
        raise ValueError("SimC export does not contain valid race= and level=")
    level = int(level_text)
    talents = base_option("talents")
    if not talents or not _TALENT_RE.fullmatch(talents):
        raise ValueError("SimC export does not contain valid active talents=")
    trait_systems: dict[str, str] = {}
    for line in base_lines:
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key != "talents" and key.endswith("_talents"):
            value = value.strip()
            if not _TRAIT_RE.fullmatch(value):
                raise ValueError(f"SimC export contains invalid {key}=")
            trait_systems[key] = value
    trait_systems.setdefault("omnium_talents", "")

    equipped: dict[str, ItemSpec] = {}
    pending_name: str | None = None
    for line in base_lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            pending_name = stripped[2:]
            continue
        item = _parse_item(stripped, pending_name)
        if item is not None:
            equipped[item.slot] = item
        if stripped and not stripped.startswith("#"):
            pending_name = None

    candidates: list[ItemSpec] = []
    warnings: list[ParseWarning] = []
    if bag_marker is not None:
        pending_name = None
        for index in range(bag_marker + 1, len(lines)):
            raw = lines[index]
            if raw.startswith("###"):
                if pending_name is not None:
                    warnings.append(
                        ParseWarning(index + 1, "Candidate description has no item line", raw)
                    )
                    pending_name = None
                break
            if raw == "#":
                if pending_name is not None:
                    warnings.append(
                        ParseWarning(index + 1, "Candidate description has no item line", raw)
                    )
                pending_name = None
                continue
            if not raw.startswith("# "):
                continue
            content = raw[2:].strip()
            possible = _ITEM_RE.match(content)
            if possible and possible.group("slot") in EQUIPMENT_SLOTS:
                item = _parse_item(content, pending_name)
                if item is None:
                    warnings.append(ParseWarning(index + 1, "Candidate has no valid item id", raw))
                else:
                    candidates.append(item)
                pending_name = None
            elif possible and possible.group("slot") != "upgrade_levels":
                warnings.append(
                    ParseWarning(index + 1, "Candidate uses an unsupported equipment slot", raw)
                )
                pending_name = None
            elif pending_name is None:
                pending_name = content
        if pending_name is not None:
            warnings.append(
                ParseWarning(len(lines), "Candidate description has no item line", pending_name)
            )

    return SimcExport(
        character_class=actor.group(1),
        character_name=actor.group(2),
        spec=spec,
        level=level,
        race=race,
        region=region,
        server=server,
        talents=talents,
        trait_systems=trait_systems,
        base_profile=base_profile,
        equipped=equipped,
        candidates=tuple(candidates),
        warnings=tuple(warnings),
    )
