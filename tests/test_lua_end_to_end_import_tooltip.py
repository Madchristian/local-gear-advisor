"""End-to-end behavioral proof (real Lua 5.1 execution via lupa, one shared
runtime): a real Python-generated transport blob travels through Import.lua's
decode -> Core.lua's shared schema validator -> Import.lua's transactional
SavedVariables apply -> Core.lua's tooltip resolver, all without a reload --
exactly the path a player takes when they paste an import string and then
hover an item. Also proves the no-mutation-on-failure, identity precedence,
and one-step-undo contracts hold end to end, not just at the unit level.
"""

from __future__ import annotations

from _lua_wow_mock import LuaHarness, RuntimeIdentity, item_link

from local_gear_advisor.import_codec import encode_profile_transport
from local_gear_advisor.state import (
    ProfileItem,
    ProfileRecord,
    empty_state,
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
_ITEM_ID = 200101
_ITEM_OPTIONS = ",id=200101"


def _record(*, delta_percent: float = 2.345678) -> ProfileRecord:
    return ProfileRecord(
        identity=normalize_identity(region="eu", realm="TestRealm", name="Testchar", spec_id=262),
        character_class="shaman",
        spec="elemental",
        level=90,
        race="orc",
        talents="CYQA...",
        trait_systems={"omnium_talents": "100:1/200:1"},
        baseline_gear={slot: None for slot in _BASELINE_SLOTS},
        fight_style="Patchwerk",
        baseline_dps=123456.789,
        simc_version="1205-01",
        simc_revision="5a982a3",
        game_version="12.0.7.68887",
        dbc_source="Live",
        profile_hash="a" * 64,
        generated_at=_NOW - 10,
        items=(
            ProfileItem(
                options=_ITEM_OPTIONS,
                item_id=_ITEM_ID,
                item_name="Ring of Testing",
                fingerprint="b" * 64,
                best_slot="finger2",
                candidate_dps=126281.234,
                delta_percent=delta_percent,
                iterations=2500,
            ),
        ),
    )


def _identity() -> RuntimeIdentity:
    return RuntimeIdentity(
        name="Testchar",
        class_file="SHAMAN",
        race_file="Orc",
        level=90,
        spec_id=262,
        realm_name="TestRealm",
        region_id=3,
        talents="CYQA...",
        omnium_entries=_OMNIUM_ENTRIES,
    )


def _harness() -> LuaHarness:
    return LuaHarness(
        results_lua=render_aggregate_lua(empty_state()),
        identity=_identity(),
        now=_NOW,
        include_import=True,
    )


def test_real_transport_applies_and_tooltip_shows_immediately_without_reload() -> None:
    harness = _harness()
    text = encode_profile_transport(_record(delta_percent=2.345678))

    decoded, profile = harness.decode_profile_transport(text)
    assert decoded is True

    applied, err = harness.apply_profile_transport(profile)
    assert applied is True
    assert err is None

    # No reload/logout between apply and this lookup: same runtime, same session.
    lines = harness.show_tooltip(item_link(_ITEM_ID))
    assert "DPS upgrade=+2.35%" in lines


def test_tampered_digest_transport_never_mutates_db_and_tooltip_stays_empty() -> None:
    harness = _harness()
    text = encode_profile_transport(_record())
    magic, digest, payload = text.split(":", 2)
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    tampered = f"{magic}:{flipped}:{payload}"

    decoded, err = harness.decode_profile_transport(tampered)

    assert decoded is False
    assert isinstance(err, str) and "digest" in err
    assert harness.db_is_nil() is True
    assert harness.show_tooltip(item_link(_ITEM_ID)) == []


def test_shape_tampered_profile_is_never_applied_and_leaves_db_untouched() -> None:
    harness = _harness()
    text = encode_profile_transport(_record())
    decoded, profile = harness.decode_profile_transport(text)
    assert decoded is True

    applied, _ = harness.apply_profile_transport(profile)
    assert applied is True
    assert harness.db_profile_count() == 1

    tamper = harness.rt.eval(
        """
        function(profile)
          local copy = {}
          for k, v in pairs(profile) do copy[k] = v end
          copy.level = 999
          return copy
        end
        """
    )
    tampered_profile = tamper(profile)

    applied_again, err = harness.apply_profile_transport(tampered_profile)

    assert applied_again is False
    assert err is not None
    # Refused before mutation: the DB still has exactly the one valid entry,
    # and the tooltip still reflects it (never a half-applied/tampered state).
    assert harness.db_profile_count() == 1
    assert "DPS upgrade=+2.35%" in harness.show_tooltip(item_link(_ITEM_ID))


def test_imported_profile_immediately_outranks_the_fallback_profile() -> None:
    fallback_state = empty_state()
    fallback_record = _record(delta_percent=99.0)
    from local_gear_advisor.state import merge_profile

    fallback_state = merge_profile(fallback_state, fallback_record)
    harness = LuaHarness(
        results_lua=render_aggregate_lua(fallback_state),
        identity=_identity(),
        now=_NOW,
        include_import=True,
    )
    # Sanity: before any import, the immutable fallback is what tooltips use.
    assert "DPS upgrade=+99.00%" in harness.show_tooltip(item_link(_ITEM_ID))

    text = encode_profile_transport(_record(delta_percent=3.0))
    decoded, profile = harness.decode_profile_transport(text)
    applied, _ = harness.apply_profile_transport(profile)
    assert decoded is True and applied is True

    lines = harness.show_tooltip(item_link(_ITEM_ID))
    assert "DPS upgrade=+3.00%" in lines
    assert not any("99.00%" in line for line in lines)


def test_undo_after_a_real_import_reverts_the_tooltip_immediately() -> None:
    harness = _harness()
    first_text = encode_profile_transport(_record(delta_percent=2.0))
    _, first_profile = harness.decode_profile_transport(first_text)
    harness.apply_profile_transport(first_profile)
    assert "DPS upgrade=+2.00%" in harness.show_tooltip(item_link(_ITEM_ID))

    second_text = encode_profile_transport(_record(delta_percent=9.0))
    _, second_profile = harness.decode_profile_transport(second_text)
    applied, _ = harness.apply_profile_transport(second_profile)
    assert applied is True
    assert "DPS upgrade=+9.00%" in harness.show_tooltip(item_link(_ITEM_ID))

    ok, err = harness.undo_last_import()
    assert ok is True
    assert err is None

    # Same runtime, no reload: the very next tooltip call must already
    # reflect the reverted state.
    lines = harness.show_tooltip(item_link(_ITEM_ID))
    assert "DPS upgrade=+2.00%" in lines
    assert not any("9.00%" in line for line in lines)


def test_delete_of_imported_profile_immediately_falls_back_and_undo_restores_it() -> None:
    fallback_state = empty_state()
    from local_gear_advisor.state import merge_profile

    fallback_state = merge_profile(fallback_state, _record(delta_percent=42.0))
    harness = LuaHarness(
        results_lua=render_aggregate_lua(fallback_state),
        identity=_identity(),
        now=_NOW,
        include_import=True,
    )
    text = encode_profile_transport(_record(delta_percent=2.0))
    _, profile = harness.decode_profile_transport(text)
    harness.apply_profile_transport(profile)
    assert "DPS upgrade=+2.00%" in harness.show_tooltip(item_link(_ITEM_ID))

    key = harness.identity_key(profile)
    ok, err = harness.delete_db_profile(key)
    assert ok is True
    assert err is None

    # Deleting the DB entry falls back to the immutable fallback profile
    # immediately, in the same session.
    assert "DPS upgrade=+42.00%" in harness.show_tooltip(item_link(_ITEM_ID))

    undo_ok, undo_err = harness.undo_last_import()
    assert undo_ok is True
    assert undo_err is None
    assert "DPS upgrade=+2.00%" in harness.show_tooltip(item_link(_ITEM_ID))
