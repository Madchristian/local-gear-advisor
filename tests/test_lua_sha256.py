"""Correctness proof (real Lua 5.1 execution via lupa) for the addon's pure-Lua
SHA-256 implementation. WoW's Lua 5.1 runtime has no bit32/bitlib, so Sha256.lua
must be arithmetic-only; this cross-checks it against Python's hashlib for many
inputs (including padding boundary lengths and a real transport payload) rather
than trusting a single hand-typed vector.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from lupa.lua51 import LuaRuntime

from local_gear_advisor.import_codec import encode_profile_transport
from local_gear_advisor.state import ProfileItem, ProfileRecord, normalize_identity

SHA256_SOURCE = (Path(__file__).parents[1] / "addon" / "LocalGearAdvisor" / "Sha256.lua").read_text(
    encoding="utf-8"
)


def _runtime() -> LuaRuntime:
    rt = LuaRuntime(unpack_returned_tuples=True)
    rt.execute(SHA256_SOURCE)
    return rt


def _lua_sha256_hex(rt: LuaRuntime, text: str) -> str:
    fn = rt.eval("function(s) return LocalGearAdvisorNS.Sha256Hex(s) end")
    return fn(text)


@pytest.mark.parametrize(
    "message",
    [
        "",
        "a",
        "abc",
        "The quick brown fox jumps over the lazy dog",
        "x" * 55,
        "x" * 56,
        "x" * 57,
        "x" * 63,
        "x" * 64,
        "x" * 65,
        "x" * 119,
        "x" * 120,
        "x" * 121,
        "0123456789" * 100,
        "a" * 10_000,
    ],
)
def test_matches_python_hashlib_across_padding_boundaries(message: str) -> None:
    rt = _runtime()
    expected = hashlib.sha256(message.encode("ascii")).hexdigest()
    assert _lua_sha256_hex(rt, message) == expected


def test_digest_is_lowercase_64_char_hex() -> None:
    rt = _runtime()
    digest = _lua_sha256_hex(rt, "some payload text")
    assert len(digest) == 64
    assert digest == digest.lower()
    assert all(c in "0123456789abcdef" for c in digest)


def test_matches_real_python_generated_transport_payload_digest() -> None:
    baseline_gear = {
        slot: None
        for slot in (
            "head",
            "neck",
            "shoulder",
            "back",
            "chest",
            "wrist",
            "hands",
            "waist",
            "legs",
            "feet",
            "finger1",
            "finger2",
            "trinket1",
            "trinket2",
            "main_hand",
            "off_hand",
        )
    }
    record = ProfileRecord(
        identity=normalize_identity(
            region="eu", realm="ExampleRealm", name="Testchar", spec_id=262
        ),
        character_class="shaman",
        spec="elemental",
        level=90,
        race="orc",
        talents="CYQA...",
        trait_systems={"omnium_talents": "100:1/200:1"},
        baseline_gear=baseline_gear,
        fight_style="Patchwerk",
        baseline_dps=123456.789,
        simc_version="1205-01",
        simc_revision="5a982a3",
        game_version="12.0.7.68887",
        dbc_source="Live",
        profile_hash="a" * 64,
        generated_at=1_785_573_600,
        items=(
            ProfileItem(
                options=",id=200101",
                item_id=200101,
                item_name="Ring of Testing",
                fingerprint="b" * 64,
                best_slot="finger2",
                candidate_dps=126281.234,
                delta_percent=2.5,
                iterations=2500,
            ),
        ),
    )
    text = encode_profile_transport(record)
    magic, digest, payload = text.split(":", 2)
    assert magic == "LGA2"

    rt = _runtime()
    assert _lua_sha256_hex(rt, payload) == digest
