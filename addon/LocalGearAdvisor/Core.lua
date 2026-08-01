local ADDON_NAME = ...

local L = GetLocale() == "deDE" and {
  title = "Lokale Ausrüstungsanalyse",
  upgrade = "Upgrade",
  downgrade = "Downgrade",
  equal = "Ungefähr gleich",
  stale = "Ergebnis veraltet",
  noProfile = "Keine gültigen Simulationsdaten",
  character = "anderer Charakter",
  classSpec = "andere Spezialisierung",
  identity = "Stufe oder Volk geändert",
  gameBuild = "andere WoW-/SimC-Datenversion",
  talents = "Talente geändert",
  traits = "Omnium-Talente geändert",
  gear = "Ausrüstung geändert",
  expired = "Simulation älter als 7 Tage",
  unknown = "Zustand nicht sicher lesbar",
  slot = "Beste Position",
  iterations = "Iterationen",
  scenario = "Szenario",
  age = "Alter",
  simc = "SimC",
} or {
  title = "Local gear analysis",
  upgrade = "Upgrade",
  downgrade = "Downgrade",
  equal = "Approximately equal",
  stale = "Result is stale",
  noProfile = "No valid simulation data",
  character = "different character",
  classSpec = "different specialization",
  identity = "level or race changed",
  gameBuild = "different WoW/SimC data version",
  talents = "talents changed",
  traits = "Omnium talents changed",
  gear = "equipment changed",
  expired = "simulation is older than 7 days",
  unknown = "state cannot be read safely",
  slot = "Best slot",
  iterations = "Iterations",
  scenario = "Scenario",
  age = "Age",
  simc = "SimC",
}

local SLOT_LABELS = GetLocale() == "deDE" and {
  finger1 = "Ring 1", finger2 = "Ring 2",
  trinket1 = "Schmuck 1", trinket2 = "Schmuck 2",
  main_hand = "Waffenhand", off_hand = "Schildhand",
} or {
  finger1 = "Ring 1", finger2 = "Ring 2",
  trinket1 = "Trinket 1", trinket2 = "Trinket 2",
  main_hand = "Main hand", off_hand = "Off hand",
}

local SLOT_IDS = {
  head = 1, neck = 2, shoulder = 3, shirt = 4, chest = 5, waist = 6,
  legs = 7, feet = 8, wrist = 9, hands = 10, finger1 = 11, finger2 = 12,
  trinket1 = 13, trinket2 = 14, back = 15, main_hand = 16, off_hand = 17,
  tabard = 19,
}
local BASELINE_SLOTS = {
  "head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist",
  "legs", "feet", "finger1", "finger2", "trinket1", "trinket2", "main_hand", "off_hand",
}

local function IsSecret(value)
  return issecretvalue and issecretvalue(value)
end

local function IsFiniteNumber(value)
  return not IsSecret(value)
      and type(value) == "number"
      and value == value
      and value > -math.huge
      and value < math.huge
end

local function IsNonEmptyString(value)
  return not IsSecret(value)
      and type(value) == "string"
      and value:find("%S") ~= nil
end

local function Tokenize(value)
  if type(value) ~= "string" or IsSecret(value) then return nil end
  value = string.lower(value):gsub(" ", "_")
  value = value:gsub("[^%w%%+%._\128-\255]", "")
  return value:gsub("_+$", "")
end

local REGION_NAMES = { [1] = "us", [2] = "kr", [3] = "eu", [4] = "tw", [5] = "cn" }
local MAX_RESULT_AGE = 7 * 24 * 60 * 60

local function RaceToken(value)
  local token = Tokenize(value)
  return token and token:gsub("_", "") or nil
end

local function AgeText(seconds)
  if seconds < 3600 then return string.format("%d min", math.floor(seconds / 60)) end
  if seconds < 86400 then return string.format("%.1f h", seconds / 3600) end
  return string.format("%.1f d", seconds / 86400)
