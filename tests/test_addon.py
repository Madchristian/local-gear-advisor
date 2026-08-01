from pathlib import Path

from luaparser import ast

ADDON = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"


def test_addon_lua_files_parse() -> None:
    for path in ADDON.glob("*.lua"):
        ast.parse(path.read_text(encoding="utf-8"))


def test_results_load_before_tooltip_core() -> None:
    toc = (ADDON / "LocalGearAdvisor.toc").read_text(encoding="utf-8")
    assert toc.index("Results.lua") < toc.index("Core.lua")


def test_tooltip_is_exact_match_and_fails_closed_on_stale_state() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "local getItem = tooltip.GetItem" in core
    assert "pcall(getItem, tooltip)" in core
    assert "results.items[options]" in core
    assert "C_Traits.GenerateImportString" in core
    assert "results.baselineGear" in core
    assert "issecretvalue" in core
    assert "if not valid then" in core
    assert 'HookScript("OnTooltipCleared"' in core
    assert "Result is stale" in core
    assert '"suffix=" .. suffixID' in core
    assert "redirected_base_stats" not in core
    assert "MAX_RESULT_AGE" in core
    assert "if not validityDirty then" not in core
    assert 'RegisterEvent("PLAYER_LEVEL_UP")' in core
    assert "IsFiniteNumber(results.generatedAt)" in core
    assert "IsFiniteNumber(result.iterations)" in core
    assert "local specAPI = C_SpecializationInfo" in core
    assert "specAPI.GetSpecialization()" in core
    assert "local trackedTooltips = setmetatable" in core
    assert "for tooltip in pairs(trackedTooltips)" in core
    assert "tooltip:Hide()" in core
    assert "results.gameVersion" in core
    assert "IsNonEmptyString(results.profileHash)" in core
    assert "IsNonEmptyString(results.simcVersion)" in core
    assert "IsNonEmptyString(results.simcRevision)" in core
    assert "IsNonEmptyString(results.fightStyle)" in core
    assert 'type(results.traitSystems.omnium_talents) ~= "string"' in core
    assert "local expectedOmnium = results.traitSystems.omnium_talents" in core
    assert 'results.dbcSource ~= "Live"' in core
    assert "BASELINE_SLOTS" in core
    toc = (ADDON / "LocalGearAdvisor.toc").read_text(encoding="utf-8")
    assert "## Interface: 120007" in toc
    assert "120005" not in toc and "120100" not in toc
