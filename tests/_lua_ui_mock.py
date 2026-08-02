"""Generic WoW widget mock so UI.lua and Minimap.lua can be executed by a
real Lua runtime (lupa) end to end -- clicked, dragged, typed into -- rather
than only parsed or source-grepped. Implements just enough of the Frame/
Button/EditBox/Texture/FontString API surface for the addon's real
CreateFrame-based code to run unmodified; anything not given real semantics
below is a harmless no-op (chainable, like the real widget methods), so the
addon file never has to be changed to accommodate the mock.
"""

from __future__ import annotations

from pathlib import Path

from lupa.lua51 import LuaRuntime

_ADDON_DIR = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"
LOCALIZATION_SOURCE = (_ADDON_DIR / "Localization.lua").read_text(encoding="utf-8")
SHA256_SOURCE = (_ADDON_DIR / "Sha256.lua").read_text(encoding="utf-8")
CORE_SOURCE = (_ADDON_DIR / "Core.lua").read_text(encoding="utf-8")
IMPORT_SOURCE = (_ADDON_DIR / "Import.lua").read_text(encoding="utf-8")
MINIMAP_SOURCE = (_ADDON_DIR / "Minimap.lua").read_text(encoding="utf-8")
UI_SOURCE = (_ADDON_DIR / "UI.lua").read_text(encoding="utf-8")

