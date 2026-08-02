"""Minimal WoW API mock so Core.lua can be executed by a real Lua runtime
(lupa) rather than only parsed. Static string/AST assertions cannot prove
runtime behavior like cross-character isolation; this harness drives the
addon's real tooltip hook end to end against synthetic SavedVariables-shaped
data, exactly as WoW would call it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from lupa.lua51 import LuaRuntime

_ADDON_DIR = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"
LOCALIZATION_SOURCE = (_ADDON_DIR / "Localization.lua").read_text(encoding="utf-8")
SHA256_SOURCE = (_ADDON_DIR / "Sha256.lua").read_text(encoding="utf-8")
CORE_SOURCE = (_ADDON_DIR / "Core.lua").read_text(encoding="utf-8")
IMPORT_SOURCE = (_ADDON_DIR / "Import.lua").read_text(encoding="utf-8")

_SLOT_IDS = {
    "head": 1,
    "neck": 2,
    "shoulder": 3,
    "back": 15,
    "chest": 5,
    "wrist": 9,
    "hands": 10,
    "waist": 6,
    "legs": 7,
    "feet": 8,
    "finger1": 11,
    "finger2": 12,
    "trinket1": 13,
    "trinket2": 14,
    "main_hand": 16,
    "off_hand": 17,
}


def item_link(item_id: int) -> str:
    """A minimal 16-field synthetic item link: itemID plus zeroed bonus/gem/
    crafted-stat counts, so ItemOptions() renders it as ",id=<item_id>"."""
    return "item:" + ":".join([str(item_id)] + ["0"] * 15)


@dataclass(frozen=True)
class RuntimeIdentity:
    name: str
    class_file: str
    race_file: str
    level: int
    spec_id: int
    realm_name: str
    region_id: int
    talents: str
    omnium_entries: tuple[tuple[int, int], ...] = ()
    spec_index: int = 1
    game_version: tuple[str, str] = ("12.0.7", "68887")
    baseline_gear_links: dict[str, str | None] = field(default_factory=dict)


class LuaHarness:
    def __init__(
        self,
        *,
        results_lua: str,
        identity: RuntimeIdentity,
        now: int,
        locale: str = "enUS",
        secret_values: frozenset[str] = frozenset(),
        include_import: bool = False,
    ) -> None:
        self.rt = LuaRuntime(unpack_returned_tuples=True)
        self._hooks: list = []
        g = self.rt.globals()

        g.GetLocale = lambda: locale
        g.issecretvalue = lambda value: value in secret_values
        g.time = lambda: now
        g.geterrorhandler = lambda: lambda *_args: None

        hooks = self._hooks

        class _TooltipDataProcessor:
            @staticmethod
            def AddTooltipPostCall(_item_type, callback):
                hooks.append(callback)

        g.TooltipDataProcessor = _TooltipDataProcessor
        self.rt.execute("Enum = {TooltipDataType = {Item = 1}}")
        g.strsplit = lambda delim, s: tuple(s.split(delim))
        g.CreateFrame = lambda *_args: self.rt.eval(
            "{RegisterEvent = function() end, SetScript = function() end}"
        )

        g.UnitName = lambda _unit: identity.name
        g.UnitClass = lambda _unit: ("Display", identity.class_file)
        g.UnitRace = lambda _unit: ("Display", identity.race_file)
        g.UnitLevel = lambda _unit: identity.level
        g.GetRealmName = lambda: identity.realm_name
        g.GetCurrentRegion = lambda: identity.region_id
        g.GetBuildInfo = lambda: identity.game_version

        links_by_slot_id = {
            _SLOT_IDS[slot]: link for slot, link in identity.baseline_gear_links.items()
        }
        g.GetInventoryItemLink = lambda _unit, slot_id: links_by_slot_id.get(slot_id)

        class _SpecAPI:
            @staticmethod
            def GetSpecialization():
                return identity.spec_index

            @staticmethod
            def GetSpecializationInfo(_index):
                return identity.spec_id

        g.C_SpecializationInfo = _SpecAPI

        class _ClassTalents:
            @staticmethod
            def GetActiveConfigID():
                return 1

        g.C_ClassTalents = _ClassTalents

        node_ids = [10 + 10 * i for i in range(len(identity.omnium_entries))]
        node_info = dict(zip(node_ids, identity.omnium_entries, strict=True))
        rt = self.rt

        class _Traits:
            @staticmethod
            def GenerateImportString(_config_id):
                return identity.talents

            @staticmethod
            def GetConfigIDBySystemID(_system_id):
                return 1

            @staticmethod
            def GetConfigInfo(_config_id):
                return rt.eval("{treeIDs = {1}}")

            @staticmethod
            def GetTreeNodes(_tree_id):
                return rt.table_from(node_ids)

            @staticmethod
            def GetNodeInfo(_config_id, node_id):
                entry = node_info.get(node_id)
                if entry is None:
                    return None
                entry_id, rank = entry
                return rt.eval(
                    f"{{ranksPurchased=1, activeEntry={{entryID={entry_id}, rank={rank}}}}}"
                )

        g.C_Traits = _Traits

        self.rt.execute(results_lua)
        self.rt.execute(LOCALIZATION_SOURCE)
        if include_import:
            self.rt.execute(SHA256_SOURCE)
        self.rt.execute(CORE_SOURCE)
        if include_import:
            self.rt.execute(IMPORT_SOURCE)

    def set_results(self, results_lua: str) -> None:
        self.rt.execute(results_lua)

    def set_db(self, db_lua: str) -> None:
        self.rt.execute(db_lua)

    def decode_profile_transport(self, text: str):
        """Real Import.lua decode. Returns (True, profile) or (False, err)."""
        fn = self.rt.eval(
            """
            function(text)
              local profile, err = LocalGearAdvisorNS.DecodeProfileTransport(text)
              if profile == nil then return false, err end
              return true, profile
            end
            """
        )
        return fn(text)

    def apply_profile_transport(self, profile):
        """Real Import.lua transactional apply. Returns (True, nil) or (False, err)."""
        fn = self.rt.eval(
            """
            function(profile)
              local ok, err = LocalGearAdvisorNS.ApplyProfileTransport(profile)
              return ok, err
            end
            """
        )
        return fn(profile)

    def undo_last_import(self):
        fn = self.rt.eval("function() return LocalGearAdvisorNS.UndoLastImport() end")
        return fn()

    def delete_db_profile(self, identity_key: str):
        fn = self.rt.eval("function(k) return LocalGearAdvisorNS.DeleteDbProfile(k) end")
        return fn(identity_key)

    def identity_key(self, profile) -> str:
        fn = self.rt.eval(
            "function(profile) return LocalGearAdvisorNS.Schema.IdentityKey(profile) end"
        )
        return fn(profile)

    def db_profile_count(self) -> int:
        fn = self.rt.eval(
            "function() if LocalGearAdvisorDB == nil then return 0 end "
            "return #(LocalGearAdvisorDB.profiles) end"
        )
        return fn()

    def db_is_nil(self) -> bool:
        fn = self.rt.eval("function() return LocalGearAdvisorDB == nil end")
        return fn()

    def show_tooltip(self, item_link_text: str) -> list[str]:
        mock = self.rt.eval(
            """
            function(itemLink)
              local lines = {}
              return {
                GetItem = function(self) return "MockItem", itemLink end,
                AddLine = function(self, text) lines[#lines+1] = "L:" .. tostring(text) end,
                AddDoubleLine = function(self, left, right)
                  lines[#lines+1] = tostring(left) .. "=" .. tostring(right)
                end,
                HookScript = function(self, event, fn) end,
                Hide = function(self) end,
                recordedLines = lines,
              }
            end
            """
        )
        tooltip = mock(item_link_text)
        for hook in self._hooks:
            hook(tooltip)
        return list(tooltip.recordedLines.values())
