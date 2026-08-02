"""Cross-language proof that the Python identity normalizer matches
Core.lua's Tokenize() exactly. state.py normalizes realm names when writing
the aggregate; Core.lua re-derives the same token from GetRealmName() at
runtime. If the two algorithms ever diverged, real accented/punctuated realm
names (e.g. "Aggra (Português)") could silently mismatch and hide a
character's data. Verified here against the real Lua source, not an
assumption about what it does.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from lupa.lua51 import LuaRuntime

from local_gear_advisor.state import _wow_tokenize

CORE_SOURCE = (Path(__file__).parents[1] / "addon" / "LocalGearAdvisor" / "Core.lua").read_text(
    encoding="utf-8"
)


def _lua_tokenize_function():
    marker = "local REGION_NAMES"
    assert marker in CORE_SOURCE
    prefix = CORE_SOURCE.split(marker, 1)[0]
    rt = LuaRuntime()
    g = rt.globals()
    g.issecretvalue = lambda _value: False
    g.GetLocale = lambda: "enUS"
    # A game client links against a fixed C runtime and cannot depend on
    # each player's OS locale for deterministic parsing; pin "C" explicitly
    # so string.lower() only touches ASCII A-Z, never mangling multi-byte
    # UTF-8 continuation bytes the way an arbitrary locale's tolower() can
    # (verified: the machine's default locale here does mangle them).
    rt.execute('os.setlocale("C")')
    rt.execute(prefix + "\n_G.DebugTokenize = Tokenize\n")
    tokenize = g.DebugTokenize

    def call(value: str) -> str:
        result = tokenize(value)
        return result[0] if isinstance(result, tuple) else result

    return call


_LUA_TOKENIZE = _lua_tokenize_function()


@pytest.mark.parametrize(
    "realm_name",
    [
        "TestRealm",
        "testrealm",
        "Twisting Nether",
        "Az'Shara",
        "Aggra (Português)",
        "Die Aldor",
        "Confrérie du Thorium",
        "Realm ",
        " Realm",
        "!!!Realm!!!",
        "Realm-Name",
        "Realm_Name",
        "100% Pure Saurfang",
        "Bloodhoof",
        "Königreich",
    ],
)
def test_python_tokenize_matches_lua_tokenize_exactly(realm_name: str) -> None:
    assert _wow_tokenize(realm_name) == _LUA_TOKENIZE(realm_name)


def test_all_symbols_tokenizes_to_empty_on_both_sides() -> None:
    assert _wow_tokenize("!!!") == ""
    assert _LUA_TOKENIZE("!!!") == ""
