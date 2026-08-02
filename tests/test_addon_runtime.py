"""Behavioral proof (real Lua execution via lupa) that Core.lua's
multi-profile selection actually isolates characters at runtime. The static
checks in test_addon.py only prove certain source patterns exist; they
cannot prove that two profiles sharing an item option key never leak into
each other, or that a tampered aggregate is really refused end to end.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from _lua_wow_mock import LuaHarness, RuntimeIdentity, item_link

from local_gear_advisor.state import (
    ProfileItem,
    ProfileRecord,
    empty_state,
    merge_profile,
    normalize_identity,
    render_aggregate_lua,
)

_BASELINE_SLOTS = (
    "head",
    "neck",
    "shoulder",
    "back",
    "chest",
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
)
_NOW = 2_000_000_000
_OMNIUM_ENTRIES = ((100, 1), (200, 1))


def _profile_record(
    *,
    name: str,
    spec_id: int,
    spec: str = "protection",
    delta_percent: float = 2.0,
    options: str = ",id=200101",
    item_id: int = 200101,
    item_name: str | None = "Ring",
    generated_at: int = _NOW - 10,
) -> ProfileRecord:
    return ProfileRecord(
        identity=normalize_identity(region="eu", realm="TestRealm", name=name, spec_id=spec_id),
        character_class="paladin",
        spec=spec,
        level=90,
        race="maghar_orc",
        talents="CYQA...",
        trait_systems={"omnium_talents": "100:1/200:1"},
        baseline_gear={slot: None for slot in _BASELINE_SLOTS},
        fight_style="Patchwerk",
        baseline_dps=100000.0,
        simc_version="1205-01",
        simc_revision="5a982a3",
        game_version="12.0.7.68887",
        dbc_source="Live",
        profile_hash="a" * 64,
        generated_at=generated_at,
        items=(
            ProfileItem(
                options=options,
                item_id=item_id,
                item_name=item_name,
                fingerprint="b" * 64,
                best_slot="finger2",
                candidate_dps=100000.0 * (1 + delta_percent / 100),
                delta_percent=delta_percent,
                iterations=2500,
            ),
        ),
    )


def _identity_for(name: str, spec_id: int) -> RuntimeIdentity:
    return RuntimeIdentity(
        name=name,
        class_file="PALADIN",
        race_file="MagharOrc",
        level=90,
        spec_id=spec_id,
        realm_name="TestRealm",
        region_id=3,
        talents="CYQA...",
        omnium_entries=_OMNIUM_ENTRIES,
    )


def test_matching_character_sees_own_delta_not_the_other_characters() -> None:
    state = empty_state()
    state = merge_profile(state, _profile_record(name="Testadin", spec_id=66, delta_percent=2.0))
    state = merge_profile(state, _profile_record(name="Zweiter", spec_id=71, delta_percent=-5.0))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(state), identity=_identity_for("Testadin", 66), now=_NOW
    )

    lines = harness.show_tooltip(item_link(200101))

    assert "DPS upgrade=+2.00%" in lines
    assert "DPS downgrade=-5.00%" not in lines


def test_unknown_item_name_does_not_invalidate_the_aggregate() -> None:
    state = merge_profile(
        empty_state(), _profile_record(name="Testadin", spec_id=66, item_name=None)
    )
    harness = LuaHarness(
        results_lua=render_aggregate_lua(state), identity=_identity_for("Testadin", 66), now=_NOW
    )
    assert "DPS upgrade=+2.00%" in harness.show_tooltip(item_link(200101))


def test_secret_baseline_link_fails_closed_before_comparison() -> None:
    record = _profile_record(name="Testadin", spec_id=66)
    baseline_gear = dict(record.baseline_gear)
    baseline_gear["finger1"] = ",id=100101"
    record = replace(record, baseline_gear=baseline_gear)
    state = merge_profile(empty_state(), record)
    secret_link = item_link(100101)
    identity = replace(_identity_for("Testadin", 66), baseline_gear_links={"finger1": secret_link})
    harness = LuaHarness(
        results_lua=render_aggregate_lua(state),
        identity=identity,
        now=2_000_000_100,
        secret_values=frozenset({",id=100101"}),
    )

    assert harness.show_tooltip(item_link(200101)) == []


def test_other_character_sees_their_own_delta_for_the_same_item() -> None:
    state = empty_state()
    state = merge_profile(state, _profile_record(name="Testadin", spec_id=66, delta_percent=2.0))
    state = merge_profile(state, _profile_record(name="Zweiter", spec_id=71, delta_percent=-5.0))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(state), identity=_identity_for("Zweiter", 71), now=_NOW
    )

    lines = harness.show_tooltip(item_link(200101))

    assert "DPS downgrade=-5.00%" in lines
    assert "DPS upgrade=+2.00%" not in lines


def test_item_known_only_for_another_character_is_silent_not_leaked() -> None:
    state = empty_state()
    state = merge_profile(
        state, _profile_record(name="Testadin", spec_id=66, options=",id=1", item_id=1)
    )
    state = merge_profile(state, _profile_record(name="Zweiter", spec_id=71, options=",id=200101"))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(state), identity=_identity_for("Testadin", 66), now=_NOW
    )

    lines = harness.show_tooltip(item_link(200101))

    assert lines == []


def test_identity_with_no_matching_profile_is_silent() -> None:
    state = empty_state()
    state = merge_profile(state, _profile_record(name="Zweiter", spec_id=71))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(state),
        identity=_identity_for("SomeoneElse", 66),
        now=_NOW,
    )

    lines = harness.show_tooltip(item_link(200101))

    assert lines == []


def _hand_rolled_profile_block(*, delta_percent: float = 2.0) -> str:
    return """{
          region = "eu", server = "testrealm", characterName = "Testadin", specID = 66,
          class = "paladin", spec = "protection", level = 90, race = "maghar_orc",
          talents = "CYQA...", generatedAt = %d, profileHash = "%s",
          simcVersion = "1205-01", simcRevision = "5a982a3", gameVersion = "12.0.7.68887",
          dbcSource = "Live", fightStyle = "Patchwerk", baselineDps = 100000,
          traitSystems = { omnium_talents = "100:1/200:1" },
          baselineGear = { head=false, neck=false, shoulder=false, back=false, chest=false,
            wrist=false, hands=false, waist=false, legs=false, feet=false, finger1=false,
            finger2=false, trinket1=false, trinket2=false, main_hand=false, off_hand=false },
          items = { [",id=200101"] = { itemID=200101, name="Ring", fingerprint="%s",
            bestSlot="finger2", candidateDps=%f, deltaPercent=%f, iterations=2500,
            status="simulated" } },
        }""" % (
        _NOW - 10,
        "a" * 64,
        "b" * 64,
        100000.0 * (1 + delta_percent / 100),
        delta_percent,
    )


def test_duplicate_identity_profiles_fail_the_whole_aggregate_closed() -> None:
    tampered = f"""
    LocalGearAdvisorResults = {{
      schemaVersion = 2,
      profiles = {{
        {_hand_rolled_profile_block(delta_percent=2.0)},
        {_hand_rolled_profile_block(delta_percent=999.0)},
      }},
    }}
    """
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)

    lines = harness.show_tooltip(item_link(200101))

    assert lines == []


def test_profiles_array_with_a_hole_fails_closed_despite_valid_head_entry() -> None:
    # profiles[1] is a genuinely valid, matching entry; profiles[2] is missing
    # (a hole); profiles[3] exists. Naive ipairs() stops at the first nil and
    # would (wrongly) see only the valid index-1 entry and accept it; the
    # whole aggregate must instead be rejected because it is not a dense
    # 1..N array.
    tampered = f"""
    LocalGearAdvisorResults = {{
      schemaVersion = 2,
      profiles = {{
        [1] = {_hand_rolled_profile_block(delta_percent=2.0)},
        [3] = {_hand_rolled_profile_block(delta_percent=999.0)},
      }},
    }}
    """
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)

    lines = harness.show_tooltip(item_link(200101))

    assert lines == []


def test_duplicate_item_option_keys_fail_closed() -> None:
    profile = _hand_rolled_profile_block().replace(
        '[",id=200101"]', '[",id=200101,bonus_id=1,bonus_id=2"]'
    )
    tampered = "LocalGearAdvisorResults = { schemaVersion = 2, profiles = { " + profile + " } }"
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)
    assert harness.show_tooltip(item_link(200101)) == []


def test_item_option_id_mismatch_fails_closed() -> None:
    profile = _hand_rolled_profile_block().replace("itemID=200101", "itemID=999999")
    tampered = "LocalGearAdvisorResults = { schemaVersion = 2, profiles = { " + profile + " } }"
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)
    assert harness.show_tooltip(item_link(200101)) == []


def test_unrealistic_iterations_fail_closed() -> None:
    profile = _hand_rolled_profile_block().replace("iterations=2500", "iterations=999999999")
    tampered = "LocalGearAdvisorResults = { schemaVersion = 2, profiles = { " + profile + " } }"
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)
    assert harness.show_tooltip(item_link(200101)) == []


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("baselineDps = 100000", "baselineDps = 1000000000001"),
        ("candidateDps=102000.000000", "candidateDps=1000000000001"),
        ("deltaPercent=2.000000", "deltaPercent=1000001"),
    ],
)
def test_implausible_dps_and_delta_ranges_fail_closed(old: str, new: str) -> None:
    profile = _hand_rolled_profile_block().replace(old, new)
    tampered = "LocalGearAdvisorResults = { schemaVersion = 2, profiles = { " + profile + " } }"
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)
    assert harness.show_tooltip(item_link(200101)) == []


def test_profile_with_unsupported_region_fails_closed() -> None:
    profile = _hand_rolled_profile_block().replace('region = "eu"', 'region = "xx"')
    tampered = "LocalGearAdvisorResults = { schemaVersion = 2, profiles = { " + profile + " } }"
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)
    assert harness.show_tooltip(item_link(200101)) == []


def test_profile_with_unexpected_key_fails_closed() -> None:
    profile = _hand_rolled_profile_block().replace(
        'region = "eu",', 'unexpected = 1, region = "eu",'
    )
    tampered = "LocalGearAdvisorResults = { schemaVersion = 2, profiles = { " + profile + " } }"
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)

    assert harness.show_tooltip(item_link(200101)) == []


def test_malformed_nonmatching_profile_invalidates_whole_aggregate() -> None:
    other = _hand_rolled_profile_block(delta_percent=-5.0)
    other = other.replace('characterName = "Testadin"', 'characterName = "Other"')
    other = other.replace("specID = 66", "specID = 71")
    other = other.replace("candidateDps=95000.000000", "candidateDps=math.huge")
    tampered = f"""
    LocalGearAdvisorResults = {{
      schemaVersion = 2,
      profiles = {{
        {other},
        {_hand_rolled_profile_block(delta_percent=2.0)},
      }},
    }}
    """
    harness = LuaHarness(results_lua=tampered, identity=_identity_for("Testadin", 66), now=_NOW)

    assert harness.show_tooltip(item_link(200101)) == []


def test_gear_change_flags_stale_but_still_shows_item_state() -> None:
    state = empty_state()
    record = _profile_record(name="Testadin", spec_id=66)
    record = ProfileRecord(
        identity=record.identity,
        character_class=record.character_class,
        spec=record.spec,
        level=record.level,
        race=record.race,
        talents=record.talents,
        trait_systems=record.trait_systems,
        baseline_gear={**record.baseline_gear, "head": ",id=100001"},
        fight_style=record.fight_style,
        baseline_dps=record.baseline_dps,
        simc_version=record.simc_version,
        simc_revision=record.simc_revision,
        game_version=record.game_version,
        dbc_source=record.dbc_source,
        profile_hash=record.profile_hash,
        generated_at=record.generated_at,
        items=record.items,
    )
    state = merge_profile(state, record)
    identity = _identity_for("Testadin", 66)
    # No head item equipped at runtime even though the profile expects one:
    # baseline_gear_links stays empty, so GetInventoryItemLink returns nil.
    harness = LuaHarness(results_lua=render_aggregate_lua(state), identity=identity, now=_NOW)

    lines = harness.show_tooltip(item_link(200101))

    assert any(line.startswith("Result is stale=") for line in lines)
    assert not any(line.startswith("DPS upgrade=") for line in lines)
