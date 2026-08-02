-- Workflow-first Midnight Dark UI: a 1154x600 window with a fixed sidebar
-- (Analyse/Import/Profile/Einstellungen) matching the approved mockup
-- direction. Every widget here is glue around the small, independently
-- testable functions on NS.UI (page metadata, scale presets, the export/
-- check/import wrappers, and the merged profile list) -- the actual
-- CreateFrame calls never contain business logic of their own so the logic
-- can be proven correct without a real WoW client.
--
-- Real GetSimcProfile call, never simulated: WoW addons cannot write to the
-- OS clipboard, so the Analyse export box is a manually copyable EditBox
-- (Ctrl+C), never a false "copied" claim. Import.lua's existing decode/
-- apply/undo/delete already own every SavedVariables mutation and its
-- safety contract; this file only ever calls through those functions.

local ADDON_NAME = ...
LocalGearAdvisorNS = LocalGearAdvisorNS or {}
local NS = LocalGearAdvisorNS
local L = NS.L

NS.UI = NS.UI or {}
local UI = NS.UI

--------------------------------------------------------------------------
-- Geometry & palette (Midnight Dark: real dark surfaces/borders, not
-- transparent Blizzard chrome templates).

local FRAME_WIDTH, FRAME_HEIGHT = 1154, 600
local SIDEBAR_WIDTH = 176
local HEADER_HEIGHT = 92
local ROW_HEIGHT = 30
local EDITBOX_HEIGHT = FRAME_HEIGHT - HEADER_HEIGHT - 180

local COLORS = {
  frame   = { 0.051, 0.071, 0.094, 0.99 },
  sidebar = { 0.027, 0.039, 0.055, 0.98 },
  header  = { 0.051, 0.071, 0.094, 1.00 },
  surface = { 0.043, 0.059, 0.078, 0.98 },
  border  = { 1, 1, 1, 0.08 },
  hover   = { 0.063, 0.133, 0.161, 1.00 },
  active  = { 0.063, 0.169, 0.169, 1.00 },
  accent  = { 0.051, 0.820, 0.620, 1.00 },
  none    = { 0, 0, 0, 0 },
}
UI.COLORS = COLORS

local SCALE_PRESETS = { 70, 85, 100, 115, 130, 150 }
UI.SCALE_PRESETS = SCALE_PRESETS

function UI.ScaleForPreset(percent)
  for _, candidate in ipairs(SCALE_PRESETS) do
    if candidate == percent then return percent / 100 end
  end
  return nil
end

local PAGE_ORDER = { "analyse", "import", "profiles", "settings" }
UI.PAGE_ORDER = PAGE_ORDER

local function PageMeta()
  return {
    analyse  = { title = L.pageAnalyse,  desc = L.pageAnalyseDesc },
    import   = { title = L.pageImport,   desc = L.pageImportDesc },
    profiles = { title = L.pageProfiles, desc = L.pageProfilesDesc },
    settings = { title = L.pageSettings, desc = L.pageSettingsDesc },
  }
end
UI.PageMeta = PageMeta

--------------------------------------------------------------------------
-- Pure(ish) data helpers -- independently testable without any frame.

local function ItemCount(profile)
  local count = 0
  for _ in pairs(profile.items) do count = count + 1 end
  return count
end
UI.ItemCount = ItemCount

function UI.BuildPreviewSummary(profile)
  return {
    identity = profile.characterName .. "-" .. profile.server,
    spec = profile.spec,
    scenario = profile.fightStyle,
    simc = profile.simcVersion,
    itemCount = ItemCount(profile),
    generatedAt = profile.generatedAt,
  }
end

