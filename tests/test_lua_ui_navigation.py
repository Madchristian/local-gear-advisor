"""Behavioral proof (real Lua 5.1 execution via lupa, generic widget mock)
that UI.lua's navigation, header, and ESC/toggle contracts actually behave
as specified -- not just that the source text contains certain strings.
Every assertion here drives the addon's real OnClick/OnShow/OnHide handlers
through the mock widget system in _lua_ui_mock.py.
"""

from __future__ import annotations

from _lua_ui_mock import UIHarness

from local_gear_advisor.state import empty_state, render_aggregate_lua


def _harness() -> UIHarness:
    return UIHarness(results_lua=render_aggregate_lua(empty_state()))


def _sidebar_entries(h: UIHarness):
    table = h.eval("function() return LocalGearAdvisorNS.UI._sidebarButtons end")()
    return {entry["key"]: entry for entry in table.values()}


def test_toggle_creates_and_shows_the_root_frame_sized_to_the_mockup_geometry() -> None:
    h = _harness()
    h.eval("function() LocalGearAdvisorNS.UI.Toggle() end")()

    frame = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert h.is_shown(frame) is True
    assert (frame.width, frame.height) == (1154, 600)


def test_toggle_twice_hides_the_frame_again() -> None:
    h = _harness()
    h.eval("function() LocalGearAdvisorNS.UI.Toggle() end")()
    h.eval("function() LocalGearAdvisorNS.UI.Toggle() end")()

    frame = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert h.is_shown(frame) is False


def test_default_page_on_first_show_is_analyse() -> None:
    h = _harness()
    h.eval("function() LocalGearAdvisorNS.UI.CreateRoot() end")()

    assert h.eval("function() return LocalGearAdvisorNS.UI.GetCurrentPage() end")() == "analyse"


def test_clicking_each_nav_button_switches_the_active_page_and_header_text() -> None:
    h = _harness()
    h.eval("function() LocalGearAdvisorNS.UI.CreateRoot() end")()
    entries = _sidebar_entries(h)

    expected_titles = {
        "analyse": "Analysis",
        "import": "Import",
        "profiles": "Profiles",
        "settings": "Settings",
    }
    header_title = h.eval("function() return LocalGearAdvisorNS.UI._headerTitle end")()
    header_desc = h.eval("function() return LocalGearAdvisorNS.UI._headerDesc end")()
    for key, entry in entries.items():
        h.click(entry["button"])
        assert h.eval("function() return LocalGearAdvisorNS.UI.GetCurrentPage() end")() == key
        meta = h.eval("function(k) return LocalGearAdvisorNS.UI.PageMeta()[k] end")(key)
        assert meta["title"] == expected_titles[key]
        assert h.get_text(header_title) == expected_titles[key]
        assert h.get_text(header_desc) == meta["desc"]


def test_only_the_active_pages_frame_is_shown() -> None:
    h = _harness()
    h.eval("function() LocalGearAdvisorNS.UI.CreateRoot() end")()
    entries = _sidebar_entries(h)
    h.click(entries["profiles"]["button"])

    pages = h.eval("function() return LocalGearAdvisorNS.UI._pages end")()
    for key, frame in pages.items():
        assert h.is_shown(frame) == (key == "profiles")

    for key, entry in entries.items():
        assert h.is_shown(entry["indicator"]) == (key == "profiles")


def test_esc_registration_is_idempotent_across_many_toggles() -> None:
    h = _harness()
    for _ in range(6):
        h.eval("function() LocalGearAdvisorNS.UI.Toggle() end")()

    esc_frames = list(h.eval("function() return UISpecialFrames end")().values())
    assert esc_frames.count("LocalGearAdvisorFrame") == 1


def test_create_root_is_idempotent_and_returns_the_same_frame() -> None:
    h = _harness()
    first = h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    second = h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()

    assert h.eval("function(a, b) return a == b end")(first, second) is True


def test_close_button_hides_the_frame() -> None:
    h = _harness()
    h.eval("function() LocalGearAdvisorNS.UI.Show() end")()
    close_button = h.eval("function() return LocalGearAdvisorNS.UI._closeButton end")()

    h.click(close_button)

    frame = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert h.is_shown(frame) is False


def test_slash_command_toggles_the_frame() -> None:
    h = _harness()
    handler = h.eval("function() return SlashCmdList['LOCALGEARADVISOR'] end")()
    assert handler is not None

    handler("")
    frame = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert h.is_shown(frame) is True

    handler("")
    assert h.is_shown(frame) is False


def test_slash_command_is_registered_as_lga() -> None:
    h = _harness()
    assert h.eval("function() return SLASH_LOCALGEARADVISOR1 end")() == "/lga"


def test_addon_compartment_click_toggles_and_never_raises() -> None:
    h = _harness()
    ok = h.eval(
        "function() return pcall(LocalGearAdvisor_OnAddonCompartmentClick, "
        "'LocalGearAdvisor', 'btn') end"
    )()
    assert ok is True
    frame = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert h.is_shown(frame) is True


def test_addon_compartment_click_never_raises_even_when_toggle_errors() -> None:
    h = _harness()
    h.execute(
        """
        ErrorHandlerCalls = {}
        geterrorhandler = function()
          return function(msg) table.insert(ErrorHandlerCalls, msg) end
        end
        LocalGearAdvisorNS.UI.Toggle = function() error('boom') end
        """
    )

    ok = h.eval(
        "function() return pcall(LocalGearAdvisor_OnAddonCompartmentClick, "
        "'LocalGearAdvisor', 'btn') end"
    )()

    assert ok is True
    calls = list(h.eval("function() return ErrorHandlerCalls end")().values())
    assert len(calls) == 1
    assert "addon compartment click failed" in calls[0]
    assert "boom" in calls[0]


def test_locale_other_than_dede_falls_back_to_enus_page_titles() -> None:
    h = UIHarness(results_lua=render_aggregate_lua(empty_state()), locale="frFR")
    meta = h.eval("function() return LocalGearAdvisorNS.UI.PageMeta().analyse end")()
    assert meta["title"] == "Analysis"


def test_dede_locale_produces_german_page_titles() -> None:
    h = UIHarness(results_lua=render_aggregate_lua(empty_state()), locale="deDE")
    meta = h.eval("function() return LocalGearAdvisorNS.UI.PageMeta().analyse end")()
    assert meta["title"] == "Analyse"
