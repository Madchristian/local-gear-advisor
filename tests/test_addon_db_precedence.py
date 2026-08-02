"""Behavioral proof (real Lua execution via lupa) that Core.lua's tooltip
resolution combines the immutable LocalGearAdvisorResults fallback with the
mutable, account-wide LocalGearAdvisorDB (written by Import.lua) with DB
taking precedence for an identical identity, never falling back to a
different character/spec, and never partially trusting (or crashing on) a
malformed DB.
"""

from __future__ import annotations

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
    name: str = "Testadin",
    spec_id: int = 66,
    delta_percent: float = 2.0,
    options: str = ",id=200101",
    item_id: int = 200101,
    generated_at: int = _NOW - 10,
) -> ProfileRecord:
    return ProfileRecord(
        identity=normalize_identity(region="eu", realm="TestRealm", name=name, spec_id=spec_id),
        character_class="paladin",
        spec="protection",
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
                item_name="Ring",
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


def _db_lua_from_state(state) -> str:
    """LocalGearAdvisorDB has the exact same schemaVersion-2 shape as
    LocalGearAdvisorResults; render_aggregate_lua() already produces that
    shape, just under a different global name."""
    rendered = render_aggregate_lua(state)
    return rendered.replace("LocalGearAdvisorResults", "LocalGearAdvisorDB", 1)


def _db_lua(*records: ProfileRecord) -> str:
    state = empty_state()
    for record in records:
        state = merge_profile(state, record)
    return _db_lua_from_state(state)


def test_db_profile_wins_over_fallback_for_the_same_identity() -> None:
    fallback_state = merge_profile(empty_state(), _profile_record(delta_percent=2.0))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(fallback_state),
        identity=_identity_for("Testadin", 66),
        now=_NOW,
    )
    harness.set_db(_db_lua(_profile_record(delta_percent=-9.0)))

    lines = harness.show_tooltip(item_link(200101))

    assert "DPS downgrade=-9.00%" in lines
    assert "DPS upgrade=+2.00%" not in lines


def test_fallback_used_when_db_has_no_matching_identity() -> None:
    fallback_state = merge_profile(empty_state(), _profile_record(delta_percent=2.0))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(fallback_state),
        identity=_identity_for("Testadin", 66),
        now=_NOW,
    )
    harness.set_db(_db_lua(_profile_record(name="SomeoneElse", spec_id=71, delta_percent=-9.0)))

    lines = harness.show_tooltip(item_link(200101))

    assert "DPS upgrade=+2.00%" in lines


def test_db_used_when_fallback_has_no_matching_identity() -> None:
    harness = LuaHarness(
        results_lua=render_aggregate_lua(empty_state()),
        identity=_identity_for("Testadin", 66),
        now=_NOW,
    )
    harness.set_db(_db_lua(_profile_record(delta_percent=7.5)))

    lines = harness.show_tooltip(item_link(200101))

    assert "DPS upgrade=+7.50%" in lines


def test_no_match_in_either_source_is_silent() -> None:
    harness = LuaHarness(
        results_lua=render_aggregate_lua(empty_state()),
        identity=_identity_for("Testadin", 66),
        now=_NOW,
    )
    harness.set_db(_db_lua(_profile_record(name="Zweiter", spec_id=71)))

    assert harness.show_tooltip(item_link(200101)) == []


def test_db_never_leaks_a_different_characters_profile() -> None:
    harness = LuaHarness(
        results_lua=render_aggregate_lua(empty_state()),
        identity=_identity_for("Testadin", 66),
        now=_NOW,
    )
    harness.set_db(_db_lua(_profile_record(name="Zweiter", spec_id=71, delta_percent=-9.0)))

    lines = harness.show_tooltip(item_link(200101))

    assert lines == []
    assert not any("DPS downgrade" in line for line in lines)


def test_malformed_db_does_not_crash_and_falls_back_cleanly() -> None:
    fallback_state = merge_profile(empty_state(), _profile_record(delta_percent=2.0))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(fallback_state),
        identity=_identity_for("Testadin", 66),
        now=_NOW,
    )
    harness.set_db("LocalGearAdvisorDB = { schemaVersion = 2, profiles = { 1, 2, 3 } }")

    lines = harness.show_tooltip(item_link(200101))

    assert "DPS upgrade=+2.00%" in lines


def test_malformed_db_never_partially_trusts_a_bad_entry_even_when_it_matches() -> None:
    # One entry is a well-formed profile for a DIFFERENT character; the other
    # matches the current character but has an implausible candidateDps --
    # the whole DB must be refused, not just the bad entry, and the valid
    # fallback profile must still be usable afterwards.
    fallback_state = merge_profile(empty_state(), _profile_record(delta_percent=2.0))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(fallback_state),
        identity=_identity_for("Testadin", 66),
        now=_NOW,
    )
    db_state = merge_profile(empty_state(), _profile_record(name="Zweiter", spec_id=71))
    db_state = merge_profile(db_state, _profile_record(delta_percent=-5.0))
    db_lua = _db_lua_from_state(db_state)
    tampered_db = db_lua.replace("candidateDps = 95000", "candidateDps = math.huge")
    assert tampered_db != db_lua, "replacement target not found in rendered DB Lua"
    harness.set_db(tampered_db)

    lines = harness.show_tooltip(item_link(200101))

    assert "DPS upgrade=+2.00%" in lines
    assert not any("DPS downgrade" in line for line in lines)


def test_db_absent_falls_back_exactly_like_before() -> None:
    fallback_state = merge_profile(empty_state(), _profile_record(delta_percent=2.0))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(fallback_state),
        identity=_identity_for("Testadin", 66),
        now=_NOW,
    )

    lines = harness.show_tooltip(item_link(200101))

    assert "DPS upgrade=+2.00%" in lines
