"""Behavioral proof (real Lua 5.1 execution via lupa, generic widget mock)
of the Import page's check-before-import gating: the Import button is only
ever enabled after the exact text currently in the box has passed a real
Check (Import.lua's strict decoder), any edit to that text after a Check
immediately disables Import again, an invalid Check never mutates
SavedVariables, and clicking Import against stale/unchecked text refuses
without mutating SavedVariables either -- even if a caller bypasses the
disabled widget state entirely, RunImport's own text-match guard is the
real enforcement. A successful Import activates the profile immediately
(via the same transactional Import.lua path proven elsewhere) and refreshes
the Profiles page.
"""

from __future__ import annotations

from dataclasses import replace

from _lua_ui_mock import UIHarness

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


def _harness() -> UIHarness:
    return UIHarness(results_lua=render_aggregate_lua(empty_state()), now=1_785_573_700)


def _import_widgets(h: UIHarness):
    box = h.eval("function() return LocalGearAdvisorNS.UI._importBox end")()
    check_button = h.eval("function() return LocalGearAdvisorNS.UI._checkButton end")()
    import_button = h.eval("function() return LocalGearAdvisorNS.UI._importButton end")()
    return box, check_button, import_button


def _status_text(h: UIHarness) -> str:
    status = h.eval("function() return LocalGearAdvisorNS.UI._importStatus end")()
    return h.get_text(status)


def _db_is_nil(h: UIHarness) -> bool:
    return h.eval("function() return LocalGearAdvisorDB == nil end")()


def test_import_button_starts_disabled_before_any_check() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    _, _, import_button = _import_widgets(h)

    assert h.is_enabled(import_button) is False


def test_import_edit_box_has_clickable_area_and_mouse_click_focuses_it() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, _, _ = _import_widgets(h)

    assert h.method(box, "GetHeight") > 0
    assert h.method(box, "IsMouseEnabled") is True
    assert h.method(box, "IsFocused") is False

    h.mouse_down(box)

    assert h.method(box, "IsFocused") is True


def test_import_edit_box_is_visually_framed_and_padded() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, _, _ = _import_widgets(h)

    has_backdrop, has_border, left, right, top, bottom = h.eval(
        """
        function(widget)
          local backdrop = rawget(widget, "backdrop")
          local insets = rawget(widget, "textInsets")
          return backdrop ~= nil,
                 backdrop and backdrop.edgeFile ~= nil,
                 insets and insets[1],
                 insets and insets[2],
                 insets and insets[3],
                 insets and insets[4]
        end
        """
    )(box)

    assert has_backdrop is True
    assert has_border is True
    assert (left, right, top, bottom) == (8, 8, 8, 8)


def test_analyse_export_edit_box_has_visible_height() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box = h.eval("function() return LocalGearAdvisorNS.UI._exportBox end")()

    assert h.method(box, "GetHeight") > 0


def test_check_enables_import_only_for_a_valid_profile() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)

    text = encode_profile_transport(_record())
    h.type_text(box, text)
    h.click(check_button)

    assert h.is_enabled(import_button) is True
    assert _status_text(h) == ""
    preview = h.eval("function() return LocalGearAdvisorNS.UI._importPreview end")()
    assert "Testchar-examplerealm" in h.get_text(preview["identity"])
    assert _db_is_nil(h) is True


def test_invalid_check_disables_import_shows_error_and_never_touches_db() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)

    h.type_text(box, "not a real transport")
    h.click(check_button)

    assert h.is_enabled(import_button) is False
    assert _status_text(h).startswith("Invalid: ")
    assert _db_is_nil(h) is True


def test_check_rejects_a_schema_valid_profile_older_than_the_tooltip_limit() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)
    old = replace(_record(), generated_at=1_785_573_700 - 604_801)

    h.type_text(box, encode_profile_transport(old))
    h.click(check_button)

    assert h.is_enabled(import_button) is False
    assert "older than 7 days" in _status_text(h)
    assert _db_is_nil(h) is True


def test_check_rejects_a_profile_more_than_five_minutes_in_the_future() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)
    future = replace(_record(), generated_at=1_785_573_700 + 301)

    h.type_text(box, encode_profile_transport(future))
    h.click(check_button)

    assert h.is_enabled(import_button) is False
    assert "state cannot be read safely" in _status_text(h)
    assert _db_is_nil(h) is True


def test_editing_text_after_a_valid_check_invalidates_import_again() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)

    text = encode_profile_transport(_record())
    h.type_text(box, text)
    h.click(check_button)
    assert h.is_enabled(import_button) is True

    h.type_text(box, text + " ")

    assert h.is_enabled(import_button) is False


def test_clicking_import_with_stale_checked_text_refuses_and_never_touches_db() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)

    text = encode_profile_transport(_record())
    h.type_text(box, text)
    h.click(check_button)
    assert h.is_enabled(import_button) is True

    h.type_text(box, text + "\n")
    # Even bypassing the (now-disabled) widget state, RunImport's own guard
    # must refuse: it re-checks the box text against what was last Checked.
    h.click(import_button)

    assert _status_text(h) == "Text changed since the last check - please check again."
    assert _db_is_nil(h) is True


def test_successful_import_applies_db_clears_preview_and_refreshes_profile_list() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)

    h.execute(
        """
        RefreshCalls = 0
        local orig = LocalGearAdvisorNS.UI.RefreshProfiles
        LocalGearAdvisorNS.UI.RefreshProfiles = function()
          RefreshCalls = RefreshCalls + 1
          orig()
        end
        """
    )

    text = encode_profile_transport(_record())
    h.type_text(box, text)
    h.click(check_button)
    assert h.is_enabled(import_button) is True

    h.click(import_button)

    assert _status_text(h) == "Profile is active immediately - no reload, no file change."
    assert h.is_enabled(import_button) is False
    preview = h.eval("function() return LocalGearAdvisorNS.UI._importPreview end")()
    assert h.get_text(preview["identity"]) == ""
    assert h.eval("function() return #(LocalGearAdvisorDB.profiles) end")() == 1
    assert h.eval("function() return RefreshCalls end")() >= 1

    profile = h.eval(
        "function() local p = LocalGearAdvisorNS.UI.GetLastCheckedProfile() return p end"
    )()
    assert profile is None

    rows = list(
        h.eval("function() return LocalGearAdvisorNS.UI.EffectiveProfileList() end")().values()
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "db"
    assert rows[0]["characterName"] == "Testchar"


def test_apply_rechecks_age_after_check_before_mutating_saved_variables() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)
    h.type_text(box, encode_profile_transport(_record()))
    h.click(check_button)
    assert h.is_enabled(import_button) is True

    h.execute("time = function() return 1785573700 + 604801 end")
    h.click(import_button)

    assert _status_text(h).startswith("Import failed: ")
    assert "older than 7 days" in _status_text(h)
    assert _db_is_nil(h) is True


def test_apply_rechecks_future_skew_after_check_before_mutating_saved_variables() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    box, check_button, import_button = _import_widgets(h)
    h.type_text(box, encode_profile_transport(_record()))
    h.click(check_button)
    assert h.is_enabled(import_button) is True

    h.execute("time = function() return 1785573299 end")
    h.click(import_button)

    assert _status_text(h).startswith("Import failed: ")
    assert "state cannot be read safely" in _status_text(h)
    assert _db_is_nil(h) is True