# Generic mock widget system, executed once before any addon source. Real
# semantics are implemented only where a test needs to observe them; every
# other method call is a harmless recorded/ignored no-op.
_WOW_UI_MOCK_LUA = r"""
MOCK = { allFrames = {}, cursor = { x = 0, y = 0 } }

local FrameMethods = {}
FrameMethods.__index = function(t, key)
  local explicit = rawget(FrameMethods, key)
  if explicit ~= nil then return explicit end
  return function(...) end
end

function FrameMethods:SetSize(w, h) self.width, self.height = w, h end
function FrameMethods:SetWidth(w) self.width = w end
function FrameMethods:SetHeight(h) self.height = h end
function FrameMethods:GetWidth() return self.width or 0 end
function FrameMethods:GetHeight() return self.height or 0 end

function FrameMethods:SetPoint(point, relTo, relPoint, x, y)
  if relTo ~= nil and type(relTo) ~= "table" then
    -- SetPoint(point, x, y) shorthand (relative to parent)
    relPoint, relTo, x, y = point, nil, relTo, relPoint
  end
  self.points[#self.points + 1] = {
    point = point, relTo = relTo, relPoint = relPoint, x = x, y = y,
  }
end
function FrameMethods:ClearAllPoints() self.points = {} end
function FrameMethods:GetPoint(index)
  local p = self.points[index or 1]
  if not p then return nil end
  return p.point, p.relTo, p.relPoint or p.point, p.x or 0, p.y or 0
end
function FrameMethods:GetNumPoints() return #self.points end

function FrameMethods:GetCenter()
  return self.centerX or 0, self.centerY or 0
end

function FrameMethods:SetScript(event, fn) self.scripts[event] = fn end
function FrameMethods:GetScript(event) return self.scripts[event] end
function FrameMethods:HookScript(event, fn)
  local existing = self.scripts[event]
  self.scripts[event] = function(...)
    if existing then existing(...) end
    return fn(...)
  end
end

function FrameMethods:Show()
  self.shownFlag = true
  local s = self.scripts.OnShow
  if s then s(self) end
end
function FrameMethods:Hide()
  self.shownFlag = false
  local s = self.scripts.OnHide
  if s then s(self) end
end
function FrameMethods:IsShown() return self.shownFlag == true end
function FrameMethods:IsVisible() return self.shownFlag == true end

function FrameMethods:SetText(text) self.text = text end
function FrameMethods:GetText() return self.text or "" end
function FrameMethods:SetChecked(v) self.checked = v end
function FrameMethods:GetChecked() return self.checked end

function FrameMethods:SetAlpha(a) self.alpha = a end
function FrameMethods:GetAlpha() return self.alpha or 1 end
function FrameMethods:SetScale(s) self.scale = s end
function FrameMethods:GetScale() return self.scale or 1 end
function FrameMethods:GetEffectiveScale() return self.effectiveScale or self.scale or 1 end
function FrameMethods:SetParent(p) self.parent = p end
function FrameMethods:GetParent() return self.parent end
function FrameMethods:SetFrameStrata(s) self.strata = s end
function FrameMethods:GetFrameStrata() return self.strata end
function FrameMethods:SetFrameLevel(l) self.level = l end
function FrameMethods:GetFrameLevel() return self.level or 0 end
function FrameMethods:EnableMouse(v) self.mouseEnabled = v end
function FrameMethods:IsMouseEnabled() return self.mouseEnabled == true end
function FrameMethods:SetMovable(v) self.movable = v end
function FrameMethods:IsMovable() return self.movable == true end
function FrameMethods:SetUserPlaced(v) self.userPlaced = v end
function FrameMethods:SetClampedToScreen(v) self.clamped = v end
function FrameMethods:RegisterForDrag(...) self.dragButtons = { ... } end
function FrameMethods:RegisterForClicks(...) self.clickButtons = { ... } end
function FrameMethods:StartMoving() self.moving = true end
function FrameMethods:StopMovingOrSizing() self.moving = false end

function FrameMethods:SetMask(path) self.mask = path end
function FrameMethods:SetTexture(path) self.texturePath = path end
function FrameMethods:SetColorTexture(r, g, b, a) self.colorTexture = { r, g, b, a } end
function FrameMethods:SetVertexColor(r, g, b, a) self.vertexColor = { r, g, b, a } end
function FrameMethods:SetTextColor(r, g, b, a) self.textColor = { r, g, b, a } end

function FrameMethods:SetBackdrop(t) self.backdrop = t end
function FrameMethods:SetBackdropColor(r, g, b, a) self.backdropColor = { r, g, b, a } end
function FrameMethods:SetBackdropBorderColor(r, g, b, a)
  self.backdropBorderColor = { r, g, b, a }
end

function FrameMethods:SetFontObject(f) self.fontObject = f end
function FrameMethods:SetTextInsets(left, right, top, bottom)
  self.textInsets = { left, right, top, bottom }
end
function FrameMethods:SetJustifyH(j) self.justifyH = j end
function FrameMethods:SetJustifyV(j) self.justifyV = j end

function FrameMethods:SetMultiLine(v) self.multiLine = v end
function FrameMethods:SetAutoFocus(v) self.autoFocus = v end
function FrameMethods:SetMaxLetters(n) self.maxLetters = n end
function FrameMethods:SetCursorPosition(n) self.cursorPos = n end
function FrameMethods:HighlightText() self.highlighted = true end
function FrameMethods:SetFocus() self.focused = true end
function FrameMethods:ClearFocus() self.focused = false end
function FrameMethods:IsFocused() return self.focused == true end

function FrameMethods:SetEnabled(v) self.enabledFlag = v end
function FrameMethods:Enable() self.enabledFlag = true end
function FrameMethods:Disable() self.enabledFlag = false end
function FrameMethods:IsEnabled()
  if self.enabledFlag == nil then return true end
  return self.enabledFlag == true
end

function FrameMethods:SetScrollChild(c) self.scrollChild = c end
function FrameMethods:GetScrollChild() return self.scrollChild end

function FrameMethods:RegisterEvent(e)
  self.events[e] = true
end
function FrameMethods:UnregisterEvent(e)
  self.events[e] = nil
end

function FrameMethods:CreateTexture(name, layer)
  local tex = MOCK.NewRegion("Texture")
  tex.layer = layer
  table.insert(self.children, tex)
  return tex
end

function FrameMethods:CreateFontString(name, layer, template)
  local fs = MOCK.NewRegion("FontString")
  fs.layer = layer
  fs.text = ""
  table.insert(self.children, fs)
  return fs
end

-- Every field a getter reads via `self.field or default` (or a plain
-- `return self.field`) MUST be a real, present value from construction on --
-- otherwise an UNSET field falls through FrameMethods.__index's catch-all
-- (since Lua's __index cannot tell "reading a data field" apart from
-- "looking up an unimplemented method") and resolves to the generic stub
-- FUNCTION instead of nil, which is truthy and silently wins the `or`.
-- Fields only ever compared with `==` (shownFlag, enabledFlag, ...) are not
-- strictly vulnerable to this, but are given real defaults anyway so they
-- match real WoW widget defaults (visible + enabled unless told otherwise).
function MOCK.NewRegion(kind)
  local instance = {
    __kind = kind, points = {}, scripts = {}, children = {}, events = {},
    width = 0, height = 0, text = "", alpha = 1, scale = 1, level = 0,
    centerX = 0, centerY = 0, shownFlag = true, enabledFlag = true,
    focused = false, movable = false, checked = false,
  }
  setmetatable(instance, FrameMethods)
  table.insert(MOCK.allFrames, instance)
  return instance
end

function CreateFrame(kind, name, parent, template)
  local instance = MOCK.NewRegion(kind)
  instance.frameType = kind
  instance.name = name
  instance.parent = parent
  instance.template = template
  if name ~= nil and name ~= "" then
    _G[name] = instance
  end
  return instance
end

UIParent = MOCK.NewRegion("Frame")
UISpecialFrames = {}
SlashCmdList = {}

Minimap = MOCK.NewRegion("Minimap")
Minimap.width = 140
Minimap.centerX = 400
Minimap.centerY = 300

GameTooltip = MOCK.NewRegion("GameTooltip")
function GameTooltip:SetOwner(owner, anchor)
  self.owner, self.anchor = owner, anchor
  self.lines = {}
end
function GameTooltip:AddLine(text, r, g, b)
  self.lines = self.lines or {}
  table.insert(self.lines, tostring(text))
end

function GetCursorPosition()
  return MOCK.cursor.x, MOCK.cursor.y
end
function MOCK.SetCursor(x, y)
  MOCK.cursor.x, MOCK.cursor.y = x, y
end

-- Test-driving helpers: simulate exactly what the real WoW client does when
-- a Button is clicked/dragged, so tests exercise the addon's real OnClick/
-- OnDragStart/OnUpdate/OnDragStop handlers instead of calling into private
-- state directly.
function MOCK.Click(frame, mouseButton)
  local handler = frame.scripts.OnClick
  if handler then handler(frame, mouseButton or "LeftButton") end
end

function MOCK.MouseDown(frame, mouseButton)
  local handler = frame.scripts.OnMouseDown
  if handler then handler(frame, mouseButton or "LeftButton") end
end

function MOCK.Enter(frame)
  local handler = frame.scripts.OnEnter
  if handler then handler(frame) end
end

function MOCK.Leave(frame)
  local handler = frame.scripts.OnLeave
  if handler then handler(frame) end
end

function MOCK.DragStart(frame)
  local handler = frame.scripts.OnDragStart
  if handler then handler(frame) end
end

function MOCK.DragUpdate(frame)
  local handler = frame.scripts.OnUpdate
  if handler then handler(frame, 0.016) end
end

function MOCK.DragStop(frame)
  local handler = frame.scripts.OnDragStop
  if handler then handler(frame) end
end
"""


