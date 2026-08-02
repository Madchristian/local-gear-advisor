-- Dependency-free draggable minimap button (no LibDBIcon/LibDataBroker):
-- this addon has exactly one button to place, so a small self-contained
-- implementation avoids pulling in a shared library and its own load-order
-- and versioning concerns. All angle/position math is expressed as plain,
-- directly testable functions; the frame-construction glue below is a thin
-- shell around them.

local ADDON_NAME = ...
LocalGearAdvisorNS = LocalGearAdvisorNS or {}
local NS = LocalGearAdvisorNS
local L = NS.L

NS.Minimap = NS.Minimap or {}
local M = NS.Minimap

local BUTTON_SIZE = 31
-- Keeps the icon mostly overlapping the minimap ring, the same convention
-- long-established minimap button addons use.
local BUTTON_RADIUS = BUTTON_SIZE / 2 - 3
local DEFAULT_ANGLE = 220
local DEFAULT_MINIMAP_RADIUS = 80

--------------------------------------------------------------------------
-- Pure geometry: independently testable without any WoW frame at all.

-- WoW's Lua 5.1 runtime always ships math.atan2; this fallback only exists
-- so the module still loads (with reduced but still-correct precision) on a
-- hypothetical host without it, never exercised on retail WoW today.
local atan2 = math.atan2 or function(y, x)
  if x == nil then x = 0 end
  if x > 0 then return math.atan(y / x) end
  if x < 0 and y >= 0 then return math.atan(y / x) + math.pi end
  if x < 0 and y < 0 then return math.atan(y / x) - math.pi end
  if y > 0 then return math.pi / 2 end
  if y < 0 then return -math.pi / 2 end
  return 0
end
M.Atan2 = atan2

-- Angle 0 = due east of the minimap center, increasing counter-clockwise,
-- matching standard math.cos/math.sin convention.
function M.Position(angleDegrees, radius)
  local radians = math.rad(angleDegrees)
  return radius * math.cos(radians), radius * math.sin(radians)
end

function M.AngleFromXY(dx, dy)
  if dx == 0 and dy == 0 then return 0 end
  local degrees = math.deg(atan2(dy, dx))
  if degrees < 0 then degrees = degrees + 360 end
  return degrees
end

function M.CurrentRadius()
  local minimapRadius = DEFAULT_MINIMAP_RADIUS
  if Minimap and Minimap.GetWidth then
    local ok, width = pcall(Minimap.GetWidth, Minimap)
    if ok and type(width) == "number" and width > 0 then
      minimapRadius = width / 2
    end
  end
  return minimapRadius + BUTTON_RADIUS
end

M.BUTTON_SIZE = BUTTON_SIZE
M.BUTTON_RADIUS = BUTTON_RADIUS
M.DEFAULT_ANGLE = DEFAULT_ANGLE

--------------------------------------------------------------------------
-- SavedVariables-backed state. Lives in LocalGearAdvisorSettings (session/
-- UI preferences only -- never the imported-profile DB or its one-step undo
-- snapshot, so toggling the minimap or resizing the window can never
-- interact with the import transaction contract in Import.lua).

local function EnsureSettings()
  if type(LocalGearAdvisorSettings) ~= "table" then
    LocalGearAdvisorSettings = {}
  end
  return LocalGearAdvisorSettings
end
NS.EnsureSettings = NS.EnsureSettings or EnsureSettings

local function SavedAngle()
  local settings = EnsureSettings()
  local angle = settings.minimapAngle
  if type(angle) ~= "number" or angle ~= angle then return DEFAULT_ANGLE end
  return angle % 360
end

local function SavedShown()
  local settings = EnsureSettings()
  if settings.minimapShown == nil then return true end
  return settings.minimapShown == true
end

--------------------------------------------------------------------------
-- Frame construction

local button
local dragging = false

