"""Behavioral proof (real Lua 5.1 execution via lupa) that Import.lua's strict
transport decoder accepts genuine Python-generated transport vectors and
rejects tampered/malformed ones -- byte for byte the same security contract
import_codec.py already proves on the Python side, but now on the exact Lua
parser the addon runs. Never loadstring/load/eval: Import.lua only tokenizes
and validates, so a malicious payload is data, never code.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from lupa.lua51 import LuaRuntime

from local_gear_advisor.import_codec import TRANSPORT_MAGIC, _encode_value, encode_profile_transport
from local_gear_advisor.state import ProfileItem, ProfileRecord, normalize_identity, profile_to_dict

ADDON = Path(__file__).parents[1] / "addon" / "LocalGearAdvisor"
_SOURCES = [
    (ADDON / "Localization.lua").read_text(encoding="utf-8"),
    (ADDON / "Sha256.lua").read_text(encoding="utf-8"),
    (ADDON / "Core.lua").read_text(encoding="utf-8"),
    (ADDON / "Import.lua").read_text(encoding="utf-8"),
]

_BASELINE_SLOTS = (
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


def _record(
    *,
    region: str = "eu",
    realm: str = "ExampleRealm",
    name: str = "Cöa",
    spec_id: int = 262,
    item_name: str | None = "Ring of Testing",
    delta_percent: float = 2.345678,
) -> ProfileRecord:
    baseline_gear = {slot: None for slot in _BASELINE_SLOTS}
    baseline_gear["head"] = ",id=100001"
    return ProfileRecord(
        identity=normalize_identity(region=region, realm=realm, name=name, spec_id=spec_id),
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
                item_name=item_name,
                fingerprint="b" * 64,
                best_slot="finger2",
                candidate_dps=126281.234,
                delta_percent=delta_percent,
                iterations=2500,
            ),
        ),
    )


def _bs(text: str) -> str:
    data = text.encode("utf-8")
    return f"{len(data)}:{data.hex()}"


def _sign(payload: str) -> str:
    digest = hashlib.sha256(payload.encode("ascii")).hexdigest()
    return f"{TRANSPORT_MAGIC}:{digest}:{payload}"


def _runtime() -> LuaRuntime:
    rt = LuaRuntime(unpack_returned_tuples=True)
    g = rt.globals()
    # Core.lua only needs enough of the WoW environment to finish loading
    # (locale table + the tooltip-hook registration guard); the actual
    # tooltip runtime behavior is exercised separately in test_addon_runtime.py.
    g.GetLocale = lambda: "enUS"
    g.geterrorhandler = lambda: lambda *_args: None
    g.CreateFrame = lambda *_args: rt.eval(
        "{RegisterEvent = function() end, SetScript = function() end}"
    )
    rt.execute("Enum = {TooltipDataType = {Item = 1}}")
    rt.execute("TooltipDataProcessor = {AddTooltipPostCall = function(_type, _cb) end}")
    for source in _SOURCES:
        rt.execute(source)
    return rt


def _decode(rt: LuaRuntime, text: str):
    fn = rt.eval(
        """
        function(text)
          local profile, err = LocalGearAdvisorNS.DecodeProfileTransport(text)
          if profile == nil then
            return false, err
          end
          return true, profile
        end
        """
    )
    return fn(text)


def test_decodes_a_real_python_generated_transport_into_the_flat_profile_shape() -> None:
    record = _record()
    text = encode_profile_transport(record)
    rt = _runtime()

    ok, profile = _decode(rt, text)

    assert ok is True
    assert profile["region"] == "eu"
    assert profile["server"] == "examplerealm"
    assert profile["characterName"] == "Cöa"
    assert profile["specID"] == 262
    assert profile["class"] == "shaman"
    assert profile["level"] == 90
    assert profile["profileHash"] == "a" * 64
    item = profile["items"][",id=200101"]
    assert item["itemID"] == 200101
    assert item["name"] == "Ring of Testing"
    assert item["status"] == "simulated"
    assert profile["baselineGear"]["head"] == ",id=100001"
    assert profile["baselineGear"]["neck"] is False


def test_decodes_null_item_name_and_empty_baseline_slots_as_false_not_nil() -> None:
    record = _record(item_name=None)
    text = encode_profile_transport(record)
    rt = _runtime()

    ok, profile = _decode(rt, text)

    assert ok is True
    item = profile["items"][",id=200101"]
    assert item["name"] is False
    for slot in _BASELINE_SLOTS:
        if slot != "head":
            assert profile["baselineGear"][slot] is False


def test_round_trip_preserves_unicode_realm_and_name() -> None:
    record = _record(realm="Blackmoore", name="Cöa")
    text = encode_profile_transport(record)
    rt = _runtime()

    ok, profile = _decode(rt, text)

    assert ok is True
    assert profile["characterName"] == "Cöa"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda text: "LGA9" + text[len(TRANSPORT_MAGIC) :],
        lambda text: text[:-5],
        lambda text: text + "\x80",
    ],
)
def test_rejects_wrong_version_truncated_and_non_ascii(mutate) -> None:
    text = encode_profile_transport(_record())
    rt = _runtime()

    ok, err = _decode(rt, mutate(text))

    assert ok is False
    assert isinstance(err, str) and err != ""


def test_rejects_tampered_digest() -> None:
    text = encode_profile_transport(_record())
    magic, digest, payload = text.split(":", 2)
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    tampered = f"{magic}:{flipped}:{payload}"
    rt = _runtime()

    ok, err = _decode(rt, tampered)

    assert ok is False
    assert "digest" in err


def test_rejects_tampered_payload_with_matching_length() -> None:
    text = encode_profile_transport(_record())
    magic, digest, payload = text.split(":", 2)
    index = payload.index(":") + 1
    flipped_char = "1" if payload[index] != "1" else "2"
    tampered_payload = payload[:index] + flipped_char + payload[index + 1 :]
    tampered = f"{magic}:{digest}:{tampered_payload}"
    rt = _runtime()

    ok, err = _decode(rt, tampered)

    assert ok is False
    assert "digest" in err


def test_rejects_trailing_data_after_payload() -> None:
    text = encode_profile_transport(_record())
    magic, digest, payload = text.split(":", 2)
    trailing_payload = payload + "d" + _bs("a") + "i1e" + "e"
    trailing_digest = hashlib.sha256(trailing_payload.encode("ascii")).hexdigest()
    tampered = f"{magic}:{trailing_digest}:{trailing_payload}"
    rt = _runtime()

    ok, err = _decode(rt, tampered)

    assert ok is False


def test_rejects_duplicate_dict_keys() -> None:
    # "class" is a real top-level field; repeating it violates strict
    # ascending order (key <= previousKey) exactly like a true duplicate would.
    payload = "d" + _bs("class") + _bs("shaman") + _bs("class") + _bs("shaman") + "e"
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_non_canonical_key_order() -> None:
    # "spec" sorts after "class"; listing it first breaks strict ascending order.
    payload = "d" + _bs("spec") + _bs("elemental") + _bs("class") + _bs("shaman") + "e"
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_malformed_length_prefix_with_leading_zero() -> None:
    payload = "d06:" + "726567696f6e" + "e"
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_non_hex_bytestring_content() -> None:
    payload = "d" + _bs("class") + "1:zz" + "e"
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_nan_and_inf_like_real_tokens() -> None:
    rt = _runtime()
    for token in ("fnane", "finfe"):
        payload = "d" + _bs("baselineDps") + token + "e"
        ok, err = _decode(rt, _sign(payload))
        assert ok is False


def test_rejects_excessive_integer_digits() -> None:
    payload = "d" + _bs("level") + "i" + "9" * 40 + "e" + "e"
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_oversize_transport() -> None:
    huge = _sign("d" + "1:61" * 1_200_000 + "e")
    rt = _runtime()

    ok, err = _decode(rt, huge)

    assert ok is False


def test_rejects_payload_that_is_not_a_dict() -> None:
    rt = _runtime()

    ok, err = _decode(rt, _sign("i1e"))

    assert ok is False


def test_rejects_unexpected_top_level_field() -> None:
    payload_dict = profile_to_dict(_record())
    payload_dict["unexpectedField"] = "x"
    payload = _encode_value(payload_dict)
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_missing_required_field() -> None:
    payload_dict = profile_to_dict(_record())
    del payload_dict["profileHash"]
    payload = _encode_value(payload_dict)
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_semantically_invalid_profile_via_shared_core_validator() -> None:
    payload_dict = profile_to_dict(_record())
    payload_dict["level"] = 999
    payload = _encode_value(payload_dict)
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_wrong_item_options_id_via_shared_core_validator() -> None:
    payload_dict = profile_to_dict(_record())
    payload_dict["items"][0]["itemId"] = 999999
    payload = _encode_value(payload_dict)
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_duplicate_item_option_keys() -> None:
    payload_dict = profile_to_dict(_record())
    duplicate = dict(payload_dict["items"][0])
    payload_dict["items"] = [payload_dict["items"][0], duplicate]
    payload = _encode_value(payload_dict)
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_rejects_invalid_utf8_bytes_in_a_string_field() -> None:
    # 0xC0 is not a valid UTF-8 lead byte at all (overlong-encoding prefix).
    payload = "d" + _bs("class") + "1:c0" + "e"
    rt = _runtime()

    ok, err = _decode(rt, _sign(payload))

    assert ok is False


def test_accepts_valid_two_byte_utf8_inside_a_known_field() -> None:
    record = _record(name="Cöa")
    text = encode_profile_transport(record)
    rt = _runtime()

    ok, profile = _decode(rt, text)

    assert ok is True
    assert profile["characterName"] == "Cöa"
