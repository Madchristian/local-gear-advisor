from pathlib import Path

import pytest

from local_gear_advisor.profilesets import SimSettings, build_profileset_input
from local_gear_advisor.simc_export import parse_simc_export

FIXTURE = Path(__file__).parent / "fixtures" / "sample.simc"


def test_min_item_level_defaults_to_disabled() -> None:
    assert SimSettings().min_item_level == 0


def test_min_item_level_negative_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_item_level"):
        SimSettings(min_item_level=-1)


def test_min_item_level_above_sane_bound_is_rejected() -> None:
    with pytest.raises(ValueError, match="min_item_level"):
        SimSettings(min_item_level=1000)


def test_min_item_level_zero_and_positive_values_are_accepted() -> None:
    assert SimSettings(min_item_level=0).min_item_level == 0
    assert SimSettings(min_item_level=282).min_item_level == 282


def _build():
    profile = parse_simc_export(FIXTURE.read_text(encoding="utf-8"))
    return build_profileset_input(
        profile,
        SimSettings(iterations=2500, fight_style="Patchwerk", profileset_work_threads=1),
    )


def test_ring_and_trinket_candidates_target_both_slots() -> None:
    built = _build()

    assert [(variant.item_id, variant.target_slot) for variant in built.variants] == [
        (200101, "finger1"),
        (200101, "finger2"),
        (200201, "trinket1"),
        (200201, "trinket2"),
        (200001, "head"),
    ]


def test_profileset_lines_use_documented_override_syntax() -> None:
    built = _build()

    ring = built.variants[1]
    assert (
        f'profileset."{ring.profileset_name}"=finger2=,id=200101,gem_id=3001/0/3002,bonus_id=50/51'
    ) in built.input_text
    assert "iterations=2500" in built.input_text
    assert "fight_style=Patchwerk" in built.input_text
    assert "profileset_metric=dps" in built.input_text
    assert "profileset_work_threads=1" in built.input_text


def test_profileset_names_are_safe_unique_and_deterministic() -> None:
    first = _build()
    second = _build()

    names = [variant.profileset_name for variant in first.variants]
    assert len(names) == len(set(names))
    assert all(name.replace("_", "").isalnum() and "." not in name for name in names)
    assert names == [variant.profileset_name for variant in second.variants]
    assert first.profile_hash == second.profile_hash


def test_profile_hash_changes_with_scenario() -> None:
    profile = parse_simc_export(FIXTURE.read_text(encoding="utf-8"))
    patchwerk = build_profileset_input(profile, SimSettings(fight_style="Patchwerk"))
    dungeon = build_profileset_input(profile, SimSettings(fight_style="DungeonSlice"))

    assert patchwerk.profile_hash != dungeon.profile_hash


def test_duplicate_identical_bag_items_are_simulated_only_once() -> None:
    text = FIXTURE.read_text(encoding="utf-8").replace(
        "### Weekly Reward Choices",
        "#\n# Candidate Ring Duplicate (253)\n"
        "# finger1=,id=200101,gem_id=3001/0/3002,bonus_id=50/51\n\n"
        "### Weekly Reward Choices",
    )
    built = build_profileset_input(parse_simc_export(text), SimSettings())

    assert len(built.variants) == 5
    assert len({variant.profileset_name for variant in built.variants}) == 5