local function Reposition()
  if not button then return end
  local angle = SavedAngle()
  local x, y = M.Position(angle, M.CurrentRadius())
  button:ClearAllPoints()
  button:SetPoint("CENTER", Minimap, "CENTER", x, y)
end
M.Reposition = Reposition

function M.SetAngle(angleDegrees)
  local settings = EnsureSettings()
  settings.minimapAngle = angleDegrees % 360
  Reposition()
end

function M.GetAngle()
  return SavedAngle()
end

local function OnUpdateDrag(self)
  if not dragging then return end
  if not (Minimap and Minimap.GetCenter and GetCursorPosition) then return end
  local scale = (self.GetEffectiveScale and self:GetEffectiveScale()) or 1
  if type(scale) ~= "number" or scale == 0 then scale = 1 end
  local mx, my = GetCursorPosition()
  mx, my = mx / scale, my / scale
  local cx, cy = Minimap:GetCenter()
  if type(cx) ~= "number" or type(cy) ~= "number" then return end
  M.SetAngle(M.AngleFromXY(mx - cx, my - cy))
end
M._OnUpdateDrag = OnUpdateDrag

local function OnDragStart(self)
  dragging = true
  self:SetScript("OnUpdate", OnUpdateDrag)
end

local function OnDragStop(self)
  dragging = false
  self:SetScript("OnUpdate", nil)
end

local function OnClick(self, mouseButton)
  if mouseButton == "LeftButton" and NS.UI and NS.UI.Toggle then
    NS.UI.Toggle()
  end
end

local function OnEnter(self)
  if not GameTooltip then return end
  GameTooltip:SetOwner(self, "ANCHOR_LEFT")
  GameTooltip:AddLine(L.minimapTooltipTitle)
  GameTooltip:AddLine(L.minimapTooltipHint, 0.6, 0.6, 0.6)
  GameTooltip:Show()
end

local function OnLeave(self)
  if GameTooltip then GameTooltip:Hide() end
end

function M.SetShown(shown)
  local settings = EnsureSettings()
  settings.minimapShown = shown == true
  if button then
    if shown then button:Show() else button:Hide() end
  end
end

function M.IsShown()
  if button then return button:IsShown() == true end
  return SavedShown()
end

-- Idempotent: called on load and safe to call again (e.g. from a future
-- /reload-free settings toggle) without creating a second button.
function M.Create()
  if button then return button end
  if not Minimap or not CreateFrame then return nil end

  button = CreateFrame("Button", "LocalGearAdvisorMinimapButton", Minimap)
  button:SetSize(BUTTON_SIZE, BUTTON_SIZE)
  button:SetFrameStrata("MEDIUM")
  button:SetFrameLevel((Minimap.GetFrameLevel and Minimap:GetFrameLevel() or 0) + 8)
  button:SetMovable(true)
  button:EnableMouse(true)
  button:RegisterForDrag("LeftButton")
  button:RegisterForClicks("LeftButtonUp")

  local icon = button:CreateTexture(nil, "BACKGROUND")
  icon:SetTexture("Interface\\Icons\\INV_Misc_Gear_01")
  icon:SetSize(20, 20)
  icon:SetPoint("CENTER", 0, 0)
  icon:SetMask("Interface\\Minimap\\UI-Minimap-Background")
  button.icon = icon

  local border = button:CreateTexture(nil, "OVERLAY")
  border:SetTexture("Interface\\Minimap\\MiniMap-TrackingBorder")
  border:SetSize(54, 54)
  border:SetPoint("TOPLEFT", 0, 0)
  button.border = border

  button:SetScript("OnDragStart", OnDragStart)
  button:SetScript("OnDragStop", OnDragStop)
  button:SetScript("OnClick", OnClick)
  button:SetScript("OnEnter", OnEnter)
  button:SetScript("OnLeave", OnLeave)

  Reposition()
  if SavedShown() then button:Show() else button:Hide() end

  return button
end

function M.GetButton()
  return button
end
