"""Behavioral proof (real Lua 5.1 execution via lupa, generic widget mock)
that the Analyse page never fabricates an export: it calls the exact,
documented SimulationCraft addon method signature --
SimulationcraftAPI:GetSimcProfile(false, false, false, nil) -- and fails
closed with a localized reason whenever that addon is missing, errors, or
returns something other than a non-empty string. Also proves the manual
Ctrl+C workflow (WoW addons cannot write to the OS clipboard): a successful
export selects and focuses the export box and shows the Ctrl+C hint text.
"""

from __future__ import annotations

from _lua_ui_mock import UIHarness

from local_gear_advisor.state import empty_state, render_aggregate_lua


def _harness() -> UIHarness:
    return UIHarness(results_lua=render_aggregate_lua(empty_state()))


def test_run_export_calls_the_documented_simc_addon_method_signature_exactly() -> None:
    h = _harness()
    h.execute(
        """
        CallArgCount = nil
        CallArg1, CallArg2, CallArg3, CallArg4 = nil, nil, nil, nil
        SimulationcraftAPI = {}
        function SimulationcraftAPI.GetSimcProfile(self, ...)
          CallArgCount = select('#', ...)
          CallArg1, CallArg2, CallArg3, CallArg4 = ...
          return 'EXPORT_TEXT_HERE'
        end
        """
    )

    ok, text = h.eval("function() return LocalGearAdvisorNS.UI.RunExport() end")()

    assert ok is True
    assert text == "EXPORT_TEXT_HERE"
    assert h.eval("function() return CallArgCount end")() == 4
    assert h.eval("function() return CallArg1 end")() is False
    assert h.eval("function() return CallArg2 end")() is False
    assert h.eval("function() return CallArg3 end")() is False
    assert h.eval("function() return CallArg4 end")() is None


def test_export_button_click_selects_and_focuses_text_with_ctrl_c_hint() -> None:
    h = _harness()
    h.execute(
        "SimulationcraftAPI = { GetSimcProfile = function(self, ...) "
        "return 'REAL EXPORT TEXT' end }"
    )
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    export_button = h.eval("function() return LocalGearAdvisorNS.UI._exportButton end")()
    export_box = h.eval("function() return LocalGearAdvisorNS.UI._exportBox end")()

    h.click(export_button)

    assert h.get_text(export_box) == "REAL EXPORT TEXT"
    assert h.eval("function(f) return f.highlighted end")(export_box) is True
    assert h.eval("function(f) return f.focused end")(export_box) is True
    status = h.eval("function() return LocalGearAdvisorNS.UI._exportStatus end")()
    assert h.get_text(status) == "Text selected - copy with Ctrl+C."


def test_export_button_click_fails_closed_when_the_simc_addon_is_missing() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    export_button = h.eval("function() return LocalGearAdvisorNS.UI._exportButton end")()
    export_box = h.eval("function() return LocalGearAdvisorNS.UI._exportBox end")()

    h.click(export_button)

    assert h.get_text(export_box) == ""
    status = h.eval("function() return LocalGearAdvisorNS.UI._exportStatus end")()
    assert h.get_text(status) == "SimulationCraft addon not found"


def test_export_button_click_fails_closed_when_the_simc_addon_errors() -> None:
    h = _harness()
    h.execute("SimulationcraftAPI = { GetSimcProfile = function(self, ...) error('boom') end }")
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    export_button = h.eval("function() return LocalGearAdvisorNS.UI._exportButton end")()
    export_box = h.eval("function() return LocalGearAdvisorNS.UI._exportBox end")()

    h.click(export_button)

    assert h.get_text(export_box) == ""
    status = h.eval("function() return LocalGearAdvisorNS.UI._exportStatus end")()
    assert h.get_text(status) == "SimulationCraft export failed"


def test_export_button_click_fails_closed_on_empty_or_non_string_export_text() -> None:
    for bad_return in ("''", "nil", "123"):
        h = _harness()
        h.execute(
            "SimulationcraftAPI = { GetSimcProfile = function(self, ...) "
            f"return {bad_return} end }}"
        )
        h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
        export_button = h.eval("function() return LocalGearAdvisorNS.UI._exportButton end")()
        export_box = h.eval("function() return LocalGearAdvisorNS.UI._exportBox end")()

        h.click(export_button)

        assert h.get_text(export_box) == "", bad_return
        status = h.eval("function() return LocalGearAdvisorNS.UI._exportStatus end")()
        assert h.get_text(status) == "SimulationCraft export failed", bad_return


def test_refresh_analyse_shows_addon_ready_and_missing_pill_states() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    pill = h.eval("function() return LocalGearAdvisorNS.UI._exportPill end")()

    h.eval("function() LocalGearAdvisorNS.UI.RefreshAnalyse() end")()
    assert h.get_text(pill) == "SimulationCraft addon not found"

    h.execute("SimulationcraftAPI = { GetSimcProfile = function() return 'x' end }")
    h.eval("function() LocalGearAdvisorNS.UI.RefreshAnalyse() end")()
    assert h.get_text(pill) == "SimulationCraft addon ready"


def test_character_pill_shows_name_and_specialization_when_available() -> None:
    h = _harness()
    h.execute(
        """
        function UnitName(unit) return 'Testchar' end
        C_SpecializationInfo = {
          GetSpecialization = function() return 1 end,
          GetSpecializationInfo = function(i) return 262, 'Elemental' end,
        }
        """
    )
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    h.eval("function() LocalGearAdvisorNS.UI.RefreshAnalyse() end")()
    pill = h.eval("function() return LocalGearAdvisorNS.UI._characterPill end")()
    assert h.get_text(pill) == "Testchar - Elemental"


def test_character_pill_is_blank_when_no_player_identity_is_available() -> None:
    h = _harness()
    h.eval("function() return LocalGearAdvisorNS.UI.CreateRoot() end")()
    h.eval("function() LocalGearAdvisorNS.UI.RefreshAnalyse() end")()
    pill = h.eval("function() return LocalGearAdvisorNS.UI._characterPill end")()
    assert h.get_text(pill) == ""
