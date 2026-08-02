"""Static and runtime proof that locale strings live in their own file and
that Core.lua/UI.lua consume them from there instead of each defining their
own copy (which would drift). Locale selection itself (deDE full, everything
else falls back to enUS) is exercised for real via lupa, not just grepped.
"""

from __future__ import annotations

from pathlib import Path

from luaparser import ast
from lupa.lua51 import LuaRuntime

ADDON = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"
LOCALIZATION_SOURCE = (ADDON / "Localization.lua").read_text(encoding="utf-8")


def _runtime(locale: str) -> LuaRuntime:
    rt = LuaRuntime(unpack_returned_tuples=True)
    rt.globals().GetLocale = lambda: locale
    rt.execute(LOCALIZATION_SOURCE)
    return rt


def test_localization_lua_parses() -> None:
    ast.parse(LOCALIZATION_SOURCE)


def test_core_lua_no_longer_defines_its_own_locale_tables() -> None:
    core = (ADDON / "Core.lua").read_text(encoding="utf-8")
    assert "local L = NS.L" in core
    assert "local SLOT_LABELS = NS.SlotLabels" in core
    assert 'GetLocale() == "deDE" and {' not in core


def test_dede_locale_selects_german_strings() -> None:
    rt = _runtime("deDE")
    L = rt.globals().LocalGearAdvisorNS.L
    assert L.dpsOnly == "Nur offensiver DPS-Vergleich"
    assert L.upgrade == "DPS-Upgrade"
    assert L.downgrade == "DPS-Downgrade"
    assert L.equal == "DPS ungefähr gleich"


def test_enus_locale_selects_english_strings() -> None:
    rt = _runtime("enUS")
    L = rt.globals().LocalGearAdvisorNS.L
    assert L.dpsOnly == "Offensive DPS comparison only"
    assert L.upgrade == "DPS upgrade"


def test_unsupported_locale_falls_back_to_english() -> None:
    for locale in ("frFR", "esES", "zhCN", "ptBR", "ruRU", ""):
        rt = _runtime(locale)
        L = rt.globals().LocalGearAdvisorNS.L
        assert L.dpsOnly == "Offensive DPS comparison only", locale


def test_slot_labels_present_for_both_locales() -> None:
    for locale in ("deDE", "enUS"):
        rt = _runtime(locale)
        labels = rt.globals().LocalGearAdvisorNS.SlotLabels
        assert labels.finger1 == "Ring 1"
        assert labels.finger2 == "Ring 2"
        assert labels.trinket1 is not None
        assert labels.main_hand is not None
