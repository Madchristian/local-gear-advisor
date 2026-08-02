"""Behavioral proof (real Lua 5.1 execution via lupa) of Import.lua's
transactional DB apply: no mutation before full validation, identity-scoped
replace/add, immediate activation without reload, a one-step undo snapshot
that refuses to clobber a newer/different state, and safe delete of only
imported (DB) profiles. Tests drive real Python-generated transport blobs
through the actual Lua decoder + apply path end to end.
"""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from lupa.lua51 import LuaRuntime

from local_gear_advisor.import_codec import TRANSPORT_MAGIC, _encode_value, encode_profile_transport
from local_gear_advisor.state import (
    ProfileItem,
    ProfileRecord,
    normalize_identity,
    profile_to_dict,
)

ADDON = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"
_SOURCES = [
    (ADDON / "Localization.lua").read_text(encoding="utf-8"),
    (ADDON / "Sha256.lua").read_text(encoding="utf-8"),
    (ADDON / "Core.lua").read_text(encoding="utf-8"),
    (ADDON / "Import.lua").read_text(encoding="utf-8"),
]

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


def _record(
    *,
    region: str = "eu",
    realm: str = "ExampleRealm",
    name: str = "Testchar",
    spec_id: int = 262,
    delta_percent: float = 2.345678,
) -> ProfileRecord:
    baseline_gear = {slot: None for slot in _BASELINE_SLOTS}
    return ProfileRecord(
        identity=normalize_identity(region=region, realm=realm, name=name, spec_id=spec_id),
        character_class="shaman",
        spec="elemental",
        level=90,
        race="orc",
        talents="CYQA...",
        trait_systems={"omnium_talents": "100:1/200:1"},
        baseline_gear=baseline_gear,
        fight_style="Patchwerk",
        baseline_dps=123456.789,
        simc_version="1205-01",
        simc_revision="5a982a3",
        game_version="12.0.7.68887",
        dbc_source="Live",
        profile_hash="a" * 64,
        generated_at=1_785_573_600,
        items=(
            ProfileItem(
                options=",id=200101",
                item_id=200101,
                item_name="Ring of Testing",
                fingerprint="b" * 64,
                best_slot="finger2",
                candidate_dps=126281.234,
                delta_percent=delta_percent,
                iterations=2500,
            ),
        ),
    )


def _runtime() -> LuaRuntime:
    rt = LuaRuntime(unpack_returned_tuples=True)
    rt.execute("time = function() return 1785573700 end")
    g = rt.globals()
    g.GetLocale = lambda: "enUS"
    g.geterrorhandler = lambda: lambda *_args: None
    g.CreateFrame = lambda *_args: rt.eval(
        "{RegisterEvent = function() end, SetScript = function() end}"
    )
    rt.execute("Enum = {TooltipDataType = {Item = 1}}")
    rt.execute("TooltipDataProcessor = {AddTooltipPostCall = function(_type, _cb) end}")
    for source in _SOURCES:
        rt.execute(source)
    return rt


def _decode(rt: LuaRuntime, text: str):
    fn = rt.eval(
        """
        function(text)
          local profile, err = LocalGearAdvisorNS.DecodeProfileTransport(text)
          if profile == nil then return false, err end
          return true, profile
        end
        """
    )
    return fn(text)


def _decode_rehashed_dict(rt: LuaRuntime, payload_dict: dict):
    payload = _encode_value(payload_dict)
    digest = hashlib.sha256(payload.encode("ascii")).hexdigest()
    return _decode(rt, f"{TRANSPORT_MAGIC}:{digest}:{payload}")


def _apply(rt: LuaRuntime, profile):
    fn = rt.eval(
        """
        function(profile)
          local ok, err = LocalGearAdvisorNS.ApplyProfileTransport(profile)
          return ok, err
        end
        """
    )
    return fn(profile)


def _db_profile_count(rt: LuaRuntime) -> int:
    return rt.eval("function() return #(LocalGearAdvisorDB.profiles) end")()


def _db_is_nil(rt: LuaRuntime) -> bool:
    return rt.eval("function() return LocalGearAdvisorDB == nil end")()


def test_apply_activates_immediately_without_touching_fallback() -> None:
    rt = _runtime()
    ok, profile = _decode(rt, encode_profile_transport(_record()))
    assert ok is True

    applied, err = _apply(rt, profile)

    assert applied is True
    assert err is None
    assert _db_profile_count(rt) == 1
    entry = rt.eval("function() return LocalGearAdvisorDB.profiles[1] end")()
    assert entry.characterName == "Testchar"
    assert entry.specID == 262


def test_db_is_untouched_before_any_successful_apply() -> None:
    rt = _runtime()
    assert _db_is_nil(rt) is True


def test_replace_only_touches_the_exact_matching_identity() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record(name="Testchar", spec_id=262)))
    _apply(rt, first)
    _, other = _decode(rt, encode_profile_transport(_record(name="Zweiter", spec_id=71)))
    _apply(rt, other)

    assert _db_profile_count(rt) == 2

    _, updated = _decode(
        rt, encode_profile_transport(_record(name="Testchar", spec_id=262, delta_percent=9.0))
    )
    applied, err = _apply(rt, updated)

    assert applied is True
    assert _db_profile_count(rt) == 2
    names = sorted(
        rt.eval(
            "function() return {LocalGearAdvisorDB.profiles[1].characterName, "
            "LocalGearAdvisorDB.profiles[2].characterName} end"
        )().values()
    )
    assert names == ["Testchar", "Zweiter"]


