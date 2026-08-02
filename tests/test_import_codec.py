import hashlib
from dataclasses import replace

import pytest

from local_gear_advisor.import_codec import (
    TRANSPORT_MAGIC,
    TransportError,
    _encode_value,
    decode_profile_transport,
    encode_profile_transport,
)
from local_gear_advisor.state import (
    ProfileItem,
    ProfileRecord,
    StateError,
    normalize_identity,
    profile_to_dict,
)

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
    delta_percent: float = 2.345678,
    item_name: str | None = "Ring of Testing",
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
    """Encode one transport bytestring token: <len>:<hex bytes>, matching _encode_bytestring."""
    data = text.encode("utf-8")
    return f"{len(data)}:{data.hex()}"


def _sign(payload: str) -> str:
    digest = hashlib.sha256(payload.encode("ascii")).hexdigest()
    return f"{TRANSPORT_MAGIC}:{digest}:{payload}"


def test_transport_starts_with_unique_version_marker() -> None:
    text = encode_profile_transport(_record())
    assert text.startswith(f"{TRANSPORT_MAGIC}:")


def test_transport_is_pure_ascii() -> None:
    text = encode_profile_transport(_record())
    assert text.isascii()


def test_encode_is_deterministic() -> None:
    record = _record()
    assert encode_profile_transport(record) == encode_profile_transport(record)


def test_encoder_never_emits_a_transport_larger_than_its_own_decoder_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import local_gear_advisor.import_codec as codec

    monkeypatch.setattr(codec, "_MAX_TRANSPORT_CHARS", 100)

    with pytest.raises(TransportError, match="size"):
        codec.encode_profile_transport(_record())


def test_round_trip_preserves_all_fields_including_unicode_and_none_item_name() -> None:
    record = _record(item_name=None)
    text = encode_profile_transport(record)
    decoded = decode_profile_transport(text)
    assert decoded == record


def test_round_trip_preserves_negative_delta() -> None:
    record = _record(delta_percent=-5.5)
    decoded = decode_profile_transport(encode_profile_transport(record))
    assert decoded.items[0].delta_percent == pytest.approx(-5.5)


def test_decode_rejects_unknown_version_marker() -> None:
    text = encode_profile_transport(_record())
    tampered = "LGA9" + text[len(TRANSPORT_MAGIC) :]
    with pytest.raises(TransportError, match="version"):
        decode_profile_transport(tampered)


def test_decode_rejects_tampered_digest() -> None:
    text = encode_profile_transport(_record())
    magic, digest, payload = text.split(":", 2)
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    tampered = f"{magic}:{flipped}:{payload}"
    with pytest.raises(TransportError, match="digest"):
        decode_profile_transport(tampered)


def test_decode_rejects_tampered_payload_with_matching_length() -> None:
    text = encode_profile_transport(_record())
    magic, digest, payload = text.split(":", 2)
    # Flip one hex nibble inside the first bytestring field without changing overall length.
    index = payload.index(":") + 1
    flipped_char = "1" if payload[index] != "1" else "2"
    tampered_payload = payload[:index] + flipped_char + payload[index + 1 :]
    tampered = f"{magic}:{digest}:{tampered_payload}"
    with pytest.raises(TransportError, match="digest"):
        decode_profile_transport(tampered)


def test_decode_rejects_oversize_transport() -> None:
    huge = _sign("d" + "1:61" * 1_200_000 + "e")
    with pytest.raises(TransportError, match="size"):
        decode_profile_transport(huge)


def test_decode_rejects_truncated_payload() -> None:
    text = encode_profile_transport(_record())
    with pytest.raises(TransportError):
        decode_profile_transport(text[:-5])


def test_decode_rejects_trailing_data_after_payload() -> None:
    text = encode_profile_transport(_record())
    magic, digest, payload = text.split(":", 2)
    trailing_payload = payload + "d" + _bs("a") + "i1e" + "e"
    trailing_digest = hashlib.sha256(trailing_payload.encode("ascii")).hexdigest()
    tampered = f"{magic}:{trailing_digest}:{trailing_payload}"
    with pytest.raises(TransportError, match="trailing"):
        decode_profile_transport(tampered)


def test_decode_rejects_duplicate_dict_keys() -> None:
    payload = "d" + _bs("region") + _bs("eu") + _bs("region") + _bs("us") + "e"
    with pytest.raises(TransportError, match="duplicate|order"):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_non_canonical_key_order() -> None:
    payload = "d" + _bs("server") + _bs("eu") + _bs("region") + _bs("us") + "e"
    with pytest.raises(TransportError, match="order"):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_malformed_length_prefix_with_leading_zero() -> None:
    payload = "d06:" + "726567696f6e" + "e"
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_non_hex_bytestring_content() -> None:
    payload = "d" + _bs("region") + "1:zz" + "e"
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_nan_like_real_token() -> None:
    payload = "d" + _bs("x") + "fnane" + "e"
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_inf_like_real_token() -> None:
    payload = "d" + _bs("x") + "finfe" + "e"
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_excessive_integer_digits() -> None:
    payload = "d" + _bs("x") + "i" + "9" * 40 + "e" + "e"
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_excessive_nesting_depth() -> None:
    payload = "d" + _bs("x") + ("l" * 200) + ("e" * 200) + "e"
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_payload_that_is_not_a_dict() -> None:
    payload = "i1e"
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_semantically_invalid_profile_via_shared_validator() -> None:
    payload_dict = profile_to_dict(_record())
    payload_dict["level"] = 999  # exceeds state.py's _MAX_CHARACTER_LEVEL
    payload = _encode_value(payload_dict)
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_decode_rejects_non_ascii_transport() -> None:
    text = encode_profile_transport(_record())
    with pytest.raises(TransportError):
        decode_profile_transport(text + "ö")


def test_decode_rejects_wrong_item_options_id_via_shared_validator() -> None:
    payload_dict = profile_to_dict(_record())
    payload_dict["items"][0]["itemId"] = 999999
    payload = _encode_value(payload_dict)
    with pytest.raises(TransportError):
        decode_profile_transport(_sign(payload))


def test_encoder_rejects_whitespace_only_baseline_gear_before_emitting_transport() -> None:
    record = _record()
    baseline = dict(record.baseline_gear)
    baseline["head"] = " "

    with pytest.raises(StateError, match="baselineGear.head"):
        encode_profile_transport(replace(record, baseline_gear=baseline))


def test_encoder_rejects_nbsp_only_baseline_gear_before_emitting_transport() -> None:
    record = _record()
    baseline = dict(record.baseline_gear)
    baseline["head"] = "\N{NO-BREAK SPACE}"

    with pytest.raises(StateError, match="baselineGear.head"):
        encode_profile_transport(replace(record, baseline_gear=baseline))
