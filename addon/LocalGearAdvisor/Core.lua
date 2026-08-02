local ADDON_NAME = ...

local L = GetLocale() == "deDE" and {
  title = "Lokale Ausrüstungsanalyse",
  upgrade = "DPS-Upgrade",
  downgrade = "DPS-Downgrade",
  equal = "DPS ungefähr gleich",
  dpsOnly = "Nur offensiver DPS-Vergleich",
  stale = "Ergebnis veraltet",
  noProfile = "Keine gültigen Simulationsdaten",
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
  upgrade = "DPS upgrade",
  downgrade = "DPS downgrade",
  equal = "DPS approximately equal",
  dpsOnly = "Offensive DPS comparison only",
  stale = "Result is stale",
  noProfile = "No valid simulation data",
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
  if IsSecret(value) or type(value) ~= "string" then return nil end
  value = string.lower(value):gsub(" ", "_")
  value = value:gsub("[^%w%%+%._\128-\255]", "")
  return value:gsub("_+$", "")
end

local REGION_NAMES = { [1] = "us", [2] = "kr", [3] = "eu", [4] = "tw", [5] = "cn" }
local VALID_REGIONS = { us=true, kr=true, eu=true, tw=true, cn=true }
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
  if IsSecret(itemLink) or type(itemLink) ~= "string" then return nil end
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

-- Structural/schema check for one aggregate entry. Every field required by
-- the deep runtime validation below must already be present and well typed
-- here so a tampered or partially-generated profile can never reach it.
local PROFILE_KEYS = {
  region=true, server=true, characterName=true, class=true, spec=true, specID=true,
  level=true, race=true, talents=true, traitSystems=true, baselineGear=true,
  fightStyle=true, baselineDps=true, simcVersion=true, simcRevision=true,
  gameVersion=true, dbcSource=true, profileHash=true, generatedAt=true, items=true,
}
local ITEM_KEYS = {
  itemID=true, name=true, fingerprint=true, bestSlot=true, candidateDps=true,
  deltaPercent=true, iterations=true, status=true,
}
local RESULT_SLOTS = {}
for _, slot in ipairs(BASELINE_SLOTS) do RESULT_SLOTS[slot] = true end

local function HasExactKeys(value, allowed)
  if IsSecret(value) or type(value) ~= "table" then return false end
  local found = 0
  local expected = 0
  for key in pairs(allowed) do expected = expected + 1 end
  for key in pairs(value) do
    if IsSecret(key) or not allowed[key] then return false end
    found = found + 1
  end
  return found == expected
end

local function CanonicalOptionsItemID(options)
  if not IsNonEmptyString(options) then return nil end
  local itemID = options:match("^,id=([1-9]%d*)")
  if not itemID then return nil end
  local consumed = ",id=" .. itemID
  local remainder = options:sub(#consumed + 1)
  local seen = { id=true }
  while remainder ~= "" do
    local segment, key = remainder:match("^(,([a-z_]+)=[^,\r\n]+)")
    if not segment or seen[key] then return nil end
    seen[key] = true
    remainder = remainder:sub(#segment + 1)
  end
  return tonumber(itemID)
end

local function IsValidItem(options, item)
  local optionItemID = CanonicalOptionsItemID(options)
  return IsNonEmptyString(options)
      and optionItemID ~= nil
      and HasExactKeys(item, ITEM_KEYS)
      and IsFiniteNumber(item.itemID) and item.itemID > 0 and item.itemID <= 10000000
      and item.itemID % 1 == 0
      and tonumber(optionItemID) == item.itemID
      and not IsSecret(item.name) and (item.name == false or IsNonEmptyString(item.name))
      and IsNonEmptyString(item.fingerprint) and #item.fingerprint == 64
      and item.fingerprint:match("^[0-9a-f]+$") ~= nil
      and IsNonEmptyString(item.bestSlot) and RESULT_SLOTS[item.bestSlot] == true
      and IsFiniteNumber(item.candidateDps) and item.candidateDps >= 0
      and item.candidateDps <= 1000000000000
      and IsFiniteNumber(item.deltaPercent) and math.abs(item.deltaPercent) <= 1000000
      and IsFiniteNumber(item.iterations) and item.iterations >= 100
      and item.iterations <= 1000000 and item.iterations % 1 == 0
      and not IsSecret(item.status) and item.status == "simulated"
end

local function IsValidProfileShape(profile)
  if not HasExactKeys(profile, PROFILE_KEYS)
      or not IsNonEmptyString(profile.region)
      or string.lower(profile.region) ~= profile.region
      or VALID_REGIONS[profile.region] ~= true
  then return false end
  if not IsNonEmptyString(profile.server) or Tokenize(profile.server) ~= profile.server
      or not IsNonEmptyString(profile.characterName)
      or not IsFiniteNumber(profile.specID) or profile.specID <= 0 or profile.specID > 10000
      or profile.specID % 1 ~= 0
      or not IsNonEmptyString(profile.class) or string.lower(profile.class) ~= profile.class
      or not IsNonEmptyString(profile.spec) or string.lower(profile.spec) ~= profile.spec
      or not IsFiniteNumber(profile.level) or profile.level <= 0 or profile.level > 90
      or profile.level % 1 ~= 0
      or not IsNonEmptyString(profile.race) or string.lower(profile.race) ~= profile.race
      or not IsNonEmptyString(profile.talents)
      or not HasExactKeys(profile.traitSystems, {omnium_talents=true})
      or IsSecret(profile.traitSystems.omnium_talents)
      or type(profile.traitSystems.omnium_talents) ~= "string"
      or not HasExactKeys(profile.baselineGear, RESULT_SLOTS)
      or not IsNonEmptyString(profile.fightStyle)
      or not IsFiniteNumber(profile.baselineDps) or profile.baselineDps < 0
      or profile.baselineDps > 1000000000000
      or not IsFiniteNumber(profile.generatedAt) or profile.generatedAt <= 0
      or profile.generatedAt > 9007199254740991
      or profile.generatedAt % 1 ~= 0
      or not IsNonEmptyString(profile.simcVersion)
      or not IsNonEmptyString(profile.simcRevision)
      or not IsNonEmptyString(profile.gameVersion)
      or IsSecret(profile.dbcSource) or profile.dbcSource ~= "Live"
      or not IsNonEmptyString(profile.profileHash) or #profile.profileHash ~= 64
      or profile.profileHash:match("^[0-9a-f]+$") == nil
      or IsSecret(profile.items) or type(profile.items) ~= "table"
  then return false end
  for _, slot in ipairs(BASELINE_SLOTS) do
    local expected = profile.baselineGear[slot]
    if IsSecret(expected) or (expected ~= false and not IsNonEmptyString(expected)) then
      return false
    end
  end
  for options, item in pairs(profile.items) do
    if not IsValidItem(options, item) then return false end
  end
  return true
end

local function TableLength(value)
  local count = 0
  for _ in pairs(value) do count = count + 1 end
  return count
end

-- Fail closed on the whole aggregate (not just one entry) if anything is
-- malformed, non-dense, or two entries share an identity: a tampered file
-- is never partially trusted, and one broken character must not hide
-- another's data by accident, so we simply refuse all of it.
local function ValidProfiles(results)
  if IsSecret(results)
      or type(results) ~= "table"
      or IsSecret(results.schemaVersion)
      or results.schemaVersion ~= 2
      or IsSecret(results.profiles)
      or type(results.profiles) ~= "table"
      or not HasExactKeys(results, {schemaVersion=true, profiles=true}) then
    return nil
  end
  local seenIdentity = {}
  local profiles = {}
  local arrayCount = 0
  for _, profile in ipairs(results.profiles) do
    arrayCount = arrayCount + 1
    if not IsValidProfileShape(profile) then return nil end
    local identityKey = string.lower(profile.region) .. "\30" .. string.lower(profile.server)
        .. "\30" .. string.lower(profile.characterName) .. "\30" .. profile.specID
    if seenIdentity[identityKey] then return nil end
    seenIdentity[identityKey] = true
    profiles[#profiles + 1] = profile
  end
  -- ipairs() alone stops at the first hole and silently ignores anything
  -- past it (or keys outside 1..N); comparing against a full pairs() count
  -- catches holes, non-sequential keys, and non-integer keys alike.
  if arrayCount ~= TableLength(results.profiles) then
    return nil
  end
  return profiles
end

local function CurrentRuntimeIdentity()
  local name = UnitName("player")
  local _, classFile = UnitClass("player")
  local _, raceFile = UnitRace("player")
  local level = UnitLevel("player")
  local specAPI = C_SpecializationInfo
  local specIndex = specAPI and specAPI.GetSpecialization and specAPI.GetSpecialization()
  if not specAPI or not specAPI.GetSpecializationInfo
      or IsSecret(specIndex) or type(specIndex) ~= "number" then
    return nil
  end
  local specID = specAPI.GetSpecializationInfo(specIndex)
  local realmName = GetRealmName()
  local regionID = GetCurrentRegion and GetCurrentRegion()
  if IsSecret(regionID) then regionID = nil end
  local region = regionID and REGION_NAMES[regionID]
  if IsSecret(name) or IsSecret(classFile) or IsSecret(raceFile) or IsSecret(level)
      or IsSecret(specID) or IsSecret(realmName)
      or type(name) ~= "string" or type(realmName) ~= "string" or type(specID) ~= "number" then
    return nil
  end
  local realm = Tokenize(realmName)
  if not realm or not region then return nil end
  return {
    -- WoW character names are unique per realm case-insensitively, so
    -- comparing lowercase here can never conflate two different characters.
    name = string.lower(name),
    classFile = classFile,
    raceFile = raceFile,
    level = level,
    specID = specID,
    realm = realm,
    region = region,
  }
end

-- Exact match on region/realm/name/specID only: this is the one place that
-- decides which character's data may ever be shown, so no cross-character
-- leakage is possible even if two characters share item options.
local function FindCurrentProfile(profiles, identity)
  for _, profile in ipairs(profiles) do
    if string.lower(profile.region) == identity.region
        and string.lower(profile.server) == identity.realm
        and string.lower(profile.characterName) == identity.name
        and profile.specID == identity.specID then
      return profile
    end
  end
  return nil
end

local function ValidateProfileAgainstRuntime(profile, identity)
  local now = time()
  if not IsFiniteNumber(now) or profile.generatedAt > now + 300 then
    return false, L.unknown
  end
  if now - profile.generatedAt > MAX_RESULT_AGE then
    return false, L.expired
  end
  local wowVersion, wowBuild = GetBuildInfo()
  if IsSecret(wowVersion) or IsSecret(wowBuild)
      or type(wowVersion) ~= "string" or type(wowBuild) ~= "string" then
    return false, L.unknown
  end
  if wowVersion .. "." .. wowBuild ~= profile.gameVersion then
    return false, L.gameBuild
  end
  if not identity.classFile or string.lower(identity.classFile) ~= profile.class then
    return false, L.classSpec
  end
  if identity.level ~= profile.level or not identity.raceFile
      or RaceToken(identity.raceFile) ~= RaceToken(profile.race) then
    return false, L.identity
  end

  local configID = C_ClassTalents and C_ClassTalents.GetActiveConfigID()
  if IsSecret(configID) or not configID or not C_Traits or not C_Traits.GenerateImportString then
    return false, L.unknown
  end
  local ok, talents = pcall(C_Traits.GenerateImportString, configID)
  if not ok or IsSecret(talents) or type(talents) ~= "string" then
    return false, L.unknown
  end
  if talents ~= profile.talents then
    return false, L.talents
  end

  local expectedOmnium = profile.traitSystems.omnium_talents
  for optionName in pairs(profile.traitSystems) do
    if optionName ~= "omnium_talents" then
      return false, L.unknown
    end
  end
  local currentOmnium = CurrentTraitString(48)
  if currentOmnium == nil then
    return false, L.unknown
  end
  if currentOmnium ~= expectedOmnium then
    return false, L.traits
  end

  for _, slot in ipairs(BASELINE_SLOTS) do
    local expected = profile.baselineGear[slot]
    if IsSecret(expected) then
      return false, L.unknown
    end
    if expected == nil or (expected ~= false and type(expected) ~= "string") then
      return false, L.noProfile
    end
    local itemLink = GetInventoryItemLink("player", SLOT_IDS[slot])
    if IsSecret(itemLink) then
      return false, L.unknown
    end
    if expected == false then
      if itemLink ~= nil then
        return false, L.gear
      end
    else
      if type(itemLink) ~= "string" then
        return false, L.unknown
      end
      if ItemOptions(itemLink) ~= expected then
        return false, L.gear
      end
    end
  end

  return true, nil
end

-- Locate exactly the current character/spec's record (if any) and validate
-- it. Returns the matched profile (or nil), ok, reason -- item lookups in
-- AddResult must only ever use the returned profile, never the raw table.
local function CheckValidity()
  local profiles = ValidProfiles(LocalGearAdvisorResults)
  if not profiles then
    return nil, false, L.noProfile
  end
  local identity = CurrentRuntimeIdentity()
  if not identity then
    return nil, false, L.unknown
  end
  local matched = FindCurrentProfile(profiles, identity)
  if not matched then
    return nil, false, L.noProfile
  end
  local ok, reason = ValidateProfileAgainstRuntime(matched, identity)
  return matched, ok, reason
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
  if not options then return end
  local profile, valid, reason = CheckValidity()
  if not profile or type(profile.items) ~= "table" then return end
  local result = profile.items[options]
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
  tooltip:AddLine(L.dpsOnly, 0.95, 0.75, 0.20)
  if type(profile.fightStyle) == "string" then
    tooltip:AddDoubleLine(L.scenario, profile.fightStyle, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8)
  end
  local now = time()
  if IsFiniteNumber(profile.generatedAt) and IsFiniteNumber(now) then
    local age = math.max(0, now - profile.generatedAt)
    tooltip:AddDoubleLine(L.age, AgeText(age), 0.6, 0.6, 0.6, 0.8, 0.8, 0.8)
  end
  if type(profile.simcVersion) == "string" then
    tooltip:AddDoubleLine(L.simc, profile.simcVersion, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8)
  end
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
