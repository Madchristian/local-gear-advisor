from dataclasses import replace
from pathlib import Path

import pytest

from local_gear_advisor.pipeline import analyze_export
from local_gear_advisor.profilesets import SimSettings
from local_gear_advisor.runner import ParsedSimcReport

FIXTURE = Path(__file__).parent / "fixtures" / "sample.simc"


def _clean_export() -> str:
    return FIXTURE.read_text(encoding="utf-8").replace(
        "#\n# Malformed Candidate\n# head=this_has_no_item_id\n", ""
    )


def _fake_report(**kwargs):
    names = sorted(kwargs["expected_names"])
    return ParsedSimcReport(
        simc_version="1205-01",
        git_revision="5a982a3",
        fight_style="Patchwerk",
        game_version="12.0.7.68887",
        dbc_source="Live",
        baseline_dps=100000,
        variant_dps={name: 101000 + index for index, name in enumerate(names)},
        iterations={name: 1000 for name in names},
    )


def test_pipeline_publishes_only_after_complete_valid_results(tmp_path: Path) -> None:
    observed = {}

    def fake_runner(**kwargs):
        observed.update(kwargs)
        names = sorted(kwargs["expected_names"])
        return ParsedSimcReport(
            simc_version="1205-01",
            git_revision="5a982a3",
            fight_style="Patchwerk",
            game_version="12.0.7.68887",
            dbc_source="Live",
            baseline_dps=100000,
            variant_dps={name: 101000 + index for index, name in enumerate(names)},
            iterations={name: 1000 for name in names},
        )

    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    summary = analyze_export(
        export_text=_clean_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=fake_runner,
        staging_target=target,
    )

    assert target.is_file()
    assert "LocalGearAdvisorResults" in target.read_text(encoding="utf-8")
    assert summary.candidate_count == 3
    assert summary.variant_count == 5
    assert summary.simc_version == "1205-01"
    assert len(observed["expected_names"]) == 5


def test_malformed_candidate_blocks_publication_and_preserves_existing_result(
    tmp_path: Path,
) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    target.parent.mkdir(parents=True)
    target.write_text("old verified result", encoding="utf-8")

    with pytest.raises(ValueError, match="unparseable bag candidates"):
        analyze_export(
            export_text=FIXTURE.read_text(encoding="utf-8"),
            executable=tmp_path / "simc.exe",
            settings=SimSettings(),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=_fake_report,
            staging_target=target,
        )

    assert target.read_text(encoding="utf-8") == "old verified result"


def test_incomplete_baseline_blocks_before_simulation(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    incomplete = _clean_export().replace("neck=,id=100002\n", "")

    with pytest.raises(ValueError, match="missing slots: neck"):
        analyze_export(
            export_text=incomplete,
            executable=tmp_path / "simc.exe",
            settings=SimSettings(),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=_fake_report,
            staging_target=target,
        )


def test_non_staging_output_is_rejected_before_simulation(tmp_path: Path) -> None:
    target = tmp_path / "outside.lua"
    staging = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"

    with pytest.raises(Exception, match="restricted to the staging"):
        analyze_export(
            export_text=_clean_export(),
            executable=tmp_path / "simc.exe",
            settings=SimSettings(),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=_fake_report,
            staging_target=staging,
        )


def test_reported_scenario_or_game_data_mismatch_blocks_publication(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"

    def ptr_runner(**kwargs):
        return replace(_fake_report(**kwargs), dbc_source="PTR", game_version="12.1.0.68914")

    with pytest.raises(Exception, match="unsupported SimulationCraft game data"):
        analyze_export(
            export_text=_clean_export(),
            executable=tmp_path / "simc.exe",
            settings=SimSettings(),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=ptr_runner,
            staging_target=target,
        )
    assert not target.exists()


def test_reported_iteration_mismatch_blocks_publication(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"

    def wrong_iterations(**kwargs):
        report = _fake_report(**kwargs)
        return replace(report, iterations={name: 999 for name in report.iterations})

    with pytest.raises(Exception, match="iteration count"):
        analyze_export(
            export_text=_clean_export(),
            executable=tmp_path / "simc.exe",
            settings=SimSettings(iterations=1000),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=wrong_iterations,
            staging_target=target,
        )
    assert not target.exists()
