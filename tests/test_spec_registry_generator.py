import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOL_PATH = _REPO_ROOT / "tools" / "generate_spec_registry.py"
_SOURCE_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "sc_specialization_data.inc"
_SOURCE_SHA256 = "b57147ebc86d32b9a9a0c93e71230e790aa36653cd47fc388e4176d9dce0ea1f"
_REVISION = "5a982a3"
_EXPECTED_URL = (
    "https://raw.githubusercontent.com/simulationcraft/simc/"
    f"{_REVISION}/engine/dbc/generated/sc_specialization_data.inc"
)


class _FakeResponse:
    def __init__(self, *, status: int = 200, url: str = "", body: bytes = b""):
        self.status = status
        self._url = url
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def geturl(self) -> str:
        return self._url

    def read(self, amount: int = -1) -> bytes:
        if amount is None or amount < 0:
            return self._body
        return self._body[:amount]


class _FakeOpener:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def open(self, request, timeout=None):
        return self._response


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_spec_registry", _TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load_module()


def _write_source(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "source.inc"
    path.write_text(text, encoding="utf-8")
    return path


def test_parse_source_produces_all_forty_current_specializations_deterministically(gen) -> None:
    raw = _SOURCE_FIXTURE.read_bytes()
    entries_a = gen.parse_source(raw)
    entries_b = gen.parse_source(raw)

    assert entries_a == entries_b
    assert len(entries_a) == 40
    assert ("druid", "guardian", 104) in entries_a
    assert ("demonhunter", "devourer", 1480) in entries_a
    assert ("paladin", "holy", 65) in entries_a
    assert not any(actor_class == "spec" for actor_class, _, _ in entries_a)


def test_parse_source_excludes_pet_and_none_entries(gen) -> None:
    entries = gen.parse_source(_SOURCE_FIXTURE.read_bytes())
    ids = {spec_id for _, _, spec_id in entries}

    assert 0 not in ids
    assert 1 not in ids
    assert 535 not in ids and 536 not in ids and 537 not in ids


def test_parse_source_rejects_duplicate_specialization_id(gen) -> None:
    text = "enum specialization_e {\n  WARRIOR_ARMS = 71,\n  WARRIOR_FURY = 71,\n};\n"
    with pytest.raises(gen.GeneratorError, match="duplicate"):
        gen.parse_source(text.encode("utf-8"))


def test_parse_source_rejects_unknown_class_prefix(gen) -> None:
    text = "enum specialization_e {\n  UNKNOWNCLASS_THING = 999,\n};\n"
    with pytest.raises(gen.GeneratorError, match="unrecognized"):
        gen.parse_source(text.encode("utf-8"))


def test_parse_source_rejects_invalid_generated_spec_token(gen) -> None:
    raw = _SOURCE_FIXTURE.read_bytes().replace(b"WARRIOR_ARMS", b"WARRIOR__ARMS", 1)

    with pytest.raises(gen.GeneratorError, match="invalid specialization token"):
        gen.parse_source(raw)


def test_parse_source_rejects_malformed_line(gen) -> None:
    text = "enum specialization_e {\n  this is not an enum line\n};\n"
    with pytest.raises(gen.GeneratorError, match="malformed"):
        gen.parse_source(text.encode("utf-8"))


def test_parse_source_rejects_truncated_enum_below_size_floor(gen) -> None:
    text = "enum specialization_e {\n  WARRIOR_ARMS = 71,\n};\n"
    with pytest.raises(gen.GeneratorError, match="expected between"):
        gen.parse_source(text.encode("utf-8"))


def test_parse_source_rejects_missing_enum_block(gen) -> None:
    with pytest.raises(gen.GeneratorError, match="specialization_e"):
        gen.parse_source(b"nothing to see here\n")


def test_build_and_canonical_json_round_trip_is_stable(gen) -> None:
    entries = gen.parse_source(_SOURCE_FIXTURE.read_bytes())
    registry = gen.build_registry(
        entries,
        revision=_REVISION,
        source_sha256=_SOURCE_SHA256,
        source_url="https://raw.githubusercontent.com/simulationcraft/simc/"
        f"{_REVISION}/engine/dbc/generated/sc_specialization_data.inc",
    )
    first = gen.canonical_json(registry)
    second = gen.canonical_json(registry)

    assert first == second
    payload = json.loads(first)
    assert payload["sourceRevision"] == _REVISION
    assert payload["sourceSha256"] == _SOURCE_SHA256
    assert len(payload["specs"]) == 40
    druid_guardian = next(
        s for s in payload["specs"] if s["class"] == "druid" and s["spec"] == "guardian"
    )
    assert druid_guardian["specId"] == 104
    devourer = next(
        s for s in payload["specs"] if s["class"] == "demonhunter" and s["spec"] == "devourer"
    )
    assert devourer["specId"] == 1480


def test_run_writes_registry_from_local_source_fixture(gen, tmp_path: Path) -> None:
    output = tmp_path / "spec_registry.json"

    exit_code = gen.run(
        ["--revision", _REVISION, "--source", str(_SOURCE_FIXTURE), "--output", str(output)]
    )

    assert exit_code == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["sourceRevision"] == _REVISION
    assert payload["sourceSha256"] == _SOURCE_SHA256
    assert len(payload["specs"]) == 40
    assert not list(output.parent.glob("*.tmp-*"))


def test_run_output_is_byte_identical_across_regenerations(gen, tmp_path: Path) -> None:
    output = tmp_path / "spec_registry.json"
    args = ["--revision", _REVISION, "--source", str(_SOURCE_FIXTURE), "--output", str(output)]

    assert gen.run(args) == 0
    first_bytes = output.read_bytes()
    assert gen.run(args) == 0
    second_bytes = output.read_bytes()

    assert first_bytes == second_bytes


def test_run_check_passes_when_output_matches_source(gen, tmp_path: Path) -> None:
    output = tmp_path / "spec_registry.json"
    args = ["--revision", _REVISION, "--source", str(_SOURCE_FIXTURE), "--output", str(output)]
    assert gen.run(args) == 0

    assert gen.run([*args, "--check"]) == 0


def test_run_check_fails_when_output_is_missing(gen, tmp_path: Path, capsys) -> None:
    output = tmp_path / "spec_registry.json"

    exit_code = gen.run(
        [
            "--revision",
            _REVISION,
            "--source",
            str(_SOURCE_FIXTURE),
            "--output",
            str(output),
            "--check",
        ]
    )

    assert exit_code == 1
    assert "stale" in capsys.readouterr().err.lower()


def test_run_check_detects_drift_when_source_gains_a_specialization(
    gen, tmp_path: Path, capsys
) -> None:
    output = tmp_path / "spec_registry.json"
    args = ["--revision", _REVISION, "--source", str(_SOURCE_FIXTURE), "--output", str(output)]
    assert gen.run(args) == 0

    drifted_source = _write_source(
        tmp_path,
        _SOURCE_FIXTURE.read_text(encoding="utf-8").replace(
            "  EVOKER_AUGMENTATION    = 1473,\n",
            "  EVOKER_AUGMENTATION    = 1473,\n  MAGE_ARCANE_TWO       = 9999,\n",
        ),
    )

    exit_code = gen.run(
        [
            "--revision",
            _REVISION,
            "--source",
            str(drifted_source),
            "--output",
            str(output),
            "--check",
        ]
    )

    assert exit_code == 1
    assert "stale" in capsys.readouterr().err.lower()
    assert json.loads(output.read_text(encoding="utf-8"))["specs"].__len__() == 40


def test_run_rejects_non_hex_revision(gen, tmp_path: Path, capsys) -> None:
    output = tmp_path / "spec_registry.json"

    exit_code = gen.run(
        [
            "--revision",
            "not-hex!",
            "--source",
            str(_SOURCE_FIXTURE),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 1
    assert not output.exists()


def test_parse_source_rejects_incomplete_class_coverage(gen) -> None:
    text = _SOURCE_FIXTURE.read_text(encoding="utf-8")
    text = "\n".join(line for line in text.splitlines() if "EVOKER_" not in line) + "\n"

    with pytest.raises(gen.GeneratorError, match="missing.*evoker|evoker.*missing"):
        gen.parse_source(text.encode("utf-8"))


def test_parse_source_still_accepts_full_coverage_fixture(gen) -> None:
    entries = gen.parse_source(_SOURCE_FIXTURE.read_bytes())
    assert len(entries) == 40


def test_fetch_source_rejects_response_exceeding_size_cap(gen) -> None:
    oversized = b"x" * (gen._MAX_SOURCE_BYTES + 1)
    opener = _FakeOpener(_FakeResponse(status=200, url=_EXPECTED_URL, body=oversized))

    with pytest.raises(gen.GeneratorError, match="exceeds"):
        gen.fetch_source(_REVISION, opener_factory=lambda: opener)


def test_fetch_source_accepts_response_at_size_cap(gen) -> None:
    exact = b"x" * gen._MAX_SOURCE_BYTES
    opener = _FakeOpener(_FakeResponse(status=200, url=_EXPECTED_URL, body=exact))

    raw = gen.fetch_source(_REVISION, opener_factory=lambda: opener)

    assert raw == exact


def test_fetch_source_rejects_final_url_not_matching_pinned_url(gen) -> None:
    opener = _FakeOpener(
        _FakeResponse(status=200, url="https://raw.githubusercontent.com/evil/redirect", body=b"x")
    )

    with pytest.raises(gen.GeneratorError, match="final URL"):
        gen.fetch_source(_REVISION, opener_factory=lambda: opener)


def test_fetch_source_rejects_non_200_status(gen) -> None:
    opener = _FakeOpener(_FakeResponse(status=404, url=_EXPECTED_URL, body=b""))

    with pytest.raises(gen.GeneratorError, match="404"):
        gen.fetch_source(_REVISION, opener_factory=lambda: opener)


def test_no_redirect_handler_rejects_redirects(gen) -> None:
    handler = gen._NoRedirect()

    with pytest.raises(gen.GeneratorError, match="redirect"):
        handler.redirect_request(
            None, None, 302, "Found", None, "https://raw.githubusercontent.com/evil/redirect"
        )


def test_run_rejects_local_source_exceeding_size_cap(gen, tmp_path: Path, capsys) -> None:
    big_source = tmp_path / "huge.inc"
    with big_source.open("wb") as handle:
        handle.seek(gen._MAX_SOURCE_BYTES)
        handle.write(b"\0")
    output = tmp_path / "spec_registry.json"

    exit_code = gen.run(
        ["--revision", _REVISION, "--source", str(big_source), "--output", str(output)]
    )

    assert exit_code == 1
    assert "exceeds" in capsys.readouterr().err.lower()
    assert not output.exists()


def test_run_accepts_local_source_at_size_cap(gen, tmp_path: Path) -> None:
    exact_source = tmp_path / "exact.inc"
    padding = gen._MAX_SOURCE_BYTES - len(_SOURCE_FIXTURE.read_bytes())
    assert padding >= 0
    padded_text = _SOURCE_FIXTURE.read_text(encoding="utf-8") + ("\n" * padding)
    exact_source.write_bytes(padded_text.encode("utf-8")[: gen._MAX_SOURCE_BYTES])
    output = tmp_path / "spec_registry.json"

    exit_code = gen.run(
        ["--revision", _REVISION, "--source", str(exact_source), "--output", str(output)]
    )

    assert exit_code == 0


def test_generator_and_runtime_source_url_templates_stay_in_sync(gen) -> None:
    from local_gear_advisor import spec_registry as sr

    for revision in ("5a982a3", "deadbeef", "0123456789abcdef"):
        assert gen.source_url_for(revision) == sr._expected_source_url(revision)


def test_read_local_source_rechecks_size_after_read(gen) -> None:
    class RacingSource:
        def stat(self):
            return type("Stat", (), {"st_size": 1})()

        def read_bytes(self):
            return b"x" * (gen._MAX_SOURCE_BYTES + 1)

    with pytest.raises(gen.GeneratorError, match="exceeds"):
        gen.read_local_source(RacingSource())


def test_run_reports_atomic_write_failure_without_traceback(
    gen, tmp_path: Path, monkeypatch, capsys
) -> None:
    def fail_write(_path, _data):
        raise OSError("disk full")

    monkeypatch.setattr(gen, "atomic_write", fail_write)
    output = tmp_path / "registry.json"

    exit_code = gen.run(
        ["--revision", _REVISION, "--source", str(_SOURCE_FIXTURE), "--output", str(output)]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "disk full" in captured.err
    assert "Traceback" not in captured.err
    assert not output.exists()
