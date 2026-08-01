"""Deterministic generator for the packaged SimC specialization registry.

Parses the ``specialization_e`` enum from a pinned SimulationCraft revision
(fetched over HTTPS from raw.githubusercontent.com, or read from a local
``.inc`` fixture for offline/tests) and emits canonical JSON consumed at
runtime by ``local_gear_advisor.spec_registry``. Pure deterministic parsing:
no AI/runtime inference.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

_SCHEMA_VERSION = 1
_ALLOWED_HOST = "raw.githubusercontent.com"
_SOURCE_PATH_TEMPLATE = (
    "/simulationcraft/simc/{revision}/engine/dbc/generated/sc_specialization_data.inc"
)
_REVISION_RE = re.compile(r"^[0-9a-f]{7,40}$")
_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ENUM_LINE_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*(\d+)\s*,?$")
_MIN_EXPECTED_ENTRIES = 30
_MAX_EXPECTED_ENTRIES = 200
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_IGNORED_NAMES = frozenset({"SPEC_NONE", "SPEC_PET"})
_IGNORED_PREFIXES = ("PET_",)

# Immutable allowlist: SimC enum class prefix -> SimC actor token.
# Ordered longest-prefix-first so e.g. DEMON_HUNTER_ is matched before a
# hypothetical shorter collision.
_CLASS_PREFIXES: tuple[tuple[str, str], ...] = (
    ("DEATH_KNIGHT_", "deathknight"),
    ("DEMON_HUNTER_", "demonhunter"),
    ("DRUID_", "druid"),
    ("EVOKER_", "evoker"),
    ("HUNTER_", "hunter"),
    ("MAGE_", "mage"),
    ("MONK_", "monk"),
    ("PALADIN_", "paladin"),
    ("PRIEST_", "priest"),
    ("ROGUE_", "rogue"),
    ("SHAMAN_", "shaman"),
    ("WARLOCK_", "warlock"),
    ("WARRIOR_", "warrior"),
)
_ALL_CLASS_TOKENS = frozenset(token for _, token in _CLASS_PREFIXES)

_DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "local_gear_advisor"
    / "data"
    / "spec_registry.json"
)


class GeneratorError(RuntimeError):
    """Concise, user-facing generator failure (no stack trace needed)."""


def _class_and_spec_token(name: str) -> tuple[str, str]:
    for prefix, token in _CLASS_PREFIXES:
        if name.startswith(prefix):
            spec_token = name[len(prefix) :].lower()
            if not spec_token:
                raise GeneratorError(
                    f"specialization name has no suffix after class prefix: {name}"
                )
            if not _TOKEN_RE.fullmatch(spec_token):
                raise GeneratorError(
                    f"invalid specialization token generated from {name}: {spec_token}"
                )
            return token, spec_token
    raise GeneratorError(f"unrecognized specialization class prefix: {name}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse any HTTP redirect: the fetch must land on the pinned URL directly."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
        raise GeneratorError(f"unexpected redirect during source fetch: {newurl}")


def _default_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect())


def source_url_for(revision: str) -> str:
    return f"https://{_ALLOWED_HOST}{_SOURCE_PATH_TEMPLATE.format(revision=revision)}"


def fetch_source(
    revision: str,
    *,
    opener_factory: Callable[[], Any] = _default_opener,
) -> bytes:
    if not _REVISION_RE.fullmatch(revision):
        raise GeneratorError(f"revision must be a lowercase hex string: {revision!r}")
    url = source_url_for(revision)
    request = urllib.request.Request(  # noqa: S310 -- URL is constructed from fixed HTTPS parts
        url, headers={"User-Agent": "local-gear-advisor-spec-registry-generator"}
    )
    opener = opener_factory()
    try:
        with opener.open(request, timeout=30) as response:
            if response.status != 200:
                raise GeneratorError(f"fetch failed with HTTP {response.status}: {url}")
            final_url = response.geturl()
            if final_url != url:
                raise GeneratorError(
                    f"refusing source served from an unexpected final URL: {final_url}"
                )
            raw = response.read(_MAX_SOURCE_BYTES + 1)
    except urllib.error.URLError as exc:
        raise GeneratorError(f"could not fetch pinned source: {exc}") from exc
    except OSError as exc:
        raise GeneratorError(f"could not fetch pinned source: {exc}") from exc
    if len(raw) > _MAX_SOURCE_BYTES:
        raise GeneratorError(f"source exceeds the {_MAX_SOURCE_BYTES}-byte safety limit")
    return raw


def read_local_source(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise GeneratorError(f"could not read source fixture: {exc}") from exc
    if size > _MAX_SOURCE_BYTES:
        raise GeneratorError(f"source exceeds the {_MAX_SOURCE_BYTES}-byte safety limit")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GeneratorError(f"could not read source fixture: {exc}") from exc
    if len(raw) > _MAX_SOURCE_BYTES:
        raise GeneratorError(f"source exceeds the {_MAX_SOURCE_BYTES}-byte safety limit")
    return raw


def parse_source(raw: bytes) -> list[tuple[str, str, int]]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GeneratorError(f"source is not valid UTF-8: {exc}") from exc

    entries: list[tuple[str, str, int]] = []
    seen_names: set[str] = set()
    seen_ids: set[int] = set()
    in_enum = False
    closed = False
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if not in_enum:
            if stripped.startswith("enum specialization_e"):
                in_enum = True
            continue
        if stripped.startswith("};"):
            closed = True
            break
        if not stripped:
            continue
        match = _ENUM_LINE_RE.match(stripped)
        if not match:
            raise GeneratorError(f"malformed enum line {line_number}: {stripped!r}")
        name, id_text = match.group(1), match.group(2)
        spec_id = int(id_text)
        if name in seen_names:
            raise GeneratorError(f"duplicate specialization name: {name}")
        seen_names.add(name)
        if name in _IGNORED_NAMES or name.startswith(_IGNORED_PREFIXES):
            continue
        if spec_id <= 0:
            raise GeneratorError(f"non-positive specialization id for {name}: {spec_id}")
        if spec_id in seen_ids:
            raise GeneratorError(f"duplicate specialization id {spec_id} for {name}")
        seen_ids.add(spec_id)
        class_token, spec_token = _class_and_spec_token(name)
        entries.append((class_token, spec_token, spec_id))

    if not in_enum:
        raise GeneratorError("source does not contain the specialization_e enum")
    if not closed:
        raise GeneratorError("source enum specialization_e has no closing brace")
    if not (_MIN_EXPECTED_ENTRIES <= len(entries) <= _MAX_EXPECTED_ENTRIES):
        raise GeneratorError(
            f"parsed {len(entries)} specializations, expected between "
            f"{_MIN_EXPECTED_ENTRIES} and {_MAX_EXPECTED_ENTRIES}"
        )
    found_classes = {class_token for class_token, _, _ in entries}
    missing_classes = _ALL_CLASS_TOKENS - found_classes
    if missing_classes:
        raise GeneratorError(
            "source is missing specializations for classes: " + ", ".join(sorted(missing_classes))
        )
    return entries


def build_registry(
    entries: list[tuple[str, str, int]], *, revision: str, source_sha256: str, source_url: str
) -> dict[str, Any]:
    specs = sorted(
        ({"class": c, "spec": s, "specId": i} for c, s, i in entries),
        key=lambda entry: (entry["class"], entry["spec"]),
    )
    return {
        "schemaVersion": _SCHEMA_VERSION,
        "sourceRevision": revision,
        "sourceUrl": source_url,
        "sourceSha256": source_sha256,
        "specs": specs,
    }


def canonical_json(registry: dict[str, Any]) -> bytes:
    return (json.dumps(registry, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if hashlib.sha256(temp.read_bytes()).digest() != hashlib.sha256(data).digest():
            raise GeneratorError("temporary registry verification failed")
        os.replace(temp, path)
    except BaseException:
        if temp.exists():
            temp.unlink()
        raise


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the packaged SimC specialization registry (deterministic, no AI)."
    )
    parser.add_argument(
        "--revision", required=True, help="pinned SimulationCraft git revision (lowercase hex)"
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="local sc_specialization_data.inc fixture; skips the network fetch",
    )
    parser.add_argument(
        "--output", type=Path, default=_DEFAULT_OUTPUT, help="registry JSON output path"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the output file is up to date instead of writing it",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args = _build_argument_parser().parse_args(argv)
    try:
        if not _REVISION_RE.fullmatch(args.revision):
            raise GeneratorError(f"revision must be a lowercase hex string: {args.revision!r}")
        if args.source is not None:
            raw = read_local_source(args.source)
        else:
            raw = fetch_source(args.revision)
        source_sha256 = hashlib.sha256(raw).hexdigest()
        entries = parse_source(raw)
        registry = build_registry(
            entries,
            revision=args.revision,
            source_sha256=source_sha256,
            source_url=source_url_for(args.revision),
        )
        data = canonical_json(registry)
    except GeneratorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.check:
        try:
            existing = args.output.read_bytes()
        except OSError:
            print(f"error: registry is stale or missing: {args.output}", file=sys.stderr)
            return 1
        if existing != data:
            print(f"error: registry is stale: {args.output}", file=sys.stderr)
            return 1
        print(f"ok: {args.output} is up to date ({len(registry['specs'])} specializations)")
        return 0

    try:
        atomic_write(args.output, data)
    except (OSError, GeneratorError) as exc:
        print(f"error: could not write registry: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {args.output} ({len(registry['specs'])} specializations)")
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