end

local function SafeNumber(value)
  if IsSecret(value) then return nil end
  return tonumber(value)
end

local function SplitItemLink(itemLink)
  if type(itemLink) ~= "string" or IsSecret(itemLink) then return nil end
  local itemString = string.match(itemLink, "item:([%-?%d:]+)")
  if not itemString then return nil end
  local values = {}
  for _, value in ipairs({strsplit(":", itemString)}) do
    if value == "" then
      values[#values + 1] = 0
    else
      local number = SafeNumber(value)
      if number == nil then return nil end
      values[#values + 1] = number
    end
  end
  return values
end

-- Kept in the same order as the public-domain SimulationCraft addon serializer.
local function ItemOptions(itemLink)
  local item = SplitItemLink(itemLink)
  if not item then return nil end
  local itemID = item[1]
  local enchantID = item[2] or 0
  local bonusCount = item[13]
  if not itemID or itemID <= 0 or not bonusCount or bonusCount < 0 then return nil end

  local options = {",id=" .. itemID}
  if enchantID > 0 then options[#options + 1] = "enchant_id=" .. enchantID end

  local gems = {}
  for offset = 3, 6 do gems[#gems + 1] = item[offset] or 0 end
  while #gems > 0 and gems[#gems] == 0 do table.remove(gems) end
  if #gems > 0 then options[#options + 1] = "gem_id=" .. table.concat(gems, "/") end

  local suffixID = item[7] or 0
  if suffixID ~= 0 then options[#options + 1] = "suffix=" .. suffixID end

  local bonuses = {}
  for index = 1, bonusCount do
    local value = item[13 + index]
    if value == nil then return nil end
    bonuses[#bonuses + 1] = value
  end
  if #bonuses > 0 then options[#options + 1] = "bonus_id=" .. table.concat(bonuses, "/") end

  local linkOffset = 14 + bonusCount
  local pairCount = item[linkOffset]
  if pairCount == nil or pairCount < 0 then return nil end
  local craftedStats = {}
  for index = 1, pairCount do
    local pairOffset = 1 + linkOffset + (2 * (index - 1))
    local pairType, pairValue = item[pairOffset], item[pairOffset + 1]
    if pairType == nil or pairValue == nil then return nil end
    if pairType == 9 then
      options[#options + 1] = "drop_level=" .. pairValue
    elseif pairType == 28 then
      options[#options + 1] = "content_tuning=" .. pairValue
    elseif pairType == 29 or pairType == 30 then
      craftedStats[#craftedStats + 1] = pairValue
    end
  end
  if #craftedStats > 0 then
    options[#options + 1] = "crafted_stats=" .. table.concat(craftedStats, "/")
  end

  local gemBonusOffset = linkOffset + (2 * pairCount) + 2
  local gemBonusCount = item[gemBonusOffset]
  if gemBonusCount == nil or gemBonusCount < 0 then return nil end
  local gemBonuses = {}
  for index = 1, gemBonusCount do
    local value = item[gemBonusOffset + index]
    if value == nil then return nil end
    gemBonuses[#gemBonuses + 1] = value
  end
  if #gemBonuses > 0 then
    options[#options + 1] = "gem_bonus_id=" .. table.concat(gemBonuses, "/")
  end

  if C_TradeSkillUI and C_TradeSkillUI.GetItemCraftedQualityByItemInfo then
    local ok, quality = pcall(C_TradeSkillUI.GetItemCraftedQualityByItemInfo, itemLink)
    if not ok or IsSecret(quality) then return nil end
    if quality then options[#options + 1] = "crafting_quality=" .. quality end
  end

  -- These legacy belts require tooltip spell parsing; never match them approximately.
  if itemID == 242664 or itemID == 245964 or itemID == 245965 or itemID == 245966 then
    return nil
  end
  return table.concat(options, ",")
end

local function CurrentTraitString(systemID)
  if not C_Traits or not C_Traits.GetConfigIDBySystemID then return nil end
  local configID = C_Traits.GetConfigIDBySystemID(systemID)
  if IsSecret(configID) or not configID then return nil end
  local config = C_Traits.GetConfigInfo(configID)
  if IsSecret(config) or type(config) ~= "table" then return nil end
  local treeIDs = config.treeIDs
  if IsSecret(treeIDs) or type(treeIDs) ~= "table" then return nil end
  local entries = {}
  for _, treeID in ipairs(treeIDs) do
    if IsSecret(treeID) then return nil end
    local nodes = C_Traits.GetTreeNodes(treeID)
    if IsSecret(nodes) or type(nodes) ~= "table" then return nil end
    for _, nodeID in ipairs(nodes) do
      if IsSecret(nodeID) then return nil end
      local node = C_Traits.GetNodeInfo(configID, nodeID)
      if IsSecret(node) then return nil end
      if node then
        local ranksPurchased, activeEntry = node.ranksPurchased, node.activeEntry
        if IsSecret(ranksPurchased) or IsSecret(activeEntry) then return nil end
        if ranksPurchased and ranksPurchased > 0 and activeEntry then
          local entryID, rank = activeEntry.entryID, activeEntry.rank
          if IsSecret(entryID) or IsSecret(rank) then return nil end
          if type(entryID) ~= "number" or type(rank) ~= "number" then return nil end
          entries[#entries + 1] = entryID .. ":" .. rank
        end
      end
    end
  end
  if #entries == 0 then return "" end
  return table.concat(entries, "/")
end

local validityOK, validityReason = false, L.noProfile

local function CheckValidity()
  local results = LocalGearAdvisorResults
  if type(results) ~= "table"
      or results.schemaVersion ~= 1
      or not IsFiniteNumber(results.generatedAt)
      or results.generatedAt <= 0
      or results.generatedAt % 1 ~= 0
      or not IsNonEmptyString(results.characterName)
      or not IsNonEmptyString(results.region)
      or not IsNonEmptyString(results.server)
      or not IsNonEmptyString(results.class)
      or not IsFiniteNumber(results.specID)
      or results.specID % 1 ~= 0
      or not IsFiniteNumber(results.level)
      or results.level % 1 ~= 0
      or not IsNonEmptyString(results.race)
      or not IsNonEmptyString(results.talents)
      or type(results.traitSystems) ~= "table"
      or type(results.traitSystems.omnium_talents) ~= "string"
      or type(results.baselineGear) ~= "table"
      or not IsNonEmptyString(results.fightStyle)
      or not IsNonEmptyString(results.simcVersion)
      or not IsNonEmptyString(results.simcRevision)
      or not IsNonEmptyString(results.gameVersion)
      or results.dbcSource ~= "Live"
      or not IsNonEmptyString(results.profileHash)
      or #results.profileHash ~= 64
      or not results.profileHash:match("^[0-9a-f]+$")
      or type(results.items) ~= "table" then
    validityOK, validityReason = false, L.noProfile
    return validityOK, validityReason
  end
  local now = time()
  if not IsFiniteNumber(now) or results.generatedAt > now + 300 then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  if now - results.generatedAt > MAX_RESULT_AGE then
    validityOK, validityReason = false, L.expired
    return validityOK, validityReason
  end
  local wowVersion, wowBuild = GetBuildInfo()
  if IsSecret(wowVersion) or IsSecret(wowBuild)
      or type(wowVersion) ~= "string" or type(wowBuild) ~= "string" then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  if wowVersion .. "." .. wowBuild ~= results.gameVersion then
    validityOK, validityReason = false, L.gameBuild
    return validityOK, validityReason
  end

  local name = UnitName("player")
  local _, classFile = UnitClass("player")
  local _, raceFile = UnitRace("player")
  local level = UnitLevel("player")
  local specAPI = C_SpecializationInfo
  local specIndex = specAPI and specAPI.GetSpecialization and specAPI.GetSpecialization()
  if not specAPI or not specAPI.GetSpecializationInfo
      or IsSecret(specIndex) or type(specIndex) ~= "number" then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  local specID = specAPI.GetSpecializationInfo(specIndex)
  if IsSecret(name) or IsSecret(classFile) or IsSecret(raceFile)
      or IsSecret(level) or IsSecret(specID) then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  if name ~= results.characterName then
    validityOK, validityReason = false, L.character
    return validityOK, validityReason
  end
  local realmName = GetRealmName()
  if IsSecret(realmName) or type(realmName) ~= "string" then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  local realm = Tokenize(realmName)
  local regionID = GetCurrentRegion and GetCurrentRegion()
  if IsSecret(regionID) then regionID = nil end
  local region = regionID and REGION_NAMES[regionID]
  if not realm or not region then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  if realm ~= results.server or region ~= results.region then
    validityOK, validityReason = false, L.character
    return validityOK, validityReason
  end
  if not classFile or string.lower(classFile) ~= results.class or specID ~= results.specID then
    validityOK, validityReason = false, L.classSpec
    return validityOK, validityReason
  end
  if level ~= results.level or not raceFile or RaceToken(raceFile) ~= RaceToken(results.race) then
    validityOK, validityReason = false, L.identity
    return validityOK, validityReason
  end

  local configID = C_ClassTalents and C_ClassTalents.GetActiveConfigID()
  if IsSecret(configID) or not configID or not C_Traits or not C_Traits.GenerateImportString then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  local ok, talents = pcall(C_Traits.GenerateImportString, configID)
  if not ok or IsSecret(talents) or type(talents) ~= "string" then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  if talents ~= results.talents then
    validityOK, validityReason = false, L.talents
    return validityOK, validityReason
  end

  local expectedOmnium = results.traitSystems.omnium_talents
  for optionName in pairs(results.traitSystems) do
    if optionName ~= "omnium_talents" then
      validityOK, validityReason = false, L.unknown
      return validityOK, validityReason
    end
  end
  local currentOmnium = CurrentTraitString(48)
  if currentOmnium == nil then
    validityOK, validityReason = false, L.unknown
    return validityOK, validityReason
  end
  if currentOmnium ~= expectedOmnium then
    validityOK, validityReason = false, L.traits
    return validityOK, validityReason
  end

  for _, slot in ipairs(BASELINE_SLOTS) do
    local expected = results.baselineGear[slot]
    if expected == nil or (expected ~= false and type(expected) ~= "string") then
      validityOK, validityReason = false, L.noProfile
      return validityOK, validityReason
    end
    local itemLink = GetInventoryItemLink("player", SLOT_IDS[slot])
    if IsSecret(itemLink) then
      validityOK, validityReason = false, L.unknown
      return validityOK, validityReason
    end
    if expected == false then
      if itemLink ~= nil then
        validityOK, validityReason = false, L.gear
        return validityOK, validityReason
      end
    else
      if type(itemLink) ~= "string" then
        validityOK, validityReason = false, L.unknown
        return validityOK, validityReason
      end
      if ItemOptions(itemLink) ~= expected then
        validityOK, validityReason = false, L.gear
        return validityOK, validityReason
      end
    end
  end

  validityOK, validityReason = true, nil
  return validityOK, validityReason
end

local trackedTooltips = setmetatable({}, { __mode = "k" })
local eventFrame = CreateFrame("Frame")
eventFrame:RegisterEvent("PLAYER_ENTERING_WORLD")
eventFrame:RegisterEvent("PLAYER_EQUIPMENT_CHANGED")
eventFrame:RegisterEvent("TRAIT_CONFIG_UPDATED")
eventFrame:RegisterEvent("TRAIT_CONFIG_LIST_UPDATED")
eventFrame:RegisterEvent("ACTIVE_PLAYER_SPECIALIZATION_CHANGED")
eventFrame:RegisterEvent("PLAYER_LEVEL_UP")
eventFrame:RegisterEvent("GET_ITEM_INFO_RECEIVED")
eventFrame:RegisterEvent("ITEM_DATA_LOAD_RESULT")
eventFrame:SetScript("OnEvent", function()
  for tooltip in pairs(trackedTooltips) do
    tooltip.__LocalGearAdvisorLink = nil
    trackedTooltips[tooltip] = nil
    tooltip:Hide()
  end
end)

local function AddResult(tooltip)
  local getItem = tooltip.GetItem
  if type(getItem) ~= "function" then return end
  local ok, _, itemLink = pcall(getItem, tooltip)
  if not ok or IsSecret(itemLink) or type(itemLink) ~= "string" then return end
  if not tooltip.__LocalGearAdvisorClearHook then
    tooltip.__LocalGearAdvisorClearHook = true
    tooltip:HookScript("OnTooltipCleared", function(owner)
      owner.__LocalGearAdvisorLink = nil
      trackedTooltips[owner] = nil
    end)
  end
  if tooltip.__LocalGearAdvisorLink == itemLink then return end

  local options = ItemOptions(itemLink)
  local results = LocalGearAdvisorResults
  if not options or type(results) ~= "table" or type(results.items) ~= "table" then return end
  local result = results.items[options]
  if type(result) ~= "table"
      or result.status ~= "simulated"
      or not IsFiniteNumber(result.deltaPercent)
      or type(result.bestSlot) ~= "string"
      or not SLOT_IDS[result.bestSlot]
      or not IsFiniteNumber(result.iterations)
      or result.iterations <= 0
      or result.iterations % 1 ~= 0 then
    return
  end
  tooltip.__LocalGearAdvisorLink = itemLink
  trackedTooltips[tooltip] = true

  tooltip:AddLine(" ")
  tooltip:AddLine(L.title, 0.20, 0.90, 0.85)
  if type(results.fightStyle) == "string" then
    tooltip:AddDoubleLine(L.scenario, results.fightStyle, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8)
  end
  local now = time()
  if IsFiniteNumber(results.generatedAt) and IsFiniteNumber(now) then
    local age = math.max(0, now - results.generatedAt)
    tooltip:AddDoubleLine(L.age, AgeText(age), 0.6, 0.6, 0.6, 0.8, 0.8, 0.8)
  end
  if type(results.simcVersion) == "string" then
    tooltip:AddDoubleLine(L.simc, results.simcVersion, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8)
  end
  local valid, reason = CheckValidity()
  if not valid then
    tooltip:AddDoubleLine(L.stale, reason or L.unknown, 1.0, 0.35, 0.25, 1.0, 0.75, 0.2)
    return
  end

  local delta = result.deltaPercent
  local label, red, green, blue = L.equal, 0.9, 0.85, 0.3
  if delta > 0.05 then
    label, red, green, blue = L.upgrade, 0.25, 1.0, 0.35
  elseif delta < -0.05 then
    label, red, green, blue = L.downgrade, 1.0, 0.3, 0.25
  end
  tooltip:AddDoubleLine(label, string.format("%+.2f%%", delta), red, green, blue, red, green, blue)
  tooltip:AddDoubleLine(L.slot, SLOT_LABELS[result.bestSlot] or result.bestSlot, 0.8, 0.8, 0.8, 1, 1, 1)
  tooltip:AddDoubleLine(L.iterations, tostring(result.iterations), 0.6, 0.6, 0.6, 0.8, 0.8, 0.8)
end

if TooltipDataProcessor and TooltipDataProcessor.AddTooltipPostCall then
  TooltipDataProcessor.AddTooltipPostCall(Enum.TooltipDataType.Item, AddResult)
else
  geterrorhandler()(ADDON_NAME .. ": TooltipDataProcessor is unavailable")
end
