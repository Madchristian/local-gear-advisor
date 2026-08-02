"""Behavioral proof (real Lua 5.1 execution via lupa, generic widget mock)
that the Settings page's window scale, window position, and minimap-button
visibility are all written into LocalGearAdvisorSettings (the addon's real
SavedVariable for session/UI preferences) and are correctly re-applied on a
fresh CreateRoot()/Minimap.Create() -- i.e. they survive a simulated
reload/relog, not just the current session's in-memory widgets.
"""

from __future__ import annotations

import pytest
from _lua_ui_mock import UIHarness

from local_gear_advisor.state import empty_state, render_aggregate_lua


def _harness() -> UIHarness:
    return UIHarness(results_lua=render_aggregate_lua(empty_state()))


def test_apply_scale_sets_root_scale_and_persists_the_preset_percent() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    button130 = h.eval("function() return LocalGearAdvisorNS.UI._scaleButtons[130] end")()

    h.click(button130)

    root = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert h.method(root, "GetScale") == pytest.approx(1.30)
    frame_scale = h.eval("function() return LocalGearAdvisorSettings.frameScale end")()
    assert frame_scale == 130


def test_apply_scale_rejects_a_percent_outside_the_presets() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()

    ok = h.eval("function() return LocalGearAdvisorNS.UI.ApplyScale(999) end")()

    assert ok is False
    frame_scale = h.eval("function() return LocalGearAdvisorSettings.frameScale end")()
    assert frame_scale is None


def test_scale_preset_is_restored_after_a_simulated_reload() -> None:
    h1 = _harness()
    h1.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    button130 = h1.eval("function() return LocalGearAdvisorNS.UI._scaleButtons[130] end")()
    h1.click(button130)
    frame_scale = h1.eval("function() return LocalGearAdvisorSettings.frameScale end")()

    h2 = _harness()
    h2.execute(f"LocalGearAdvisorSettings = {{ frameScale = {frame_scale} }}")
    h2.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()

    root2 = h2.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert h2.method(root2, "GetScale") == pytest.approx(1.30)


def test_reset_position_clears_saved_point_and_recenters_the_frame() -> None:
    h = _harness()
    h.execute(
        "LocalGearAdvisorSettings = { point = "
        "{ point = 'TOPLEFT', relPoint = 'TOPLEFT', x = 12, y = -34 } }"
    )
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    root = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    point, _relTo, _relPoint, x, y = h.method(root, "GetPoint", 1)
    assert (point, x, y) == ("TOPLEFT", 12, -34)

    reset_button = h.eval("function() return LocalGearAdvisorNS.UI._resetPositionButton end")()
    h.click(reset_button)

    assert h.eval("function() return LocalGearAdvisorSettings.point end")() is None
    point2, _relTo2, _relPoint2, _x2, _y2 = h.method(root, "GetPoint", 1)
    assert point2 == "CENTER"
    status = h.eval("function() return LocalGearAdvisorNS.UI._settingsStatus end")()
    assert h.get_text(status) == "Window position reset."


def test_reset_position_is_honored_after_a_simulated_reload() -> None:
    h1 = _harness()
    h1.execute(
        "LocalGearAdvisorSettings = { point = "
        "{ point = 'TOPLEFT', relPoint = 'TOPLEFT', x = 12, y = -34 } }"
    )
    h1.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    reset_button = h1.eval("function() return LocalGearAdvisorNS.UI._resetPositionButton end")()
    h1.click(reset_button)

    h2 = _harness()
    h2.execute("LocalGearAdvisorSettings = { point = nil }")
    h2.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    root2 = h2.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    point, *_rest = h2.method(root2, "GetPoint", 1)
    assert point == "CENTER"


def test_minimap_button_click_toggles_visibility_and_updates_the_label() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    h.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    h.eval("function() LocalGearAdvisorNS.UI.RefreshMinimapButtonLabel() end")()
    label = h.eval("function() return LocalGearAdvisorNS.UI._minimapButtonLabel end")()
    assert h.get_text(label) == "Hide minimap button"

    button = h.eval("function() return LocalGearAdvisorNS.UI._minimapButton end")()
    h.click(button)

    assert h.get_text(label) == "Show minimap button"
    assert h.eval("function() return LocalGearAdvisorNS.Minimap.IsShown() end")() is False
    minimap_button = h.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()
    assert h.is_shown(minimap_button) is False

    h.click(button)

    assert h.get_text(label) == "Hide minimap button"
    assert h.eval("function() return LocalGearAdvisorNS.Minimap.IsShown() end")() is True


def test_minimap_visibility_persists_and_is_honored_after_a_simulated_reload() -> None:
    h1 = _harness()
    h1.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    h1.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    h1.eval("function() LocalGearAdvisorNS.UI.RefreshMinimapButtonLabel() end")()
    minimap_button = h1.eval("function() return LocalGearAdvisorNS.UI._minimapButton end")()
    h1.click(minimap_button)
    shown_flag = h1.eval("function() return LocalGearAdvisorSettings.minimapShown end")()
    assert shown_flag is False

    h2 = _harness()
    h2.execute(f"LocalGearAdvisorSettings = {{ minimapShown = {str(shown_flag).lower()} }}")
    h2.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    button2 = h2.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()
    assert h2.is_shown(button2) is False
