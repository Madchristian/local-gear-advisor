import json
from pathlib import Path

import pytest

from local_gear_advisor import spec_registry as sr

_REVISION = "5a982a3"
_SHA256 = "b57147ebc86d32b9a9a0c93e71230e790aa36653cd47fc388e4176d9dce0ea1f"
_SOURCE_URL = (
    "https://raw.githubusercontent.com/simulationcraft/simc/"
    f"{_REVISION}/engine/dbc/generated/sc_specialization_data.inc"
)


def _payload(specs: list[dict], **overrides) -> bytes:
    base = {
        "schemaVersion": 1,
        "sourceRevision": _REVISION,
        "sourceUrl": _SOURCE_URL,
        "sourceSha256": _SHA256,
        "specs": specs,
    }
    base.update(overrides)
    return json.dumps(base).encode("utf-8")


_MINIMAL_SPECS = [{"class": "druid", "spec": "guardian", "specId": 104}]


def test_load_spec_registry_covers_all_current_specializations_from_packaged_data() -> None:
    registry = sr.load_spec_registry()

    assert registry.source_revision == "5a982a3"
    assert len(registry.specs) == 40
    assert registry.specs[("druid", "guardian")] == 104
    assert registry.specs[("demonhunter", "devourer")] == 1480
    assert registry.specs[("paladin", "holy")] == 65
    assert registry.specs[("shaman", "elemental")] == 262
    assert ("spec", "none") not in registry.specs


def test_load_spec_registry_covers_every_known_wow_class() -> None:
    from local_gear_advisor.simc_export import _WOW_CLASSES

    registry = sr.load_spec_registry()
    covered = {class_token for class_token, _ in registry.specs}

    assert covered == _WOW_CLASSES


def test_parse_registry_rejects_invalid_json() -> None:
    with pytest.raises(sr.SpecRegistryError, match="not valid JSON"):
        sr._parse_registry(b"not json")


def test_parse_registry_rejects_invalid_utf8_as_domain_error() -> None:
    with pytest.raises(sr.SpecRegistryError, match="not valid JSON"):
        sr._parse_registry(b"\xff")


def test_parse_registry_rejects_duplicate_json_keys() -> None:
    with pytest.raises(sr.SpecRegistryError, match="duplicate JSON key"):
        sr._parse_registry(b'{"schemaVersion":1,"schemaVersion":1}')


def test_parse_registry_rejects_missing_schema_version() -> None:
    payload = _payload(_MINIMAL_SPECS)
    payload = json.dumps({**json.loads(payload), "schemaVersion": None}).encode("utf-8")
    with pytest.raises(sr.SpecRegistryError, match="schemaVersion"):
        sr._parse_registry(payload)


def test_parse_registry_rejects_unexpected_top_level_key() -> None:
    obj = json.loads(_payload(_MINIMAL_SPECS))
    obj["extra"] = "surprise"
    with pytest.raises(sr.SpecRegistryError, match="unexpected top-level keys"):
        sr._parse_registry(json.dumps(obj).encode("utf-8"))


def test_parse_registry_rejects_missing_top_level_key() -> None:
    obj = json.loads(_payload(_MINIMAL_SPECS))
    del obj["sourceUrl"]
    with pytest.raises(sr.SpecRegistryError, match="unexpected top-level keys"):
        sr._parse_registry(json.dumps(obj).encode("utf-8"))


def test_parse_registry_rejects_source_url_not_matching_revision() -> None:
    payload = _payload(_MINIMAL_SPECS, sourceUrl=_SOURCE_URL.replace(_REVISION, "deadbeef"))
    with pytest.raises(sr.SpecRegistryError, match="sourceUrl"):
        sr._parse_registry(payload)


def test_parse_registry_rejects_entry_with_extra_key() -> None:
    specs = [{"class": "druid", "spec": "guardian", "specId": 104, "extra": True}]
    with pytest.raises(sr.SpecRegistryError, match="malformed"):
        sr._parse_registry(_payload(specs))


def test_parse_registry_rejects_entry_with_missing_key() -> None:
    specs = [{"class": "druid", "spec": "guardian"}]
    with pytest.raises(sr.SpecRegistryError, match="malformed"):
        sr._parse_registry(_payload(specs))


def test_parse_registry_rejects_duplicate_class_spec_pair() -> None:
    specs = [
        {"class": "druid", "spec": "guardian", "specId": 104},
        {"class": "druid", "spec": "guardian", "specId": 999},
    ]
    with pytest.raises(sr.SpecRegistryError, match="duplicate class/spec"):
        sr._parse_registry(_payload(specs))


def test_parse_registry_rejects_duplicate_spec_id() -> None:
    specs = [
        {"class": "druid", "spec": "balance", "specId": 104},
        {"class": "druid", "spec": "guardian", "specId": 104},
    ]
    with pytest.raises(sr.SpecRegistryError, match="duplicate spec id"):
        sr._parse_registry(_payload(specs))


def test_parse_registry_rejects_non_positive_spec_id() -> None:
    specs = [{"class": "druid", "spec": "none", "specId": 0}]
    with pytest.raises(sr.SpecRegistryError, match="non-positive"):
        sr._parse_registry(_payload(specs))


def test_parse_registry_rejects_unknown_class_token() -> None:
    specs = [{"class": "spacemarine", "spec": "guardian", "specId": 104}]
    with pytest.raises(sr.SpecRegistryError, match="unknown class"):
        sr._parse_registry(_payload(specs))


def test_parse_registry_rejects_out_of_order_entries() -> None:
    specs = [
        {"class": "druid", "spec": "guardian", "specId": 104},
        {"class": "druid", "spec": "balance", "specId": 102},
    ]
    with pytest.raises(sr.SpecRegistryError, match="not canonically ordered"):
        sr._parse_registry(_payload(specs))


def test_parse_registry_rejects_incomplete_class_coverage() -> None:
    specs = [{"class": "druid", "spec": "guardian", "specId": 104}]
    with pytest.raises(sr.SpecRegistryError, match="missing classes"):
        sr._parse_registry(_payload(specs))


def test_load_spec_registry_fails_closed_when_packaged_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sr, "_packaged_registry_resource", lambda: tmp_path / "missing.json")

    with pytest.raises(sr.SpecRegistryError, match="missing"):
        sr.load_spec_registry.__wrapped__()


def test_load_spec_registry_rejects_packaged_byte_tampering(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    packaged = (
        Path(__file__).parents[1] / "src" / "local_gear_advisor" / "data" / "spec_registry.json"
    )
    tampered = packaged.read_bytes().replace(b'"specId": 250', b'"specId": 999', 1)
    path = tmp_path / "spec_registry.json"
    path.write_bytes(tampered)
    monkeypatch.setattr(sr, "_packaged_registry_resource", lambda: path)

    with pytest.raises(sr.SpecRegistryError, match="integrity hash"):
        sr.load_spec_registry.__wrapped__()


def test_loaded_registry_mapping_is_immutable() -> None:
    registry = sr.load_spec_registry()

    with pytest.raises(TypeError):
        registry.specs[("druid", "guardian")] = 999  # type: ignore[index]
