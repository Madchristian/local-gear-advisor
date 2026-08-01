from dataclasses import replace as dc_replace
from pathlib import Path

import pytest

from local_gear_advisor.profilesets import SimSettings, build_profileset_input
from local_gear_advisor.results import (
    ensure_supported_profile,
    evaluate_results,
    render_results_lua,
    write_atomic_verified,
)
from local_gear_advisor.runner import ParsedSimcReport
from local_gear_advisor.simc_export import parse_simc_export

FIXTURE = Path(__file__).parent / "fixtures" / "sample.simc"


def _evaluation(export_text: str | None = None):
    profile = parse_simc_export(
        export_text if export_text is not None else FIXTURE.read_text(encoding="utf-8")
    )
    built = build_profileset_input(profile, SimSettings(iterations=2500))
    values = {
        variant.profileset_name: 100000.0 + index * 1000
        for index, variant in enumerate(built.variants, start=1)
    }
    report = ParsedSimcReport(
        simc_version="1205-01",
        git_revision="5a982a3",
        fight_style="Patchwerk",
        game_version="12.0.7.68887",
        dbc_source="Live",
        baseline_dps=100000.0,
        variant_dps=values,
        iterations={name: 2500 for name in values},
    )
    return profile, built, evaluate_results(profile, built, report, generated_at=1785573600)


def test_evaluation_selects_best_ring_and_trinket_target() -> None:
    _profile, _built, result = _evaluation()

    ring = next(item for item in result.items if item.item_id == 200101)
    trinket = next(item for item in result.items if item.item_id == 200201)
    assert ring.best_slot == "finger2"
    assert ring.candidate_dps == 102000.0
    assert ring.delta_percent == pytest.approx(2.0)
    assert trinket.best_slot == "trinket2"


def test_lua_is_keyed_by_exact_simc_item_options() -> None:
    profile, built, result = _evaluation()
    lua = render_results_lua(profile, built, result)

    assert "LocalGearAdvisorResults = {" in lua
    assert '[",id=200101,gem_id=3001/0/3002,bonus_id=50/51"]' in lua
    assert 'bestSlot = "finger2"' in lua
    assert 'profileHash = "' + built.profile_hash + '"' in lua
    assert 'simcVersion = "1205-01"' in lua
    assert 'gameVersion = "12.0.7.68887"' in lua
    assert 'dbcSource = "Live"' in lua
    assert 'region = "eu"' in lua
    assert 'server = "testrealm"' in lua
    assert "specID = 66" in lua
    assert "level = 90" in lua
    assert 'race = "maghar_orc"' in lua
    assert 'talents = "CYQA..."' in lua
    assert 'omnium_talents = "100:1/200:1"' in lua
    assert 'finger1 = ",id=100101,enchant_id=7001,bonus_id=10/20"' in lua
    assert "deltaPercent = 2" in lua


def test_lua_records_legal_empty_offhand_explicitly() -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(
        "# Equipped Shield (250)\noff_hand=,id=100301,bonus_id=40\n", ""
    )
    profile, built, result = _evaluation(text)

    assert "    off_hand = false," in render_results_lua(profile, built, result)


def test_atomic_writer_rejects_concurrent_publication_lock(tmp_path: Path) -> None:
    target = tmp_path / "Results.lua"
    target.write_text("old", encoding="utf-8")
    lock = tmp_path / "Results.lua.lock"
    lock.write_text("busy", encoding="ascii")

    with pytest.raises(OSError, match="publication is already in progress"):
        write_atomic_verified(target, "new")

    assert target.read_text(encoding="utf-8") == "old"


def test_atomic_writer_verifies_published_bytes(tmp_path: Path) -> None:
    target = tmp_path / "Results.lua"
    write_atomic_verified(target, "LocalGearAdvisorResults = {}\n")

    assert target.read_bytes() == b"LocalGearAdvisorResults = {}\n"
    assert not (tmp_path / "Results.lua.tmp").exists()


def test_ensure_supported_profile_resolves_guardian_druid_via_registry() -> None:
    profile, _built, _result = _evaluation()
    druid_profile = dc_replace(profile, character_class="druid", spec="guardian")

    assert ensure_supported_profile(druid_profile) == 104


def test_ensure_supported_profile_resolves_demon_hunter_devourer_via_registry() -> None:
    profile, _built, _result = _evaluation()
    devourer_profile = dc_replace(profile, character_class="demonhunter", spec="devourer")

    assert ensure_supported_profile(devourer_profile) == 1480


def test_ensure_supported_profile_rejects_unknown_class_spec_pair() -> None:
    profile, _built, _result = _evaluation()
    unknown_profile = dc_replace(profile, character_class="warrior", spec="made_up_spec")

    with pytest.raises(ValueError, match="unsupported class/spec pair"):
        ensure_supported_profile(unknown_profile)
