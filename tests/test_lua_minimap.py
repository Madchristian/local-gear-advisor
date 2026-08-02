"""Behavioral proof (real Lua 5.1 execution via lupa) of Minimap.lua's
geometry, dragging, click, and tooltip contracts: angle/position math,
a radius that tracks the real minimap's current width (falling back safely
when that width is unusable), a pure-Lua atan2 fallback for hosts without
math.atan2 (WoW's Lua 5.1 always has one; this only proves the fallback
formula itself is correct), GetEffectiveScale-aware cursor-to-angle
conversion, the icon's real minimap mask, and that position only ever
updates from the OnUpdate handler while actually dragging.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from _lua_ui_mock import UIHarness
from lupa.lua51 import LuaRuntime

from local_gear_advisor.state import empty_state, render_aggregate_lua

_ADDON_DIR = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"
LOCALIZATION_SOURCE = (_ADDON_DIR / "Localization.lua").read_text(encoding="utf-8")
MINIMAP_SOURCE = (_ADDON_DIR / "Minimap.lua").read_text(encoding="utf-8")


def _harness() -> UIHarness:
    return UIHarness(results_lua=render_aggregate_lua(empty_state()))


# ---------------------------------------------------------------------------
# Pure geometry: Position / AngleFromXY


def test_position_places_angle_zero_due_east_of_center() -> None:
    h = _harness()
    x, y = h.eval("function() return LocalGearAdvisorNS.Minimap.Position(0, 100) end")()
    assert x == pytest.approx(100.0)
    assert y == pytest.approx(0.0)


def test_position_and_angle_from_xy_are_inverses_across_all_quadrants() -> None:
    h = _harness()
    position = h.eval("function(a, r) return LocalGearAdvisorNS.Minimap.Position(a, r) end")
    angle_from_xy = h.eval(
        "function(dx, dy) return LocalGearAdvisorNS.Minimap.AngleFromXY(dx, dy) end"
    )
    for angle in (0, 45, 90, 135, 180, 225, 270, 315):
        dx, dy = position(angle, 82.5)
        recovered = angle_from_xy(dx, dy)
        assert recovered == pytest.approx(angle, abs=1e-6)


def test_angle_from_xy_of_the_origin_is_zero() -> None:
    h = _harness()
    angle = h.eval("function() return LocalGearAdvisorNS.Minimap.AngleFromXY(0, 0) end")()
    assert angle == 0


# ---------------------------------------------------------------------------
# Dynamic radius: tracks the real minimap's current width


def test_current_radius_tracks_the_minimaps_width() -> None:
    h = _harness()
    h.set_minimap_width(140)
    assert h.eval(
        "function() return LocalGearAdvisorNS.Minimap.CurrentRadius() end"
    )() == pytest.approx(140 / 2 + 12.5)

    h.set_minimap_width(200)
    assert h.eval(
        "function() return LocalGearAdvisorNS.Minimap.CurrentRadius() end"
    )() == pytest.approx(200 / 2 + 12.5)


def test_current_radius_falls_back_to_the_default_when_width_is_unusable() -> None:
    h = _harness()
    h.set_minimap_width(0)
    assert h.eval(
        "function() return LocalGearAdvisorNS.Minimap.CurrentRadius() end"
    )() == pytest.approx(80 + 12.5)


# ---------------------------------------------------------------------------
# atan2 fallback (WoW's Lua 5.1 always ships math.atan2; this only proves the
# pure-Lua fallback formula matches real atan2 semantics, for the
# hypothetical host that lacks it).


def _fallback_runtime() -> LuaRuntime:
    rt = LuaRuntime(unpack_returned_tuples=True)
    rt.globals().GetLocale = lambda: "enUS"
    rt.execute("math.atan2 = nil")
    rt.execute(LOCALIZATION_SOURCE)
    rt.execute(MINIMAP_SOURCE)
    return rt


def test_atan2_fallback_is_used_when_math_atan2_is_unavailable() -> None:
    rt = _fallback_runtime()
    is_real = rt.eval("function() return LocalGearAdvisorNS.Minimap.Atan2 == nil end")()
    assert is_real is False


@pytest.mark.parametrize(
    "y,x",
    [
        (1, 1),
        (1, -1),
        (-1, -1),
        (-1, 1),
        (5, 0),
        (-5, 0),
        (0, 5),
        (0, -5),
        (0, 0),
        (3.7, 2.1),
        (-3.7, 2.1),
    ],
)
def test_atan2_fallback_matches_real_atan2_across_quadrants(y: float, x: float) -> None:
    rt = _fallback_runtime()
    fallback = rt.eval("function(y, x) return LocalGearAdvisorNS.Minimap.Atan2(y, x) end")
    assert fallback(y, x) == pytest.approx(math.atan2(y, x), abs=1e-9)


# ---------------------------------------------------------------------------
# GetEffectiveScale-aware drag math


def test_drag_update_divides_cursor_position_by_the_buttons_effective_scale() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    button = h.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()
    h.set_minimap_center(400, 300)

    h.execute("LocalGearAdvisorNS.Minimap.GetButton().effectiveScale = 2")
    # mx/scale - cx = 10, my/scale - cy = 0  =>  angle 0 degrees
    h.set_cursor(820, 600)
    h.drag_start(button)
    h.drag_update(button)

    assert h.eval("function() return LocalGearAdvisorNS.Minimap.GetAngle() end")() == pytest.approx(
        0.0
    )


def test_drag_update_treats_a_zero_or_non_numeric_effective_scale_as_one() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    button = h.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()
    h.set_minimap_center(400, 300)
    h.execute("LocalGearAdvisorNS.Minimap.GetButton().effectiveScale = 0")

    # With scale treated as 1: mx - cx = 10, my - cy = 0 => angle 0 degrees.
    h.set_cursor(410, 300)
    h.drag_start(button)
    h.drag_update(button)

    assert h.eval("function() return LocalGearAdvisorNS.Minimap.GetAngle() end")() == pytest.approx(
        0.0
    )


# ---------------------------------------------------------------------------
# OnUpdate-only drag semantics


def test_position_only_updates_from_onupdate_while_dragging() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    button = h.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()
    h.set_minimap_center(400, 300)
    starting_angle = h.eval("function() return LocalGearAdvisorNS.Minimap.GetAngle() end")()

    # No drag_start: OnUpdate handler must not even be registered yet.
    h.set_cursor(1000, 1000)
    h.drag_update(button)
    assert h.eval("function() return LocalGearAdvisorNS.Minimap.GetAngle() end")() == starting_angle

    h.drag_start(button)
    h.set_cursor(400, 220)  # due "north" of center (dx=0, dy=-80 => 270 degrees)
    h.drag_update(button)
    dragging_angle = h.eval("function() return LocalGearAdvisorNS.Minimap.GetAngle() end")()
    assert dragging_angle == pytest.approx(270.0)

    h.drag_stop(button)
    # After stopping, the OnUpdate handler must be cleared: further cursor
    # movement (even if MOCK.DragUpdate is called again) must not move it.
    h.set_cursor(500, 500)
    h.drag_update(button)
    assert h.eval("function() return LocalGearAdvisorNS.Minimap.GetAngle() end")() == pytest.approx(
        dragging_angle
    )


# ---------------------------------------------------------------------------
# Icon mask / textures


def test_create_applies_the_minimap_ring_mask_to_the_icon() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    button = h.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()

    assert button.icon.mask == "Interface\\Minimap\\UI-Minimap-Background"
    assert button.icon.texturePath == "Interface\\Icons\\INV_Misc_Gear_01"
    assert button.border.texturePath == "Interface\\Minimap\\MiniMap-TrackingBorder"


# ---------------------------------------------------------------------------
# Click and tooltip


def test_left_click_toggles_the_main_ui() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    button = h.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()

    h.click(button, "LeftButton")

    root = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert h.is_shown(root) is True


def test_right_click_does_not_toggle_the_main_ui() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    button = h.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()

    h.click(button, "RightButton")

    root = h.eval("function() return LocalGearAdvisorNS.UI.GetRootFrame() end")()
    assert root is None


def test_enter_shows_tooltip_title_and_hint_and_leave_hides_it() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.Minimap.Create() end")()
    button = h.eval("function() return LocalGearAdvisorNS.Minimap.GetButton() end")()
    h.execute(
        "HideCalls = 0\n"
        "local orig = GameTooltip.Hide\n"
        "GameTooltip.Hide = function(...) HideCalls = HideCalls + 1 end"
    )

    h.enter(button)

    tooltip = h.eval("function() return GameTooltip end")()
    lines = list(tooltip.lines.values())
    assert "Local Gear Advisor" in lines
    assert "Click to open/close" in lines

    h.leave(button)
    assert h.eval("function() return HideCalls end")() == 1
