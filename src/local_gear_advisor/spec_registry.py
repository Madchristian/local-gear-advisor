from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from importlib.resources.abc import Traversable
from types import MappingProxyType
from typing import Any, Mapping

from .simc_export import _WOW_CLASSES

_SCHEMA_VERSION = 1
_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_REVISION_RE = re.compile(r"^[0-9a-f]{7,40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_EXPECTED_REGISTRY_SHA256 = "bec43c7a27d46a4ea588741d1a2bd707df8af964ccf3485b5cc1d5f0232bd10a"
_ALLOWED_TOP_KEYS = frozenset(
    {"schemaVersion", "sourceRevision", "sourceUrl", "sourceSha256", "specs"}
)
_ALLOWED_ENTRY_KEYS = frozenset({"class", "spec", "specId"})

# Mirrors tools/generate_spec_registry.py's source_url_for(); the two are
# cross-checked by test_spec_registry_generator.py so they cannot drift.
_SOURCE_HOST = "raw.githubusercontent.com"
_SOURCE_PATH_TEMPLATE = (
    "/simulationcraft/simc/{revision}/engine/dbc/generated/sc_specialization_data.inc"
)


class SpecRegistryError(RuntimeError):
    """Fail-closed: the packaged specialization registry is missing or invalid."""


@dataclass(frozen=True)
class SpecRegistry:
    source_revision: str
    source_sha256: str
    specs: Mapping[tuple[str, str], int]


def _expected_source_url(revision: str) -> str:
    return f"https://{_SOURCE_HOST}{_SOURCE_PATH_TEMPLATE.format(revision=revision)}"


def _packaged_registry_resource() -> Traversable:
    return resources.files("local_gear_advisor").joinpath("data", "spec_registry.json")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SpecRegistryError(f"specialization registry has duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _parse_registry(raw: bytes) -> SpecRegistry:
    try:
        payload: Any = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SpecRegistryError(f"specialization registry is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise SpecRegistryError("specialization registry root must be an object")
    if set(payload.keys()) != _ALLOWED_TOP_KEYS:
        unexpected = sorted(set(payload.keys()) ^ _ALLOWED_TOP_KEYS)
        raise SpecRegistryError(
            f"specialization registry has unexpected top-level keys: {unexpected}"
        )
    if payload.get("schemaVersion") != _SCHEMA_VERSION:
        raise SpecRegistryError("specialization registry schemaVersion is missing or unsupported")
    revision = payload.get("sourceRevision")
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        raise SpecRegistryError("specialization registry has no valid sourceRevision")
    source_sha256 = payload.get("sourceSha256")
    if not isinstance(source_sha256, str) or not _SHA256_RE.fullmatch(source_sha256):
        raise SpecRegistryError("specialization registry has no valid sourceSha256")
    if payload.get("sourceUrl") != _expected_source_url(revision):
        raise SpecRegistryError("specialization registry sourceUrl does not match sourceRevision")
    entries = payload.get("specs")
    if not isinstance(entries, list) or not entries:
        raise SpecRegistryError("specialization registry has no specs")

    specs: dict[tuple[str, str], int] = {}
    seen_ids: set[int] = set()
    previous_key: tuple[str, str] | None = None
    found_classes: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry.keys()) != _ALLOWED_ENTRY_KEYS:
            raise SpecRegistryError(f"specialization registry entry is malformed: {entry!r}")
        class_token = entry.get("class")
        spec_token = entry.get("spec")
        spec_id = entry.get("specId")
        if not isinstance(class_token, str) or class_token not in _WOW_CLASSES:
            raise SpecRegistryError(
                f"specialization registry has an unknown class: {class_token!r}"
            )
        if not isinstance(spec_token, str) or not _TOKEN_RE.fullmatch(spec_token):
            raise SpecRegistryError(
                f"specialization registry has an invalid spec token: {spec_token!r}"
            )
        if not isinstance(spec_id, int) or isinstance(spec_id, bool) or spec_id <= 0:
            raise SpecRegistryError(
                f"specialization registry has a non-positive spec id: {spec_id!r}"
            )
        key = (class_token, spec_token)
        if key in specs:
            raise SpecRegistryError(
                f"specialization registry has a duplicate class/spec pair: {key}"
            )
        if spec_id in seen_ids:
            raise SpecRegistryError(f"specialization registry has a duplicate spec id: {spec_id}")
        if previous_key is not None and key < previous_key:
            raise SpecRegistryError("specialization registry entries are not canonically ordered")
        previous_key = key
        seen_ids.add(spec_id)
        found_classes.add(class_token)
        specs[key] = spec_id

    missing_classes = _WOW_CLASSES - found_classes
    if missing_classes:
        raise SpecRegistryError(
            "specialization registry is missing classes: " + ", ".join(sorted(missing_classes))
        )

    return SpecRegistry(
        source_revision=revision,
        source_sha256=source_sha256,
        specs=MappingProxyType(specs),
    )


@lru_cache(maxsize=1)
def load_spec_registry() -> SpecRegistry:
    resource = _packaged_registry_resource()
    try:
        raw = resource.read_bytes()
    except (OSError, KeyError) as exc:
        raise SpecRegistryError(f"packaged specialization registry is missing: {resource}") from exc
    if hashlib.sha256(raw).hexdigest() != _EXPECTED_REGISTRY_SHA256:
        raise SpecRegistryError("packaged specialization registry integrity hash does not match")
    return _parse_registry(raw)
