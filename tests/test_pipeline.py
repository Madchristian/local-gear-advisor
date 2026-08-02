from dataclasses import replace
from pathlib import Path

import pytest

from local_gear_advisor.pipeline import ExcludedCandidate, analyze_export
from local_gear_advisor.profilesets import SimSettings
from local_gear_advisor.runner import ParsedSimcReport

FIXTURE = Path(__file__).parent / "fixtures" / "sample.simc"


def _clean_export() -> str:
    return FIXTURE.read_text(encoding="utf-8").replace(
        "#\n# Malformed Candidate\n# head=this_has_no_item_id\n", ""
    )


def _druid_guardian_export() -> str:
    return (
        _clean_export()
        .replace('paladin="Testadin"', 'druid="Testadin"')
        .replace("spec=protection", "spec=guardian")
    )


def _export_with_weapon_candidate() -> str:
    return _clean_export().replace(
        "# head=,id=200001,crafted_stats=36/40,crafting_quality=5\n",
        "# head=,id=200001,crafted_stats=36/40,crafting_quality=5\n"
        "#\n# Candidate Weapon (256)\n# main_hand=,id=200301,bonus_id=80\n",
    )


def _second_character_export() -> str:
    return (
        _clean_export()
        .replace('paladin="Testadin"', 'warrior="Zweiter"')
        .replace("spec=protection", "spec=arms")
    )


def _second_spec_export() -> str:
    return _clean_export().replace("spec=protection", "spec=retribution")


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
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert target.is_file()
    assert "LocalGearAdvisorResults" in target.read_text(encoding="utf-8")
    assert summary.candidate_count == 3
    assert summary.variant_count == 5
    assert summary.simc_version == "1205-01"
    assert len(observed["expected_names"]) == 5