-- Merges the immutable LocalGearAdvisorResults fallback with the mutable
-- LocalGearAdvisorDB, DB winning per identity -- exactly Core.lua's
-- CheckValidity() precedence, but for every stored identity, not just the
-- current character, so the Profile page can list everyone.
function UI.EffectiveProfileList()
  local schema = NS.Schema
  if not schema or not schema.ValidProfiles or not schema.IdentityKey then return {} end
  local fallbackProfiles = schema.ValidProfiles(LocalGearAdvisorResults) or {}
  local dbProfiles = schema.ValidProfiles(LocalGearAdvisorDB) or {}
  local byKey, order = {}, {}
  for _, profile in ipairs(fallbackProfiles) do
    local key = schema.IdentityKey(profile)
    byKey[key] = { profile = profile, source = "fallback" }
    order[#order + 1] = key
  end
  for _, profile in ipairs(dbProfiles) do
    local key = schema.IdentityKey(profile)
    if byKey[key] == nil then order[#order + 1] = key end
    byKey[key] = { profile = profile, source = "db" }
  end
  local rows = {}
  for _, key in ipairs(order) do
    local entry = byKey[key]
    local profile = entry.profile
    rows[#rows + 1] = {
      identityKey = key,
      characterName = profile.characterName,
      server = profile.server,
      spec = profile.spec,
      fightStyle = profile.fightStyle,
      itemCount = ItemCount(profile),
      generatedAt = profile.generatedAt,
      simcVersion = profile.simcVersion,
      source = entry.source,
    }
  end
  return rows
end

function UI.CurrentCharacterLabel()
  if type(UnitName) ~= "function" then return nil end
  local ok, name = pcall(UnitName, "player")
  if not ok or type(name) ~= "string" or name == "" then return nil end
  local specName
  if C_SpecializationInfo and C_SpecializationInfo.GetSpecialization
      and C_SpecializationInfo.GetSpecializationInfo then
    local specOk, specIndex = pcall(C_SpecializationInfo.GetSpecialization)
    if specOk and type(specIndex) == "number" then
      local infoOk, _, sName = pcall(C_SpecializationInfo.GetSpecializationInfo, specIndex)
      if infoOk and type(sName) == "string" and sName ~= "" then
        specName = sName
      end
    end
  end
  if specName then return name .. " - " .. specName end
  return name
end

-- Never fabricates an export: fails closed with a localized reason if the
-- official SimulationCraft addon is missing, errors, or returns no text.
-- Calls the exact safe method invocation the official addon documents:
-- SimulationcraftAPI:GetSimcProfile(false, false, false, nil) -- noBags is
-- false so bag items are included, matching the MVP's bag-candidate scope.
function UI.RunExport()
  if type(SimulationcraftAPI) ~= "table" or type(SimulationcraftAPI.GetSimcProfile) ~= "function" then
    return false, L.addonMissing
  end
  local ok, text, apiErr = pcall(
    SimulationcraftAPI.GetSimcProfile, SimulationcraftAPI, false, false, false, nil
  )
  if not ok or type(text) ~= "string" or text == "" or apiErr ~= nil then
    return false, L.addonApiError
  end
  return true, text
end

-- "Prüfen" (check) never mutates SavedVariables: it only decodes+validates
-- via Import.lua's existing strict decoder and hands back a profile for
-- preview. "Importieren" (import) is the one and only place a checked
-- profile is actually applied, and only for the exact text last checked.
function UI.CheckImportText(text)
  if type(NS.DecodeProfileTransport) ~= "function" then
    return nil, L.unknown
  end
  local profile, err = NS.DecodeProfileTransport(text)
  if profile == nil then return nil, err end
  if type(NS.CheckProfileFreshness) ~= "function" then return nil, L.unknown end
  local fresh, freshnessReason = NS.CheckProfileFreshness(profile)
  if not fresh then return nil, freshnessReason end
  return profile, nil
end

function UI.ApplyCheckedProfile(profile)
  return NS.ApplyProfileTransport(profile)
end

--------------------------------------------------------------------------
-- Backdrop helper: a real solid-colored surface/border, no Blizzard
-- template chrome.

local function SetSolidBackdrop(frame, background, borderColor)
  frame:SetBackdrop({
    bgFile = "Interface\\Buttons\\WHITE8X8",
    edgeFile = borderColor and "Interface\\Buttons\\WHITE8X8" or nil,
    edgeSize = borderColor and 1 or 0,
  })
  frame:SetBackdropColor(background[1], background[2], background[3], background[4])
  if borderColor then
    frame:SetBackdropBorderColor(borderColor[1], borderColor[2], borderColor[3], borderColor[4])
  end
end
UI._SetSolidBackdrop = SetSolidBackdrop

--------------------------------------------------------------------------
-- Widget state (module-local upvalues) and forward declarations. Lua 5.1
-- resolves a `local function Foo()` body's free variables at PARSE time, so
-- any locals it calls that are defined later in the file must be declared
-- (without assignment) before it -- forward-declared here to keep the
-- builder functions below in natural top-to-bottom reading order.

local root, headerTitle, headerDesc
local sidebarButtons = {}
local pages = {}
local currentPage = PAGE_ORDER[1]
local escRegistered = false

local exportBox, exportStatus, exportPill, characterPill
local importBox, importStatus, checkButtonWidget, importButtonWidget
local importPreview = {}
local lastCheckedText, lastCheckedProfile

local profilesContainer, emptyLabel, detailsPanel, undoButtonWidget, undoStatus
local detailsLines = {}
local profileRows = {}
local selectedIdentityKey, deleteConfirmPending
UI._detailsLines = detailsLines
UI._profileRows = profileRows

local BuildSidebar, BuildHeader, BuildPages
local BuildAnalysePage, BuildImportPage, BuildProfilesPage, BuildSettingsPage
local ShowPage, CreateRoot

--------------------------------------------------------------------------
-- Analyse page

function UI.RefreshAnalyse()
  if exportPill then
    if type(SimulationcraftAPI) == "table" and type(SimulationcraftAPI.GetSimcProfile) == "function" then
      exportPill:SetText(L.addonReady)
    else
      exportPill:SetText(L.addonMissing)
    end
  end
  if characterPill then
    characterPill:SetText(UI.CurrentCharacterLabel() or "")
  end
end

BuildAnalysePage = function(page)
  local statusRow = CreateFrame("Frame", nil, page)
  statusRow:SetPoint("TOPLEFT", 0, -6)
  statusRow:SetPoint("TOPRIGHT", 0, -6)
  statusRow:SetHeight(24)

  exportPill = statusRow:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  exportPill:SetPoint("LEFT", 0, 0)

  characterPill = statusRow:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  characterPill:SetPoint("LEFT", exportPill, "RIGHT", 16, 0)

  local card = CreateFrame("Frame", nil, page, "BackdropTemplate")
  card:SetPoint("TOPLEFT", statusRow, "BOTTOMLEFT", 0, -10)
  card:SetPoint("BOTTOMRIGHT", 0, 0)
  SetSolidBackdrop(card, COLORS.surface, COLORS.border)

  local title = card:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  title:SetPoint("TOPLEFT", 18, -16)
  title:SetText(L.exportTitle)

  local body = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  body:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -8)
  body:SetText(L.exportBody)

  local scroll = CreateFrame("ScrollFrame", nil, card, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 18, -70)
  scroll:SetPoint("BOTTOMRIGHT", -18, 70)

  exportBox = CreateFrame("EditBox", nil, scroll)
  exportBox:SetMultiLine(true)
  exportBox:SetAutoFocus(false)
  exportBox:EnableMouse(true)
  exportBox:SetFontObject("ChatFontNormal")
  exportBox:SetWidth(FRAME_WIDTH - SIDEBAR_WIDTH - 76)
  exportBox:SetHeight(EDITBOX_HEIGHT)
  exportBox:SetText(L.exportPending)
  exportBox:SetScript("OnMouseDown", function(self) self:SetFocus() end)
  exportBox:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  scroll:SetScrollChild(exportBox)
  UI._exportBox = exportBox

  local exportButton = CreateFrame("Button", nil, card, "BackdropTemplate")
  exportButton:SetSize(180, 28)
  exportButton:SetPoint("BOTTOMLEFT", 18, 24)
  SetSolidBackdrop(exportButton, COLORS.active, COLORS.accent)
  local exportButtonLabel = exportButton:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  exportButtonLabel:SetPoint("CENTER")
  exportButtonLabel:SetText(L.exportButton)

  exportStatus = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  exportStatus:SetPoint("LEFT", exportButton, "RIGHT", 12, 0)
  exportStatus:SetText(L.exportPending)

  exportButton:SetScript("OnClick", function()
    local ok, textOrReason = UI.RunExport()
    if ok then
      exportBox:SetText(textOrReason)
      exportBox:HighlightText()
      exportBox:SetFocus()
      exportStatus:SetText(L.exportInstruction)
    else
      exportBox:SetText("")
      exportStatus:SetText(textOrReason)
    end
  end)
  UI._exportButton = exportButton
  UI._exportStatus = exportStatus
  UI._exportPill = exportPill
  UI._characterPill = characterPill
end

--------------------------------------------------------------------------
-- Import page

local function ClearImportPreview()
  for _, fs in pairs(importPreview) do fs:SetText("") end
end

local function RunCheck()
  local text = importBox:GetText()
  local profile, err = UI.CheckImportText(text)
  if not profile then
    lastCheckedText, lastCheckedProfile = nil, nil
    ClearImportPreview()
    importStatus:SetText(L.importCheckFailedPrefix .. tostring(err))
    if importButtonWidget then importButtonWidget:Disable() end
    return
  end
  lastCheckedText, lastCheckedProfile = text, profile
  local summary = UI.BuildPreviewSummary(profile)
  importPreview.identity:SetText(L.previewIdentity .. ": " .. summary.identity)
  importPreview.spec:SetText(L.previewSpec .. ": " .. summary.spec)
  importPreview.scenario:SetText(L.previewScenario .. ": " .. summary.scenario)
  importPreview.simc:SetText(L.previewSimc .. ": " .. summary.simc)
  importPreview.items:SetText(L.previewItems .. ": " .. tostring(summary.itemCount))
  importStatus:SetText("")
  if importButtonWidget then importButtonWidget:Enable() end
end
UI._RunCheck = RunCheck

local function RunImport()
  local text = importBox:GetText()
  if lastCheckedProfile == nil or text ~= lastCheckedText then
    importStatus:SetText(L.importNeedsRecheck)
    if importButtonWidget then importButtonWidget:Disable() end
    return
  end
  local ok, err = UI.ApplyCheckedProfile(lastCheckedProfile)
  if not ok then
    importStatus:SetText(L.importErrorPrefix .. tostring(err))
    return
  end
  importStatus:SetText(L.importSuccess)
  lastCheckedText, lastCheckedProfile = nil, nil
  ClearImportPreview()
  if importButtonWidget then importButtonWidget:Disable() end
  if UI.RefreshProfiles then UI.RefreshProfiles() end
end
UI._RunImport = RunImport

function UI.GetLastCheckedProfile()
  return lastCheckedProfile, lastCheckedText
end

BuildImportPage = function(page)
  local card = CreateFrame("Frame", nil, page, "BackdropTemplate")
  card:SetPoint("TOPLEFT", 0, -6)
  card:SetPoint("BOTTOMRIGHT", 0, 0)
  SetSolidBackdrop(card, COLORS.surface, COLORS.border)

  local title = card:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  title:SetPoint("TOPLEFT", 18, -16)
  title:SetText(L.importTitle)

  local body = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  body:SetPoint("TOPLEFT", title, "BOTTOMLEFT", 0, -8)
  body:SetText(L.importBody)

  local scroll = CreateFrame("ScrollFrame", nil, card, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 18, -74)
  scroll:SetPoint("BOTTOM", 0, 90)
  scroll:SetPoint("RIGHT", -320, 0)

  importBox = CreateFrame("EditBox", nil, scroll, "BackdropTemplate")
  importBox:SetMultiLine(true)
  importBox:SetAutoFocus(false)
  importBox:EnableMouse(true)
  importBox:SetFontObject("ChatFontNormal")
  importBox:SetWidth(FRAME_WIDTH - SIDEBAR_WIDTH - 380)
  importBox:SetHeight(EDITBOX_HEIGHT)
  importBox:SetTextInsets(8, 8, 8, 8)
  SetSolidBackdrop(importBox, COLORS.frame, COLORS.accent)
  importBox:SetText("")
  importBox:SetScript("OnMouseDown", function(self) self:SetFocus() end)
  importBox:SetScript("OnEscapePressed", function(self) self:ClearFocus() end)
  importBox:SetScript("OnTextChanged", function()
    if importButtonWidget then importButtonWidget:Disable() end
  end)
  scroll:SetScrollChild(importBox)
  UI._importBox = importBox

  local previewPanel = CreateFrame("Frame", nil, card, "BackdropTemplate")
  previewPanel:SetPoint("TOPRIGHT", -18, -74)
  previewPanel:SetWidth(280)
  previewPanel:SetPoint("BOTTOM", 0, 90)
  SetSolidBackdrop(previewPanel, COLORS.header, COLORS.border)
  local previewY = -10
  for _, key in ipairs({ "identity", "spec", "scenario", "simc", "items" }) do
    local fs = previewPanel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fs:SetPoint("TOPLEFT", 10, previewY)
    importPreview[key] = fs
    previewY = previewY - 20
  end

  checkButtonWidget = CreateFrame("Button", nil, card, "BackdropTemplate")
  checkButtonWidget:SetSize(120, 28)
  checkButtonWidget:SetPoint("BOTTOMLEFT", 18, 24)
  SetSolidBackdrop(checkButtonWidget, COLORS.surface, COLORS.border)
  local checkLabel = checkButtonWidget:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  checkLabel:SetPoint("CENTER")
  checkLabel:SetText(L.checkButton)
  checkButtonWidget:SetScript("OnClick", RunCheck)
  UI._checkButton = checkButtonWidget

  importButtonWidget = CreateFrame("Button", nil, card, "BackdropTemplate")
  importButtonWidget:SetSize(140, 28)
  importButtonWidget:SetPoint("LEFT", checkButtonWidget, "RIGHT", 10, 0)
  SetSolidBackdrop(importButtonWidget, COLORS.active, COLORS.accent)
  local importLabel = importButtonWidget:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  importLabel:SetPoint("CENTER")
  importLabel:SetText(L.importButton)
  importButtonWidget:SetScript("OnClick", RunImport)
  importButtonWidget:Disable()
  UI._importButton = importButtonWidget

  importStatus = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  importStatus:SetPoint("LEFT", importButtonWidget, "RIGHT", 12, 0)
  importStatus:SetText(L.importPending)
  UI._importStatus = importStatus
  UI._importPreview = importPreview
end

--------------------------------------------------------------------------
-- Profiles page

function UI.RequestDeleteProfile(identityKey)
  if deleteConfirmPending ~= identityKey then
    deleteConfirmPending = identityKey
    UI.RefreshProfiles()
    return
  end
  deleteConfirmPending = nil
  local ok, err = NS.DeleteDbProfile(identityKey)
  if ok then
    local fallbackRevealed = false
    local fallbackFresh = false
    for _, data in ipairs(UI.EffectiveProfileList()) do
      if data.identityKey == identityKey and data.source == "fallback" then
        fallbackRevealed = true
        fallbackFresh = type(NS.CheckProfileFreshness) == "function"
            and NS.CheckProfileFreshness(data) == true
      end
    end
    if undoStatus then
      if fallbackRevealed then
        undoStatus:SetText(fallbackFresh and L.deleteFallbackRevealed or L.deleteFallbackStale)
      else
        undoStatus:SetText(L.deleteSuccess)
      end
    end
    if selectedIdentityKey == identityKey then UI.HideProfileDetails() end
  elseif undoStatus then
    undoStatus:SetText(L.deleteErrorPrefix .. tostring(err))
  end
  UI.RefreshProfiles()
end

function UI.CancelDeleteProfile()
  deleteConfirmPending = nil
  UI.RefreshProfiles()
end

function UI.ShowProfileDetails(identityKey)
  selectedIdentityKey = identityKey
  if not detailsPanel then return end
  for _, data in ipairs(UI.EffectiveProfileList()) do
    if data.identityKey == identityKey then
      detailsLines.character:SetText(data.characterName .. "-" .. data.server)
      detailsLines.spec:SetText(data.spec)
      detailsLines.scenario:SetText(data.fightStyle)
      detailsLines.items:SetText(tostring(data.itemCount))
      detailsLines.simc:SetText(data.simcVersion)
      detailsLines.source:SetText(data.source == "db" and L.sourceImported or L.sourceFallback)
      detailsPanel:Show()
      return
    end
  end
  detailsPanel:Hide()
end

function UI.HideProfileDetails()
  selectedIdentityKey = nil
  if detailsPanel then detailsPanel:Hide() end
end

local function GetOrCreateProfileRow(index)
  local row = profileRows[index]
  if row then return row end
  row = CreateFrame("Frame", nil, profilesContainer)
  row:SetHeight(ROW_HEIGHT)
  row:SetPoint("LEFT", 0, 0)
  row:SetPoint("RIGHT", 0, 0)

  local function column(width, anchorTo)
    local fs = row:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    if anchorTo then
      fs:SetPoint("LEFT", anchorTo, "RIGHT", 6, 0)
    else
      fs:SetPoint("LEFT", 4, 0)
    end
    fs:SetWidth(width)
    fs:SetJustifyH("LEFT")
    return fs
  end

  row.character = column(145)
  row.spec = column(74, row.character)
  row.scenario = column(80, row.spec)
  row.items = column(32, row.scenario)
  row.age = column(50, row.items)
  row.source = column(64, row.age)

  row.detailsButton = CreateFrame("Button", nil, row, "BackdropTemplate")
  row.detailsButton:SetSize(60, 22)
  row.detailsButton:SetPoint("LEFT", row.source, "RIGHT", 8, 0)
  SetSolidBackdrop(row.detailsButton, COLORS.surface, COLORS.border)
  row.detailsLabel = row.detailsButton:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  row.detailsLabel:SetPoint("CENTER")
  row.detailsLabel:SetText(L.detailsButton)

  row.deleteButton = CreateFrame("Button", nil, row, "BackdropTemplate")
  row.deleteButton:SetSize(96, 22)
  row.deleteButton:SetPoint("LEFT", row.detailsButton, "RIGHT", 6, 0)
  SetSolidBackdrop(row.deleteButton, COLORS.surface, COLORS.border)
  row.deleteLabel = row.deleteButton:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  row.deleteLabel:SetPoint("CENTER")
  row.deleteLabel:SetText(L.deleteButton)

  profileRows[index] = row
  return row
end

function UI.RefreshProfiles()
  if not profilesContainer then return end
  local rows = UI.EffectiveProfileList()
  if emptyLabel then
    if #rows == 0 then emptyLabel:Show() else emptyLabel:Hide() end
  end
  local now = (type(time) == "function" and time()) or 0
  local y = 0
  for index, data in ipairs(rows) do
    local row = GetOrCreateProfileRow(index)
    row:ClearAllPoints()
    row:SetPoint("TOPLEFT", 0, y)
    row:SetPoint("TOPRIGHT", 0, y)
    row:Show()
    row.character:SetText(data.characterName .. "-" .. data.server)
    row.spec:SetText(data.spec)
    row.scenario:SetText(data.fightStyle)
    row.items:SetText(tostring(data.itemCount))
    local age = math.max(0, now - data.generatedAt)
    row.age:SetText((NS.AgeText and NS.AgeText(age)) or tostring(age))
    row.source:SetText(data.source == "db" and L.sourceImported or L.sourceFallback)
    row.identityKey = data.identityKey
    row.detailsButton:SetScript("OnClick", function() UI.ShowProfileDetails(data.identityKey) end)
    if data.source == "db" then
      row.deleteButton:Show()
      row.deleteLabel:SetText(
        deleteConfirmPending == data.identityKey and L.deleteConfirmButton or L.deleteButton
      )
      row.deleteButton:SetScript("OnClick", function() UI.RequestDeleteProfile(data.identityKey) end)
    else
      row.deleteButton:Hide()
    end
    y = y - (ROW_HEIGHT + 2)
  end
  for index = #rows + 1, #profileRows do
    profileRows[index]:Hide()
  end
  profilesContainer:SetHeight(math.max(1, #rows * (ROW_HEIGHT + 2)))
end

BuildProfilesPage = function(page)
  local card = CreateFrame("Frame", nil, page, "BackdropTemplate")
  card:SetPoint("TOPLEFT", 0, -6)
  card:SetPoint("BOTTOMRIGHT", 0, 0)
  SetSolidBackdrop(card, COLORS.surface, COLORS.border)

  local headerRow = CreateFrame("Frame", nil, card)
  headerRow:SetPoint("TOPLEFT", 14, -14)
  headerRow:SetPoint("TOPRIGHT", -14, -14)
  headerRow:SetHeight(20)
  local function headerLabel(text, xOff, width)
    local fs = headerRow:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    fs:SetPoint("LEFT", xOff, 0)
    fs:SetWidth(width)
    fs:SetText(text)
    return fs
  end
  headerLabel(L.colCharacter, 4, 145)
  headerLabel(L.colSpec, 155, 74)
  headerLabel(L.colScenario, 235, 80)
  headerLabel(L.colItems, 321, 32)
  headerLabel(L.colAge, 359, 50)
  headerLabel(L.colSource, 415, 64)

  local scroll = CreateFrame("ScrollFrame", nil, card, "UIPanelScrollFrameTemplate")
  scroll:SetPoint("TOPLEFT", 14, -40)
  scroll:SetPoint("BOTTOMLEFT", 14, 44)
  scroll:SetPoint("RIGHT", -280, 0)
  profilesContainer = CreateFrame("Frame", nil, scroll)
  profilesContainer:SetWidth(650)
  profilesContainer:SetHeight(1)
  profilesContainer:SetPoint("TOPLEFT")
  profilesContainer:SetPoint("TOPRIGHT")
  scroll:SetScrollChild(profilesContainer)

  emptyLabel = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  emptyLabel:SetPoint("TOPLEFT", 18, -50)
  emptyLabel:SetText(L.noProfilesYet)
  emptyLabel:Hide()

  detailsPanel = CreateFrame("Frame", nil, card, "BackdropTemplate")
  detailsPanel:SetPoint("TOPRIGHT", -14, -40)
  detailsPanel:SetWidth(250)
  detailsPanel:SetPoint("BOTTOMRIGHT", -14, 44)
  SetSolidBackdrop(detailsPanel, COLORS.header, COLORS.border)
  detailsPanel:Hide()
  local detailsY = -10
  for _, key in ipairs({ "character", "spec", "scenario", "items", "simc", "source" }) do
    local fs = detailsPanel:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
    fs:SetPoint("TOPLEFT", 10, detailsY)
    detailsLines[key] = fs
    detailsY = detailsY - 20
  end
  local closeDetails = CreateFrame("Button", nil, detailsPanel, "BackdropTemplate")
  closeDetails:SetSize(60, 20)
  closeDetails:SetPoint("BOTTOMRIGHT", -8, 8)
  SetSolidBackdrop(closeDetails, COLORS.surface, COLORS.border)
  local closeDetailsLabel = closeDetails:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
  closeDetailsLabel:SetPoint("CENTER")
  closeDetailsLabel:SetText(L.closeButton)
  closeDetails:SetScript("OnClick", function() UI.HideProfileDetails() end)

  undoButtonWidget = CreateFrame("Button", nil, card, "BackdropTemplate")
  undoButtonWidget:SetSize(120, 26)
  undoButtonWidget:SetPoint("BOTTOMLEFT", 14, 12)
  SetSolidBackdrop(undoButtonWidget, COLORS.surface, COLORS.border)
  local undoLabel = undoButtonWidget:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  undoLabel:SetPoint("CENTER")
  undoLabel:SetText(L.undoButton)
  undoButtonWidget:SetScript("OnClick", function()
    local ok, err = NS.UndoLastImport()
    if ok then
      undoStatus:SetText(L.undoSuccess)
    else
      undoStatus:SetText(L.undoErrorPrefix .. tostring(err))
    end
    UI.RefreshProfiles()
  end)
  UI._undoButton = undoButtonWidget

  undoStatus = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  undoStatus:SetPoint("LEFT", undoButtonWidget, "RIGHT", 10, 0)
  UI._undoStatus = undoStatus
  UI._profilesContainer = profilesContainer
  UI._emptyLabel = emptyLabel
  UI._detailsPanel = detailsPanel
end

--------------------------------------------------------------------------
-- Settings page

function UI.ApplyScale(percent)
  local scale = UI.ScaleForPreset(percent)
  if not scale then return false end
  if root then root:SetScale(scale) end
  local settings = NS.EnsureSettings and NS.EnsureSettings()
  if settings then settings.frameScale = percent end
  return true
end

function UI.ResetPosition()
  if root then
    root:ClearAllPoints()
    root:SetPoint("CENTER")
  end
  local settings = NS.EnsureSettings and NS.EnsureSettings()
  if settings then settings.point = nil end
end

BuildSettingsPage = function(page)
  local card = CreateFrame("Frame", nil, page, "BackdropTemplate")
  card:SetPoint("TOPLEFT", 0, -6)
  card:SetPoint("BOTTOMRIGHT", 0, 0)
  SetSolidBackdrop(card, COLORS.surface, COLORS.border)

  local title = card:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  title:SetPoint("TOPLEFT", 18, -16)
  title:SetText(L.settingsTitle)

  local minimapLabel = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  minimapLabel:SetPoint("TOPLEFT", 18, -56)
  minimapLabel:SetText(L.settingsMinimap)

  local minimapButton = CreateFrame("Button", nil, card, "BackdropTemplate")
  minimapButton:SetSize(220, 26)
  minimapButton:SetPoint("TOPLEFT", minimapLabel, "BOTTOMLEFT", 0, -8)
  SetSolidBackdrop(minimapButton, COLORS.surface, COLORS.border)
  local minimapButtonLabel = minimapButton:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  minimapButtonLabel:SetPoint("CENTER")
  UI._minimapButton = minimapButton
  UI._minimapButtonLabel = minimapButtonLabel

  function UI.RefreshMinimapButtonLabel()
    local shown = NS.Minimap and NS.Minimap.IsShown and NS.Minimap.IsShown()
    minimapButtonLabel:SetText(shown and L.settingsMinimapHide or L.settingsMinimapShow)
  end

  minimapButton:SetScript("OnClick", function()
    if not (NS.Minimap and NS.Minimap.SetShown and NS.Minimap.IsShown) then return end
    NS.Minimap.SetShown(not NS.Minimap.IsShown())
    UI.RefreshMinimapButtonLabel()
  end)

  local scaleLabel = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  scaleLabel:SetPoint("TOPLEFT", minimapButton, "BOTTOMLEFT", 0, -24)
  scaleLabel:SetText(L.settingsScale)

  local scaleButtons = {}
  local x = 0
  for _, percent in ipairs(SCALE_PRESETS) do
    local button = CreateFrame("Button", nil, card, "BackdropTemplate")
    button:SetSize(58, 26)
    button:SetPoint("TOPLEFT", scaleLabel, "BOTTOMLEFT", x, -8)
    SetSolidBackdrop(button, COLORS.surface, COLORS.border)
    local buttonLabel = button:CreateFontString(nil, "OVERLAY", "GameFontNormalSmall")
    buttonLabel:SetPoint("CENTER")
    buttonLabel:SetText(percent .. "%")
    button:SetScript("OnClick", function() UI.ApplyScale(percent) end)
    scaleButtons[percent] = button
    x = x + 62
  end
  UI._scaleButtons = scaleButtons

  local resetButton = CreateFrame("Button", nil, card, "BackdropTemplate")
  resetButton:SetSize(220, 26)
  resetButton:SetPoint("TOPLEFT", scaleLabel, "BOTTOMLEFT", 0, -46)
  SetSolidBackdrop(resetButton, COLORS.surface, COLORS.border)
  local resetLabel = resetButton:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  resetLabel:SetPoint("CENTER")
  resetLabel:SetText(L.settingsResetPosition)
  UI._resetPositionButton = resetButton

  local settingsStatus = card:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  settingsStatus:SetPoint("LEFT", resetButton, "RIGHT", 10, 0)
  UI._settingsStatus = settingsStatus
  resetButton:SetScript("OnClick", function()
    UI.ResetPosition()
    settingsStatus:SetText(L.settingsResetPositionDone)
  end)
end

--------------------------------------------------------------------------
-- Sidebar / header / page switching

ShowPage = function(key)
  if not pages[key] then return end
  currentPage = key
  for pageKey, frame in pairs(pages) do
    if pageKey == key then frame:Show() else frame:Hide() end
  end
  local meta = PageMeta()[key]
  if headerTitle and meta then headerTitle:SetText(meta.title) end
  if headerDesc and meta then headerDesc:SetText(meta.desc) end
  for _, entry in ipairs(sidebarButtons) do
    if entry.key == key then
      SetSolidBackdrop(entry.button, COLORS.active, nil)
      entry.indicator:Show()
    else
      SetSolidBackdrop(entry.button, COLORS.none, nil)
      entry.indicator:Hide()
    end
  end
  if key == "profiles" then UI.RefreshProfiles() end
  if key == "analyse" then UI.RefreshAnalyse() end
end
UI.ShowPage = ShowPage

function UI.GetCurrentPage()
  return currentPage
end

BuildSidebar = function(parent)
  local sidebar = CreateFrame("Frame", nil, parent, "BackdropTemplate")
  sidebar:SetPoint("TOPLEFT")
  sidebar:SetPoint("BOTTOMLEFT")
  sidebar:SetWidth(SIDEBAR_WIDTH)
  SetSolidBackdrop(sidebar, COLORS.sidebar, nil)

  local brand = sidebar:CreateFontString(nil, "OVERLAY", "GameFontNormalLarge")
  brand:SetPoint("TOPLEFT", 14, -18)
  brand:SetText(L.brand)

  sidebarButtons = {}
  local y = -60
  for _, key in ipairs(PAGE_ORDER) do
    local button = CreateFrame("Button", nil, sidebar, "BackdropTemplate")
    button:SetPoint("TOPLEFT", 10, y)
    button:SetPoint("TOPRIGHT", -10, y)
    button:SetHeight(36)
    SetSolidBackdrop(button, COLORS.none, nil)

    local indicator = button:CreateTexture(nil, "OVERLAY")
    indicator:SetColorTexture(COLORS.accent[1], COLORS.accent[2], COLORS.accent[3], 1)
    indicator:SetPoint("TOPLEFT", 0, -7)
    indicator:SetPoint("BOTTOMLEFT", 0, 7)
    indicator:SetWidth(3)
    indicator:Hide()

    local label = button:CreateFontString(nil, "OVERLAY", "GameFontNormal")
    label:SetPoint("LEFT", 14, 0)
    label:SetText(PageMeta()[key].title)

    button:SetScript("OnClick", function() ShowPage(key) end)
    button:SetScript("OnEnter", function(self)
      if currentPage ~= key then SetSolidBackdrop(self, COLORS.hover, nil) end
    end)
    button:SetScript("OnLeave", function(self)
      if currentPage ~= key then SetSolidBackdrop(self, COLORS.none, nil) end
    end)

    sidebarButtons[#sidebarButtons + 1] = { key = key, button = button, indicator = indicator, label = label }
    y = y - 41
  end
  UI._sidebarButtons = sidebarButtons
end

BuildHeader = function(parent)
  local header = CreateFrame("Frame", nil, parent)
  header:SetPoint("TOPLEFT", SIDEBAR_WIDTH, 0)
  header:SetPoint("TOPRIGHT")
  header:SetHeight(HEADER_HEIGHT)
  header:EnableMouse(true)
  header:RegisterForDrag("LeftButton")
  header:SetScript("OnDragStart", function() if root then root:StartMoving() end end)
  header:SetScript("OnDragStop", function()
    if not root then return end
    root:StopMovingOrSizing()
    local settings = NS.EnsureSettings and NS.EnsureSettings()
    if settings then
      local point, _, relPoint, x, y = root:GetPoint(1)
      settings.point = { point = point, relPoint = relPoint, x = x, y = y }
    end
  end)

  headerTitle = header:CreateFontString(nil, "OVERLAY", "GameFontNormalHuge")
  headerTitle:SetPoint("TOPLEFT", 28, -22)

  headerDesc = header:CreateFontString(nil, "OVERLAY", "GameFontHighlightSmall")
  headerDesc:SetPoint("TOPLEFT", headerTitle, "BOTTOMLEFT", 0, -7)
  UI._headerTitle = headerTitle
  UI._headerDesc = headerDesc

  local closeButton = CreateFrame("Button", nil, header, "BackdropTemplate")
  closeButton:SetSize(24, 24)
  closeButton:SetPoint("TOPRIGHT", -14, -14)
  SetSolidBackdrop(closeButton, COLORS.surface, COLORS.border)
  local closeLabel = closeButton:CreateFontString(nil, "OVERLAY", "GameFontNormal")
  closeLabel:SetPoint("CENTER")
  closeLabel:SetText("x")
  closeButton:SetScript("OnClick", function() if root then root:Hide() end end)
  UI._closeButton = closeButton
end

BuildPages = function(parent)
  pages = {}
  for _, key in ipairs(PAGE_ORDER) do
    local page = CreateFrame("Frame", nil, parent)
    page:SetPoint("TOPLEFT", SIDEBAR_WIDTH, -HEADER_HEIGHT)
    page:SetPoint("BOTTOMRIGHT")
    page:Hide()
    pages[key] = page
  end
  BuildAnalysePage(pages.analyse)
  BuildImportPage(pages.import)
  BuildProfilesPage(pages.profiles)
  BuildSettingsPage(pages.settings)
  UI._pages = pages
end

--------------------------------------------------------------------------
-- Root frame: idempotent creation, ESC registration exactly once, saved
-- scale/position restored, ESC via UISpecialFrames (idempotent no matter
-- how many times Create()/Show() run).

CreateRoot = function()
  if root then return root end
  if not (CreateFrame and UIParent) then return nil end

  root = CreateFrame("Frame", "LocalGearAdvisorFrame", UIParent, "BackdropTemplate")
  root:SetSize(FRAME_WIDTH, FRAME_HEIGHT)
  root:SetMovable(true)
  root:EnableMouse(true)
  root:SetClampedToScreen(true)
  root:SetFrameStrata("HIGH")
  SetSolidBackdrop(root, COLORS.frame, COLORS.border)
  root:Hide()

  local settings = NS.EnsureSettings and NS.EnsureSettings()
  local placed = false
  if settings and type(settings.point) == "table" and type(settings.point.point) == "string" then
    local p = settings.point
    root:SetPoint(p.point, UIParent, p.relPoint or p.point, p.x or 0, p.y or 0)
    placed = true
  end
  if not placed then root:SetPoint("CENTER") end
  if settings and settings.frameScale then
    local scale = UI.ScaleForPreset(settings.frameScale)
    if scale then root:SetScale(scale) end
  end

  if type(UISpecialFrames) == "table" and not escRegistered then
    local alreadyListed = false
    for _, name in ipairs(UISpecialFrames) do
      if name == "LocalGearAdvisorFrame" then alreadyListed = true end
    end
    if not alreadyListed then
      table.insert(UISpecialFrames, "LocalGearAdvisorFrame")
    end
    escRegistered = true
  end

  BuildSidebar(root)
  BuildHeader(root)
  BuildPages(root)
  ShowPage(PAGE_ORDER[1])
  if UI.RefreshMinimapButtonLabel then UI.RefreshMinimapButtonLabel() end

  return root
end
UI.CreateRoot = CreateRoot

function UI.GetRootFrame()
  return root
end

function UI.Toggle()
  local frame = CreateRoot()
  if not frame then return end
  if frame:IsShown() then
    frame:Hide()
  else
    frame:Show()
    UI.RefreshAnalyse()
    UI.RefreshProfiles()
  end
end

function UI.Show()
  local frame = CreateRoot()
  if frame and not frame:IsShown() then
    frame:Show()
    UI.RefreshAnalyse()
    UI.RefreshProfiles()
  end
end

function UI.Hide()
  if root then root:Hide() end
end

--------------------------------------------------------------------------
-- Bootstrap: slash command, defensive Addon Compartment handler, and
-- creating the minimap button once the addon has finished loading.

SLASH_LOCALGEARADVISOR1 = "/lga"
SlashCmdList = SlashCmdList or {}
SlashCmdList["LOCALGEARADVISOR"] = function()
  UI.Toggle()
end

-- Matches the TOC's `## AddonCompartmentFunc` exactly; guarded with pcall
-- so a future Blizzard API change to the Addon Compartment call signature
-- can never turn into an unhandled Lua error for the player.
function LocalGearAdvisor_OnAddonCompartmentClick(_addonName, _buttonName)
  local ok, err = pcall(UI.Toggle)
  if not ok and geterrorhandler then
    geterrorhandler()(ADDON_NAME .. ": addon compartment click failed: " .. tostring(err))
  end
end

local loader = CreateFrame and CreateFrame("Frame") or nil
if loader then
  loader:RegisterEvent("ADDON_LOADED")
  loader:SetScript("OnEvent", function(_, _, loadedAddon)
    if loadedAddon == ADDON_NAME and NS.Minimap and NS.Minimap.Create then
      NS.Minimap.Create()
    end
  end)
end
