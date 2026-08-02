import json
import subprocess
from pathlib import Path

import pytest

from local_gear_advisor.runner import (
    SimcRunError,
    parse_json2_report,
    run_simc,
)

REPORT = Path(__file__).parent / "fixtures" / "profileset-report.json"


def test_parse_json2_report_reads_baseline_and_profileset_means() -> None:
    parsed = parse_json2_report(
        json.loads(REPORT.read_text(encoding="utf-8")),
        expected_names={"item_200101_finger1_a", "item_200101_finger2_b"},
    )

    assert parsed.simc_version == "1205-01"
    assert parsed.git_revision == "5a982a3"
    assert parsed.fight_style == "Patchwerk"
    assert parsed.game_version == "12.0.7.68887"
    assert parsed.dbc_source == "Live"
    assert parsed.baseline_dps == 100000.0
    assert parsed.variant_dps["item_200101_finger2_b"] == 102000.0
    assert parsed.iterations["item_200101_finger1_a"] == 2500


def test_parse_json2_report_rejects_missing_expected_profileset() -> None:
    with pytest.raises(SimcRunError, match="missing profileset"):
        parse_json2_report(
            json.loads(REPORT.read_text(encoding="utf-8")),
            expected_names={"item_200101_finger1_a", "missing"},
        )


def test_parse_json2_report_rejects_error_log() -> None:
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    payload["logs"] = [{"level": "error", "message": "unsupported effect"}]
    with pytest.raises(SimcRunError, match="unsupported effect"):
        parse_json2_report(
            payload,
            expected_names={"item_200101_finger1_a", "item_200101_finger2_b"},
        )


def test_parse_json2_report_requires_exact_provenance() -> None:
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    payload.pop("git_revision")
    with pytest.raises(SimcRunError, match="git revision"):
        parse_json2_report(
            payload,
            expected_names={"item_200101_finger1_a", "item_200101_finger2_b"},
        )


def test_parse_json2_report_requires_dbc_provenance() -> None:
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    payload["sim"]["options"].pop("dbc")
    with pytest.raises(SimcRunError, match="DBC provenance"):
        parse_json2_report(
            payload,
            expected_names={"item_200101_finger1_a", "item_200101_finger2_b"},
        )


def test_run_simc_uses_argv_shell_false_and_json2_file(tmp_path: Path) -> None:
    executable = tmp_path / "simc.exe"
    executable.write_bytes(b"test executable")
    observed: dict[str, object] = {}

    def fake_run(argv, **kwargs):
        observed["argv"] = argv
        observed.update(kwargs)
        report_arg = next(arg for arg in argv if arg.startswith("json2="))
        Path(report_arg.partition("=")[2]).write_text(
            REPORT.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    result = run_simc(
        executable=executable,
        input_text='paladin="Testadin"\n',
        expected_names={"item_200101_finger1_a", "item_200101_finger2_b"},
        run_root=tmp_path / "runs",
        timeout_seconds=123,
        process_runner=fake_run,
    )

    assert observed["shell"] is False
    assert observed["timeout"] == 123
    assert observed["cwd"] == executable.parent
    assert observed["argv"][0] == str(executable.resolve())
    assert any(str(arg).startswith("json2=") for arg in observed["argv"])
    assert result.baseline_dps == 100000.0


def test_run_simc_rejects_wrong_executable_basename(tmp_path: Path) -> None:
    executable = tmp_path / "SimulationCraft.exe"
    executable.write_bytes(b"test executable")
    called = False

    def should_not_run(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("process must not be started for a rejected executable")

    with pytest.raises(SimcRunError, match="simc.exe"):
        run_simc(
            executable=executable,
            input_text='paladin="Testadin"\n',
            expected_names=set(),
            run_root=tmp_path / "runs",
            process_runner=should_not_run,
        )

    assert called is False
    assert not (tmp_path / "runs").exists()


def test_run_simc_accepts_correct_basename_case_insensitively(tmp_path: Path) -> None:
    executable = tmp_path / "SimC.EXE"
    executable.write_bytes(b"test executable")

    def fake_run(argv, **_kwargs):
        report_arg = next(arg for arg in argv if arg.startswith("json2="))
        Path(report_arg.partition("=")[2]).write_text(
            REPORT.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    result = run_simc(
        executable=executable,
        input_text='paladin="Testadin"\n',
        expected_names={"item_200101_finger1_a", "item_200101_finger2_b"},
        run_root=tmp_path / "runs",
        process_runner=fake_run,
    )

    assert result.baseline_dps == 100000.0


def test_run_simc_timeout_is_a_closed_failure(tmp_path: Path) -> None:
    executable = tmp_path / "simc.exe"
    executable.write_bytes(b"test executable")

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired("simc", 5)

    with pytest.raises(SimcRunError, match="timed out"):
        run_simc(
            executable=executable,
            input_text='paladin="Testadin"\n',
            expected_names=set(),
            run_root=tmp_path / "runs",
            timeout_seconds=5,
            process_runner=timeout,
        )


def test_run_simc_rejects_warning_even_with_zero_exit_code(tmp_path: Path) -> None:
    executable = tmp_path / "simc.exe"
    executable.write_bytes(b"test executable")

    def warning(argv, **_kwargs):
        report_arg = next(arg for arg in argv if arg.startswith("json2="))
        Path(report_arg.partition("=")[2]).write_text(
            REPORT.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return subprocess.CompletedProcess(
            argv, 0, stdout="Warning: special effect is not implemented", stderr=""
        )

    with pytest.raises(SimcRunError, match="warning"):
        run_simc(
            executable=executable,
            input_text='paladin="Testadin"\n',
            expected_names={"item_200101_finger1_a", "item_200101_finger2_b"},
            run_root=tmp_path / "runs",
            process_runner=warning,
        )