def test_weapon_candidates_are_excluded_not_blocking(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    observed = {}

    def fake_runner(**kwargs):
        observed.update(kwargs)
        return _fake_report(**kwargs)

    summary = analyze_export(
        export_text=_export_with_weapon_candidate(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=fake_runner,
        staging_target=target,
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert target.is_file()
    assert summary.candidate_count == 3
    assert summary.variant_count == 5
    assert summary.excluded_weapon_count == 1
    assert summary.excluded_weapons == (
        ExcludedCandidate(
            item_id=200301, name="Candidate Weapon (256)", slot="main_hand", item_level=256
        ),
    )
    assert all("200301" not in name for name in observed["expected_names"])
    published = target.read_text(encoding="utf-8")
    assert "200301" not in published


def test_weapon_below_min_item_level_is_classified_as_below_threshold(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    export = _export_with_weapon_candidate().replace(
        "# Candidate Helm (256)", "# Candidate Helm (300)"
    )

    summary = analyze_export(
        export_text=export,
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000, min_item_level=282),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert summary.excluded_weapon_count == 0
    assert any(item.item_id == 200301 for item in summary.excluded_below_min_item_level)
    assert "200301" not in target.read_text(encoding="utf-8")


def test_weapon_at_or_above_min_item_level_remains_unsupported(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    export = (
        _export_with_weapon_candidate()
        .replace("# Candidate Helm (256)", "# Candidate Helm (300)")
        .replace("# Candidate Weapon (256)", "# Candidate Weapon (289)")
    )

    summary = analyze_export(
        export_text=export,
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000, min_item_level=282),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert summary.excluded_weapon_count == 1
    assert summary.excluded_weapons[0].item_id == 200301
    assert summary.excluded_weapons[0].item_level == 289
    assert not any(item.item_id == 200301 for item in summary.excluded_below_min_item_level)
    assert "200301" not in target.read_text(encoding="utf-8")


def _export_with_item_levels(
    *, ring_ilvl: str = "253", trinket_ilvl: str = "256", helm_ilvl: str = "256"
) -> str:
    text = _clean_export()
    text = text.replace("# Candidate Ring (253)", f"# Candidate Ring ({ring_ilvl})")
    text = text.replace("# Candidate Trinket (256)", f"# Candidate Trinket ({trinket_ilvl})")
    text = text.replace("# Candidate Helm (256)", f"# Candidate Helm ({helm_ilvl})")
    return text


def test_candidates_below_min_item_level_are_excluded_not_simulated(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    observed = {}

    def fake_runner(**kwargs):
        observed.update(kwargs)
        return _fake_report(**kwargs)

    summary = analyze_export(
        export_text=_export_with_item_levels(helm_ilvl="300"),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000, min_item_level=282),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=fake_runner,
        staging_target=target,
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert target.is_file()
    assert summary.candidate_count == 1
    assert summary.variant_count == 1
    assert summary.excluded_below_min_item_level_count == 2
    assert set(summary.excluded_below_min_item_level) == {
        ExcludedCandidate(
            item_id=200101, name="Candidate Ring (253)", slot="finger1", item_level=253
        ),
        ExcludedCandidate(
            item_id=200201, name="Candidate Trinket (256)", slot="trinket1", item_level=256
        ),
    }
    assert all("200101" not in name and "200201" not in name for name in observed["expected_names"])
    published = target.read_text(encoding="utf-8")
    assert "200101" not in published
    assert "200201" not in published


def test_candidate_with_missing_item_level_fails_closed_as_unknown_exclusion(
    tmp_path: Path,
) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    export = _export_with_item_levels(helm_ilvl="300").replace(
        "# Candidate Ring (253)", "# Candidate Ring"
    )
    observed = {}

    def fake_runner(**kwargs):
        observed.update(kwargs)
        return _fake_report(**kwargs)

    summary = analyze_export(
        export_text=export,
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000, min_item_level=282),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=fake_runner,
        staging_target=target,
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert summary.excluded_unknown_item_level_count == 1
    assert summary.excluded_unknown_item_level == (
        ExcludedCandidate(item_id=200101, name="Candidate Ring", slot="finger1", item_level=None),
    )
    assert summary.excluded_below_min_item_level_count == 1
    assert all("200101" not in name for name in observed["expected_names"])
    assert "200101" not in target.read_text(encoding="utf-8")


def test_candidate_with_out_of_range_item_level_fails_closed_as_unknown_exclusion(
    tmp_path: Path,
) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    export = _export_with_item_levels(helm_ilvl="300", ring_ilvl="0")

    summary = analyze_export(
        export_text=export,
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000, min_item_level=282),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert summary.excluded_unknown_item_level_count == 1
    assert summary.excluded_unknown_item_level == (
        ExcludedCandidate(item_id=200101, name="Candidate Ring (0)", slot="finger1", item_level=0),
    )


def test_min_item_level_disabled_by_default_does_not_filter(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"

    summary = analyze_export(
        export_text=_clean_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert summary.candidate_count == 3
    assert summary.excluded_below_min_item_level_count == 0


@pytest.mark.parametrize(
    ("export_text", "settings", "expected"),
    [
        (_clean_export(), SimSettings(min_item_level=999), "3 below minimum item level 999"),
        (
            _clean_export()
            .replace("# finger1=", "# main_hand=")
            .replace("# trinket1=", "# main_hand=")
            .replace("# head=", "# main_hand="),
            SimSettings(),
            "3 unsupported weapon",
        ),
        (
            _clean_export()
            .replace("# Candidate Ring (253)", "# Candidate Ring")
            .replace("# Candidate Trinket (256)", "# Candidate Trinket")
            .replace("# Candidate Helm (256)", "# Candidate Helm"),
            SimSettings(min_item_level=282),
            "3 unknown or invalid item level",
        ),
    ],
)
def test_all_excluded_error_reports_reason_and_preserves_existing_result(
    tmp_path: Path,
    export_text: str,
    settings: SimSettings,
    expected: str,
) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    target.parent.mkdir(parents=True)
    target.write_text("old verified result", encoding="utf-8")
    called = False

    def should_not_run(**kwargs):
        nonlocal called
        called = True
        return _fake_report(**kwargs)

    with pytest.raises(ValueError, match=expected):
        analyze_export(
            export_text=export_text,
            executable=tmp_path / "simc.exe",
            settings=settings,
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=should_not_run,
            staging_target=target,
            state_path=tmp_path / "state" / "profiles.json",
        )

    assert not called
    assert target.read_text(encoding="utf-8") == "old verified result"


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
            state_path=tmp_path / "state" / "profiles.json",
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
            state_path=tmp_path / "state" / "profiles.json",
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
            state_path=tmp_path / "state" / "profiles.json",
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
            state_path=tmp_path / "state" / "profiles.json",
        )
    assert not target.exists()


def test_exact_wow_build_mismatch_blocks_publication(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"

    def wrong_build(**kwargs):
        return replace(_fake_report(**kwargs), game_version="12.0.7.99999")

    with pytest.raises(Exception, match="unsupported SimulationCraft game data"):
        analyze_export(
            export_text=_clean_export(),
            executable=tmp_path / "simc.exe",
            settings=SimSettings(),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=wrong_build,
            staging_target=target,
            state_path=tmp_path / "state" / "profiles.json",
        )
    assert not target.exists()


def test_titan_disc_belt_candidate_blocks_before_simulation(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    belt_export = _clean_export().replace("id=200001", "id=242664")
    called = False

    def should_not_run(**kwargs):
        nonlocal called
        called = True
        return _fake_report(**kwargs)

    with pytest.raises(ValueError, match="Titan Disc belt"):
        analyze_export(
            export_text=belt_export,
            executable=tmp_path / "simc.exe",
            settings=SimSettings(),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=should_not_run,
            staging_target=target,
            state_path=tmp_path / "state" / "profiles.json",
        )
    assert not called
    assert not target.exists()


def test_titan_disc_belt_below_min_item_level_still_blocks_before_simulation(
    tmp_path: Path,
) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    belt_export = (
        _clean_export()
        .replace("id=200001", "id=242664")
        .replace("# Candidate Helm (256)", "# Candidate Helm (100)")
    )
    called = False

    def should_not_run(**kwargs):
        nonlocal called
        called = True
        return _fake_report(**kwargs)

    with pytest.raises(ValueError, match="Titan Disc belt"):
        analyze_export(
            export_text=belt_export,
            executable=tmp_path / "simc.exe",
            settings=SimSettings(min_item_level=282),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=should_not_run,
            staging_target=target,
            state_path=tmp_path / "state" / "profiles.json",
        )
    assert not called
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
            state_path=tmp_path / "state" / "profiles.json",
        )
    assert not target.exists()


def test_guardian_druid_export_is_accepted_and_renders_spec_id_104(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"

    summary = analyze_export(
        export_text=_druid_guardian_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=tmp_path / "state" / "profiles.json",
    )

    assert summary.spec == "guardian"
    published = target.read_text(encoding="utf-8")
    assert 'class = "druid"' in published
    assert 'spec = "guardian"' in published
    assert "specID = 104" in published


def test_unknown_class_spec_pair_fails_closed_before_simulation(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    export = (
        _clean_export()
        .replace('paladin="Testadin"', 'warrior="Testadin"')
        .replace("spec=protection", "spec=made_up_spec")
    )
    called = False

    def should_not_run(**kwargs):
        nonlocal called
        called = True
        return _fake_report(**kwargs)

    with pytest.raises(ValueError, match="unsupported class/spec pair"):
        analyze_export(
            export_text=export,
            executable=tmp_path / "simc.exe",
            settings=SimSettings(),
            results_path=target,
            run_root=tmp_path / "runs",
            simc_runner=should_not_run,
            staging_target=target,
            state_path=tmp_path / "state" / "profiles.json",
        )

    assert not called
    assert not target.exists()


def test_registry_revision_mismatch_blocks_publication_and_preserves_existing_result(
    tmp_path: Path,
) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    target.parent.mkdir(parents=True)
    target.write_text("old verified result", encoding="utf-8")

    def wrong_revision(**kwargs):
        return replace(_fake_report(**kwargs), git_revision="deadbeef")

    with pytest.raises(Exception, match="registry revision"):
        analyze_export(
            export_text=_clean_export(),
            executable=tmp_path / "simc.exe",
            settings=SimSettings(iterations=1000),
            results_path=target,
            run_root=tmp_path / "runs",
            generated_at=1785573600,
            simc_runner=wrong_revision,
            staging_target=target,
            state_path=tmp_path / "state" / "profiles.json",
        )

    assert target.read_text(encoding="utf-8") == "old verified result"


def test_two_characters_coexist_after_separate_analyses(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    state_path = tmp_path / "state" / "profiles.json"

    first = analyze_export(
        export_text=_clean_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )
    second = analyze_export(
        export_text=_second_character_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573700,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )

    assert first.retained_profile_count == 1
    assert second.retained_profile_count == 2
    published = target.read_text(encoding="utf-8")
    assert 'characterName = "Testadin"' in published
    assert 'characterName = "Zweiter"' in published
    assert published.count("schemaVersion = 2") == 1


def test_updating_one_character_retains_the_other(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    state_path = tmp_path / "state" / "profiles.json"

    analyze_export(
        export_text=_clean_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )
    analyze_export(
        export_text=_second_character_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573700,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )
    third = analyze_export(
        export_text=_clean_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573800,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )

    assert third.retained_profile_count == 2
    published = target.read_text(encoding="utf-8")
    assert published.count('characterName = "Testadin"') == 1
    assert published.count('characterName = "Zweiter"') == 1
    assert "generatedAt = 1785573800" in published
    assert "generatedAt = 1785573700" in published
    assert "generatedAt = 1785573600" not in published


def test_two_specs_of_same_character_are_both_retained(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    state_path = tmp_path / "state" / "profiles.json"

    analyze_export(
        export_text=_clean_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )
    second = analyze_export(
        export_text=_second_spec_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573700,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )

    assert second.retained_profile_count == 2
    published = target.read_text(encoding="utf-8")
    assert published.count('characterName = "Testadin"') == 2
    assert 'spec = "protection"' in published
    assert 'spec = "retribution"' in published
    assert "specID = 66" in published
    assert "specID = 70" in published


def test_analysis_summary_reports_identity_and_retained_count(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    state_path = tmp_path / "state" / "profiles.json"

    summary = analyze_export(
        export_text=_clean_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )

    assert summary.region == "eu"
    assert summary.realm == "testrealm"
    assert summary.spec_id == 66
    assert summary.retained_profile_count == 1


def test_publication_failure_preserves_previous_state_json_and_lua(tmp_path: Path) -> None:
    target = tmp_path / "addon" / "LocalGearAdvisor" / "Results.lua"
    state_path = tmp_path / "state" / "profiles.json"

    analyze_export(
        export_text=_clean_export(),
        executable=tmp_path / "simc.exe",
        settings=SimSettings(iterations=1000),
        results_path=target,
        run_root=tmp_path / "runs",
        generated_at=1785573600,
        simc_runner=_fake_report,
        staging_target=target,
        state_path=state_path,
    )
    published_before = target.read_text(encoding="utf-8")
    state_before = state_path.read_text(encoding="utf-8")

    def wrong_revision(**kwargs):
        return replace(_fake_report(**kwargs), git_revision="deadbeef")

    with pytest.raises(Exception, match="registry revision"):
        analyze_export(
            export_text=_second_character_export(),
            executable=tmp_path / "simc.exe",
            settings=SimSettings(iterations=1000),
            results_path=target,
            run_root=tmp_path / "runs",
            generated_at=1785573700,
            simc_runner=wrong_revision,
            staging_target=target,
            state_path=state_path,
        )

    assert target.read_text(encoding="utf-8") == published_before
    assert state_path.read_text(encoding="utf-8") == state_before