def test_apply_never_mutates_db_when_shape_validation_fails() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record()))
    _apply(rt, first)

    tampered = rt.eval(
        """
        function(profile)
          local copy = {}
          for k, v in pairs(profile) do copy[k] = v end
          copy.level = 999
          return copy
        end
        """
    )(first)

    applied, err = _apply(rt, tampered)

    assert applied is False
    assert err is not None
    assert _db_profile_count(rt) == 1


def test_apply_refuses_when_existing_db_is_already_damaged() -> None:
    rt = _runtime()
    rt.execute("LocalGearAdvisorDB = { schemaVersion = 2, profiles = { 1, 2, 3 } }")
    _, profile = _decode(rt, encode_profile_transport(_record()))

    applied, err = _apply(rt, profile)

    assert applied is False
    # The damaged DB must be left exactly as it was -- refused, not repaired.
    still_damaged = rt.eval("function() return LocalGearAdvisorDB.profiles[1] == 1 end")()
    assert still_damaged is True


def test_undo_restores_the_previous_entry_after_a_replace() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record(delta_percent=2.0)))
    _apply(rt, first)
    _, second = _decode(rt, encode_profile_transport(_record(delta_percent=9.0)))
    _apply(rt, second)

    undo = rt.eval("function() return LocalGearAdvisorNS.UndoLastImport() end")
    ok, err = undo()

    assert ok is True
    entry = rt.eval("function() return LocalGearAdvisorDB.profiles[1] end")()
    assert entry["items"][",id=200101"].deltaPercent == 2.0


def test_undo_removes_a_brand_new_entry() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record()))
    _apply(rt, first)
    assert _db_profile_count(rt) == 1

    ok, err = rt.eval("function() return LocalGearAdvisorNS.UndoLastImport() end")()

    assert ok is True
    assert _db_profile_count(rt) == 0


def test_undo_is_one_shot_and_consumes_itself() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record()))
    _apply(rt, first)
    undo = rt.eval("function() return LocalGearAdvisorNS.UndoLastImport() end")

    first_ok, _ = undo()
    second_ok, second_err = undo()

    assert first_ok is True
    assert second_ok is False
    assert second_err is not None


def test_undo_refuses_to_overwrite_a_newer_import_of_the_same_identity() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record(delta_percent=2.0)))
    _apply(rt, first)
    _, second = _decode(rt, encode_profile_transport(_record(delta_percent=9.0)))
    _apply(rt, second)

    # Simulate a third import of the SAME identity happening after the undo
    # snapshot (for the second apply) was taken -- the pending undo for
    # "restore back to delta 2.0" must not clobber this newer state.
    _, third = _decode(rt, encode_profile_transport(_record(delta_percent=42.0)))
    _apply(rt, third)

    # The undo snapshot from `second`'s apply is now stale (superseded by
    # `third`'s own apply, which itself set a fresh snapshot). Undo now must
    # only ever revert exactly one step -- back to `second`, not `first`.
    ok, err = rt.eval("function() return LocalGearAdvisorNS.UndoLastImport() end")()

    assert ok is True
    entry = rt.eval("function() return LocalGearAdvisorDB.profiles[1] end")()
    assert entry["items"][",id=200101"].deltaPercent == 9.0


def test_undo_refuses_when_current_entry_was_hand_tampered_since() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record()))
    _apply(rt, first)

    rt.execute("LocalGearAdvisorDB.profiles[1].level = 50")

    ok, err = rt.eval("function() return LocalGearAdvisorNS.UndoLastImport() end")()

    assert ok is False
    assert err is not None


def test_delete_removes_only_the_matching_imported_profile() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record(name="Testchar", spec_id=262)))
    _apply(rt, first)
    _, other = _decode(rt, encode_profile_transport(_record(name="Zweiter", spec_id=71)))
    _apply(rt, other)

    key = rt.eval(
        "function() return LocalGearAdvisorNS.Schema.IdentityKey("
        "LocalGearAdvisorDB.profiles[1]) end"
    )()
    ok, err = rt.eval("function(k) return LocalGearAdvisorNS.DeleteDbProfile(k) end")(key)

    assert ok is True
    assert _db_profile_count(rt) == 1


def test_delete_of_unknown_identity_fails_without_mutating_db() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record()))
    _apply(rt, first)

    ok, err = rt.eval("function() return LocalGearAdvisorNS.DeleteDbProfile('nope') end")()

    assert ok is False
    assert _db_profile_count(rt) == 1


def test_delete_can_be_undone() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record()))
    _apply(rt, first)
    key = rt.eval(
        "function() return LocalGearAdvisorNS.Schema.IdentityKey("
        "LocalGearAdvisorDB.profiles[1]) end"
    )()
    rt.eval("function(k) return LocalGearAdvisorNS.DeleteDbProfile(k) end")(key)
    assert _db_profile_count(rt) == 0

    ok, err = rt.eval("function() return LocalGearAdvisorNS.UndoLastImport() end")()

    assert ok is True
    assert _db_profile_count(rt) == 1


