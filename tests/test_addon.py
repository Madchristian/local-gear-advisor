from pathlib import Path

from luaparser import ast

ADDON = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"


def test_addon_lua_files_parse() -> None:
    for path in ADDON.glob("*.lua"):
        ast.parse(path.read_text(encoding="utf-8"))


def test_results_load_before_tooltip_core() -> None:
    toc = (ADDON / "LocalGearAdvisor.toc").read_text(encoding="utf-8")
    assert toc.index("Results.lua") < toc.index("Localization.lua")
    assert toc.index("Localization.lua") < toc.index("Core.lua")
    assert toc.index("Sha256.lua") < toc.index("Import.lua")
    assert toc.index("Core.lua") < toc.index("Import.lua")


def test_results_placeholder_is_a_valid_empty_v2_aggregate() -> None:
    results = (ADDON / "Results.lua").read_text(encoding="utf-8")
    assert "schemaVersion = 2" in results
    assert "profiles = {}" in results
    ast.parse(results)


def test_tooltip_is_exact_match_and_fails_closed_on_stale_state() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "local getItem = tooltip.GetItem" in core
    assert "pcall(getItem, tooltip)" in core
    assert "profile.items[options]" in core
    assert "C_Traits.GenerateImportString" in core
    assert "profile.baselineGear" in core
    assert "issecretvalue" in core
    assert "if not valid then" in core
    assert 'HookScript("OnTooltipCleared"' in core
    assert '"suffix=" .. suffixID' in core
    assert "redirected_base_stats" not in core
    assert "MAX_RESULT_AGE" in core
    assert "if not validityDirty then" not in core
    assert 'RegisterEvent("PLAYER_LEVEL_UP")' in core
    assert "IsFiniteNumber(profile.generatedAt)" in core
    assert "IsFiniteNumber(result.iterations)" in core
    assert "local specAPI = C_SpecializationInfo" in core
    assert "specAPI.GetSpecialization()" in core
    assert "local trackedTooltips = setmetatable" in core
    assert "for tooltip in pairs(trackedTooltips)" in core
    assert "tooltip:Hide()" in core
    assert "profile.gameVersion" in core
    assert "IsNonEmptyString(profile.profileHash)" in core
    assert "IsNonEmptyString(profile.simcVersion)" in core
    assert "IsNonEmptyString(profile.simcRevision)" in core
    assert "IsNonEmptyString(profile.fightStyle)" in core
    assert 'type(profile.traitSystems.omnium_talents) ~= "string"' in core
    assert "local expectedOmnium = profile.traitSystems.omnium_talents" in core
    assert 'profile.dbcSource ~= "Live"' in core
    assert "BASELINE_SLOTS" in core
    assert "tooltip:AddLine(L.dpsOnly" in core
    localization = (ADDON / "Localization.lua").read_text(encoding="utf-8")
    assert 'stale = "Result is stale"' in localization
    assert 'dpsOnly = "Nur offensiver DPS-Vergleich"' in localization
    assert 'dpsOnly = "Offensive DPS comparison only"' in localization
    assert 'upgrade = "DPS-Upgrade"' in localization
    assert 'upgrade = "DPS upgrade"' in localization
    assert 'downgrade = "DPS-Downgrade"' in localization
    assert 'downgrade = "DPS downgrade"' in localization
    assert 'equal = "DPS ungefähr gleich"' in localization
    assert 'equal = "DPS approximately equal"' in localization
    toc = (ADDON / "LocalGearAdvisor.toc").read_text(encoding="utf-8")
    assert "## Interface: 120007" in toc
    assert "120005" not in toc and "120100" not in toc


def test_schema_v2_multi_profile_aggregate_and_exact_selection() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "results.schemaVersion ~= 2" in core
    assert 'type(results.profiles) ~= "table"' in core
    assert "for _, profile in ipairs(results.profiles) do" in core
    assert "IsValidProfileShape(profile)" in core


def test_duplicate_and_malformed_profiles_fail_the_whole_aggregate_closed() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "if seenIdentity[identityKey] then return nil end" in core
    assert "if not IsValidProfileShape(profile) then return nil end" in core


def test_selection_is_exact_on_region_realm_name_specid() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "local function FindCurrentProfile(profiles, identity)" in core
    assert "string.lower(profile.region) == identity.region" in core
    assert "string.lower(profile.server) == identity.realm" in core
    assert "string.lower(profile.characterName) == identity.name" in core
    assert "profile.specID == identity.specID" in core


def test_name_matching_is_case_insensitive_like_wow_character_uniqueness() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "name = string.lower(name)," in core
    assert 'string.lower(profile.characterName) .. "\\30" .. profile.specID' in core


def test_profiles_array_rejects_holes_and_non_dense_keys() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "local function TableLength(value)" in core
    assert "if arrayCount ~= TableLength(results.profiles) then" in core


def test_no_match_and_no_data_are_silent_not_leaked() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "if not matched then\n    return nil, false, L.noProfile\n  end" in core
    assert 'if not profile or type(profile.items) ~= "table" then return end' in core
