"""Single-profile transport codec for the desktop GUI <-> in-game addon copy/paste flow.

Encodes exactly one ProfileRecord into a versioned, pure-ASCII, self-integrity-checked
blob the user copies out of the desktop GUI and pastes into the addon's Import tab.

Format (all bytes are 7-bit ASCII)::

    LGA2:<64 lowercase hex sha256 of payload>:<payload>

``payload`` is a small custom canonical grammar (a bencode variant) chosen because it
needs no external library, is unambiguous to parse with hard bounds checked as parsing
proceeds, and never uses loadstring/load/eval on either side of the transport:

    value      := integer | real | bytestring | none | list | dict
    integer    := 'i' ('0' | ['1'-'9'] digit*) 'e'
    real       := 'f' '-'? digit+ '.' digit+ 'e'   -- always fixed-point; never scientific
    bytestring := decimal_len ':' hex_chars        -- hex_chars is exactly 2*decimal_len hex digits
    none       := 'n'
    list       := 'l' value* 'e'
    dict       := 'd' (bytestring value)* 'e'      -- keys sorted strictly ascending, no duplicates

String bytes are hex-encoded (rather than embedded raw) so the entire transport, including
umlauts and any other UTF-8 content, stays pure ASCII end to end -- safe to paste through a
WoW EditBox and any clipboard manager without re-encoding risk.

The decoded payload dict has exactly the same shape as state.profile_to_dict()/
state.parse_profile_dict() already validate for the on-disk aggregate, so this module
reuses that single semantic validator rather than re-implementing the schema.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import re
from typing import Any

from .state import ProfileRecord, StateError, parse_profile_dict, profile_to_dict

TRANSPORT_MAGIC = "LGA2"

_DIGEST_HEX_LEN = 64
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX_RE = re.compile(r"^[0-9a-f]*$")
_INT_RE = re.compile(r"^(0|[1-9][0-9]*)$")
_REAL_RE = re.compile(r"^-?[0-9]+\.[0-9]+$")

_MAX_TRANSPORT_CHARS = 256 * 1024
_MAX_PARSE_DEPTH = 8
_MAX_CONTAINER_ITEMS = 20_000
_MAX_STRING_BYTES = 1_000_000
_MAX_LENGTH_PREFIX_DIGITS = 9
_MAX_INT_DIGITS = 20
_MAX_REAL_DIGITS = 64


class TransportError(RuntimeError):
    """Fail-closed: import transport is missing, malformed, tampered, or invalid."""


def _format_real(value: float) -> str:
    if not math.isfinite(value):
        raise TransportError(f"cannot encode a non-finite number: {value!r}")
    return f"{value:.6f}"


def _encode_bytestring(text: str) -> str:
    data = text.encode("utf-8")
    return f"{len(data)}:{data.hex()}"


def _encode_value(value: Any) -> str:
    if value is None:
        return "n"
    if isinstance(value, bool):
        raise TransportError("booleans are not representable in the transport grammar")
    if isinstance(value, int):
        return f"i{value}e"
    if isinstance(value, float):
        return f"f{_format_real(value)}e"
    if isinstance(value, str):
        return _encode_bytestring(value)
    if isinstance(value, list):
        return "l" + "".join(_encode_value(item) for item in value) + "e"
    if isinstance(value, dict):
        parts: list[str] = []
        for key in sorted(value.keys()):
            if not isinstance(key, str):
                raise TransportError("transport dict keys must be strings")
            parts.append(_encode_bytestring(key))
            parts.append(_encode_value(value[key]))
        return "d" + "".join(parts) + "e"
    raise TransportError(f"unsupported value type for transport encoding: {type(value)!r}")


def encode_profile_transport(record: ProfileRecord) -> str:
    """Deterministically encode one profile as a versioned, integrity-checked transport blob."""
    payload_dict = profile_to_dict(record)
    # Never hand out a blob our own decoder (and the addon's matching decoder) would refuse:
    # round-trip it through the exact same semantic validator used on decode.
    parse_profile_dict(payload_dict)
    payload = _encode_value(payload_dict)
    if not payload.isascii():
        raise TransportError("encoded transport payload is unexpectedly non-ASCII")
    digest = hashlib.sha256(payload.encode("ascii")).hexdigest()
    transport = f"{TRANSPORT_MAGIC}:{digest}:{payload}"
    if len(transport) > _MAX_TRANSPORT_CHARS:
        raise TransportError("transport exceeds the maximum size")
    return transport


class _Decoder:
    __slots__ = ("_text", "_pos", "_len")

    def __init__(self, text: str) -> None:
        self._text = text
        self._pos = 0
        self._len = len(text)

    @property
    def position(self) -> int:
        return self._pos

    def _peek(self) -> str:
        if self._pos >= self._len:
            raise TransportError("transport payload ended unexpectedly")
        return self._text[self._pos]

    def _expect(self, char: str) -> None:
        if self._pos >= self._len or self._text[self._pos] != char:
            raise TransportError(f"expected {char!r} in transport payload")
        self._pos += 1

    def parse_value(self, depth: int) -> Any:
        if depth > _MAX_PARSE_DEPTH:
            raise TransportError("transport payload exceeds the maximum nesting depth")
        char = self._peek()
        if char == "i":
            return self._parse_int()
        if char == "f":
            return self._parse_real()
        if char == "n":
            self._pos += 1
            return None
        if char == "l":
            return self._parse_list(depth)
        if char == "d":
            return self._parse_dict(depth)
        if char.isdigit():
            return self._parse_bytestring()
        raise TransportError(f"unexpected token {char!r} in transport payload")

    def _scan_until(self, terminator: str, *, max_chars: int, what: str) -> str:
        start = self._pos
        while self._pos < self._len and self._text[self._pos] != terminator:
            self._pos += 1
            if self._pos - start > max_chars:
                raise TransportError(f"{what} token is too long")
        if self._pos >= self._len:
            raise TransportError(f"unterminated {what} token")
        body = self._text[start : self._pos]
        self._pos += 1
        return body

    def _parse_int(self) -> int:
        self._expect("i")
        digits = self._scan_until("e", max_chars=_MAX_INT_DIGITS, what="integer")
        if not _INT_RE.fullmatch(digits):
            raise TransportError("malformed integer token")
        return int(digits)

    def _parse_real(self) -> float:
        self._expect("f")
        digits = self._scan_until("e", max_chars=_MAX_REAL_DIGITS, what="real")
        if not _REAL_RE.fullmatch(digits):
            raise TransportError("malformed real token")
        return float(digits)

    def _parse_bytestring(self) -> str:
        length_text = self._scan_until(
            ":", max_chars=_MAX_LENGTH_PREFIX_DIGITS, what="length prefix"
        )
        if not _INT_RE.fullmatch(length_text):
            raise TransportError("malformed length prefix")
        length = int(length_text)
        if length > _MAX_STRING_BYTES:
            raise TransportError("string field exceeds the maximum length")
        hex_len = length * 2
        if self._pos + hex_len > self._len:
            raise TransportError("truncated string field")
        hex_chars = self._text[self._pos : self._pos + hex_len]
        if not _HEX_RE.fullmatch(hex_chars):
            raise TransportError("malformed hex-encoded string field")
        self._pos += hex_len
        try:
            return bytes.fromhex(hex_chars).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TransportError("string field is not valid UTF-8") from exc

    def _parse_list(self, depth: int) -> list[Any]:
        self._expect("l")
        items: list[Any] = []
        while True:
            if self._pos >= self._len:
                raise TransportError("unterminated list")
            if self._text[self._pos] == "e":
                self._pos += 1
                return items
            if len(items) >= _MAX_CONTAINER_ITEMS:
                raise TransportError("list exceeds the maximum item count")
            items.append(self.parse_value(depth + 1))

    def _parse_dict(self, depth: int) -> dict[str, Any]:
        self._expect("d")
        result: dict[str, Any] = {}
        previous_key: str | None = None
        while True:
            if self._pos >= self._len:
                raise TransportError("unterminated dict")
            if self._text[self._pos] == "e":
                self._pos += 1
                return result
            if len(result) >= _MAX_CONTAINER_ITEMS:
                raise TransportError("dict exceeds the maximum field count")
            key = self._parse_bytestring()
            if previous_key is not None and key <= previous_key:
                raise TransportError("dict keys are not in strict canonical ascending order")
            previous_key = key
            result[key] = self.parse_value(depth + 1)


def decode_profile_transport(text: str) -> ProfileRecord:
    """Strictly decode and validate one profile transport blob. Fails closed on any defect."""
    if not isinstance(text, str):
        raise TransportError("transport must be text")
    trimmed = text.strip(" \t\r\n")
    if not trimmed:
        raise TransportError("transport is empty")
    if not trimmed.isascii():
        raise TransportError("transport must be pure ASCII")
    if len(trimmed) > _MAX_TRANSPORT_CHARS:
        raise TransportError("transport exceeds the maximum size")

    prefix = f"{TRANSPORT_MAGIC}:"
    if not trimmed.startswith(prefix):
        raise TransportError("transport has an unrecognized or missing version marker")
    rest = trimmed[len(prefix) :]

    if len(rest) < _DIGEST_HEX_LEN + 1 or rest[_DIGEST_HEX_LEN] != ":":
        raise TransportError("transport is missing a valid integrity digest")
    digest = rest[:_DIGEST_HEX_LEN]
    if not _DIGEST_RE.fullmatch(digest):
        raise TransportError("transport integrity digest is malformed")
    payload = rest[_DIGEST_HEX_LEN + 1 :]
    if not payload:
        raise TransportError("transport payload is empty")

    computed = hashlib.sha256(payload.encode("ascii")).hexdigest()
    if not hmac.compare_digest(computed, digest):
        raise TransportError("transport integrity digest does not match the payload")

    decoder = _Decoder(payload)
    value = decoder.parse_value(depth=1)
    if decoder.position != len(payload):
        raise TransportError("transport payload has trailing data")
    if not isinstance(value, dict):
        raise TransportError("transport payload must be a profile object")

    try:
        return parse_profile_dict(value)
    except StateError as exc:
        raise TransportError(f"transport payload failed schema validation: {exc}") from exc