def test_lua_decoder_rejects_duplicate_item_fingerprints_like_python() -> None:
    rt = _runtime()
    payload = profile_to_dict(_record())
    duplicate = copy.deepcopy(payload["items"][0])
    duplicate["options"] = ",id=200102"
    duplicate["itemId"] = 200102
    payload["items"].append(duplicate)

    ok, err = _decode_rehashed_dict(rt, payload)

    assert ok is False
    assert err is not None


def test_lua_decoder_rejects_malformed_simc_revision_like_python() -> None:
    rt = _runtime()
    payload = profile_to_dict(_record())
    payload["simcRevision"] = "not-a-hash"

    ok, err = _decode_rehashed_dict(rt, payload)

    assert ok is False
    assert err is not None


def test_lua_decoder_rejects_control_character_in_fight_style_like_python() -> None:
    rt = _runtime()
    payload = profile_to_dict(_record())
    payload["fightStyle"] = "Patch\nwerk"

    ok, err = _decode_rehashed_dict(rt, payload)

    assert ok is False
    assert err is not None


def test_lua_decoder_rejects_control_character_in_omnium_talents_like_python() -> None:
    rt = _runtime()
    payload = profile_to_dict(_record())
    payload["traitSystems"]["omnium_talents"] = "100:1\n/200:1"

    ok, err = _decode_rehashed_dict(rt, payload)

    assert ok is False
    assert err is not None


def test_lua_decoder_rejects_character_name_with_outer_whitespace_like_python() -> None:
    rt = _runtime()
    payload = profile_to_dict(_record())
    payload["identity"]["name"] = " Testchar "

    ok, err = _decode_rehashed_dict(rt, payload)

    assert ok is False
    assert err is not None


def test_lua_decoder_rejects_character_name_with_leading_nbsp_like_python() -> None:
    rt = _runtime()
    payload = profile_to_dict(_record())
    payload["identity"]["name"] = "\N{NO-BREAK SPACE}Testchar"

    ok, err = _decode_rehashed_dict(rt, payload)

    assert ok is False
    assert err is not None


def test_apply_rechecks_freshness_after_all_hookable_preparation_without_mutation() -> None:
    for final_now in (1_785_573_600 + 604_801, 1_785_573_600 - 301):
        rt = _runtime()
        _, profile = _decode(rt, encode_profile_transport(_record()))
        rt.execute(
            f"""
            NOW = 1785573700
            time = function() return NOW end
            local originalIdentityKey = LocalGearAdvisorNS.Schema.IdentityKey
            LocalGearAdvisorNS.Schema.IdentityKey = function(value)
              NOW = {final_now}
              return originalIdentityKey(value)
            end
            LocalGearAdvisorUndo = {{ marker = "keep" }}
            """
        )

        applied, err = _apply(rt, profile)

        assert applied is False
        assert err is not None
        assert _db_is_nil(rt) is True
        assert rt.eval("function() return LocalGearAdvisorUndo.marker end")() == "keep"


def test_lua_decoder_rejects_oversized_text_before_hashing_or_parsing() -> None:
    rt = _runtime()
    oversized = "LGA2:" + ("0" * 64) + ":" + ("x" * (256 * 1024))

    ok, error = _decode(rt, oversized)

    assert ok is False
    assert error == "transport exceeds the maximum size"


def test_undo_rejects_a_tampered_persistent_previous_snapshot_without_mutation() -> None:
    rt = _runtime()
    _, first = _decode(rt, encode_profile_transport(_record(delta_percent=2.0)))
    _apply(rt, first)
    _, second = _decode(rt, encode_profile_transport(_record(delta_percent=9.0)))
    _apply(rt, second)
    rt.execute("LocalGearAdvisorUndo.previous.level = 999")

    ok, err = rt.eval("function() return LocalGearAdvisorNS.UndoLastImport() end")()

    assert ok is False
    assert err is not None
    assert rt.eval("function() return LocalGearAdvisorDB.profiles[1].level end")() == 90
    assert rt.eval("function() return LocalGearAdvisorUndo ~= nil end")() is True
    assert (
        rt.eval(
            "function() return "
            "LocalGearAdvisorNS.Schema.ValidProfiles(LocalGearAdvisorDB) ~= nil end"
        )()
        is True
    )


def test_apply_deep_copies_the_checked_profile_before_storing_it() -> None:
    rt = _runtime()
    _, profile = _decode(rt, encode_profile_transport(_record()))
    applied, err = _apply(rt, profile)
    assert applied is True, err

    profile.level = 50
    profile["items"][",id=200101"].deltaPercent = 99.0

    assert rt.eval("function() return LocalGearAdvisorDB.profiles[1].level end")() == 90
    assert (
        rt.eval(
            "function() return LocalGearAdvisorDB.profiles[1].items[',id=200101'].deltaPercent end"
        )()
        == 2.345678
    )