class UIHarness:
    """Loads Localization/Sha256/Core/Import/Minimap/UI against the generic
    widget mock, plus enough player-identity WoW API surface for Core.lua to
    load and (optionally) resolve tooltips."""

    def __init__(
        self,
        *,
        results_lua: str,
        locale: str = "enUS",
        now: int = 2_000_000_000,
    ) -> None:
        self.rt = LuaRuntime(unpack_returned_tuples=True)
        g = self.rt.globals()

        g.GetLocale = lambda: locale
        g.issecretvalue = lambda value: False
        g.time = lambda: now
        g.geterrorhandler = lambda: lambda *_args: None
        g.strsplit = lambda delim, s: tuple(s.split(delim))

        # Core.lua's tooltip-invalidation event frame and hook registration
        # only need to not error; UI/Minimap behavior is what these tests
        # actually exercise.
        self.rt.execute("Enum = {TooltipDataType = {Item = 1}}")
        self.rt.execute("TooltipDataProcessor = {AddTooltipPostCall = function(_type, _cb) end}")

        self.rt.execute(_WOW_UI_MOCK_LUA)

        # Real WoW passes (addonName, addonTable) as `...` when loading each
        # addon file; each of these sources reads `local ADDON_NAME = ...`,
        # so it must never silently resolve to nil the way a bare execute()
        # would leave it.
        self.rt.execute(results_lua)
        self.rt.execute(LOCALIZATION_SOURCE)
        self.rt.execute(SHA256_SOURCE)
        self.rt.execute(CORE_SOURCE, "LocalGearAdvisor")
        self.rt.execute(IMPORT_SOURCE, "LocalGearAdvisor")
        self.rt.execute(MINIMAP_SOURCE, "LocalGearAdvisor")
        self.rt.execute(UI_SOURCE, "LocalGearAdvisor")

    def eval(self, expr: str):
        return self.rt.eval(expr)

    def execute(self, chunk: str):
        return self.rt.execute(chunk)

    def call(self, expr: str, *args):
        fn = self.rt.eval(expr)
        return fn(*args)

    def set_db(self, db_lua: str) -> None:
        self.rt.execute(db_lua)

    def method(self, obj, name: str, *args):
        """Call a Lua method with proper `self` binding. lupa's attribute
        access on a Lua table returns the raw function, not a bound method
        (there is no Python-side equivalent of Lua's `obj:method()` colon
        sugar), so `obj.IsShown()` from Python silently calls the function
        with zero arguments and errors inside on `self`. Always go through
        this helper instead of calling a widget method directly from Python.
        """
        fn = self.rt.eval("function(o, n, ...) return o[n](o, ...) end")
        return fn(obj, name, *args)

    def is_shown(self, frame) -> bool:
        return self.method(frame, "IsShown") is True

    def is_enabled(self, frame) -> bool:
        return self.method(frame, "IsEnabled") is True

    def get_text(self, frame) -> str:
        return self.method(frame, "GetText")

    def click(self, frame, mouse_button: str = "LeftButton") -> None:
        self.rt.eval("function(f, b) MOCK.Click(f, b) end")(frame, mouse_button)

    def mouse_down(self, frame, mouse_button: str = "LeftButton") -> None:
        self.rt.eval("function(f, b) MOCK.MouseDown(f, b) end")(frame, mouse_button)

    def enter(self, frame) -> None:
        self.rt.eval("function(f) MOCK.Enter(f) end")(frame)

    def leave(self, frame) -> None:
        self.rt.eval("function(f) MOCK.Leave(f) end")(frame)

    def drag_start(self, frame) -> None:
        self.rt.eval("function(f) MOCK.DragStart(f) end")(frame)

    def drag_update(self, frame) -> None:
        self.rt.eval("function(f) MOCK.DragUpdate(f) end")(frame)

    def drag_stop(self, frame) -> None:
        self.rt.eval("function(f) MOCK.DragStop(f) end")(frame)

    def type_text(self, frame, text: str) -> None:
        """Simulates a player editing an EditBox: sets the text (as a paste
        would) and fires OnTextChanged exactly as the real WoW EditBox widget
        does on every keystroke/paste -- FrameMethods:SetText alone does not,
        since the generic mock has no real text-input simulation."""
        self.method(frame, "SetText", text)
        handler = self.rt.eval("function(f) return f.scripts.OnTextChanged end")(frame)
        if handler is not None:
            handler(frame, True)

    def set_cursor(self, x: float, y: float) -> None:
        self.rt.eval("function(x, y) MOCK.SetCursor(x, y) end")(x, y)

    def set_minimap_center(self, x: float, y: float) -> None:
        self.rt.execute(f"Minimap.centerX, Minimap.centerY = {x}, {y}")

    def set_minimap_width(self, width: float) -> None:
        self.rt.execute(f"Minimap.width = {width}")
