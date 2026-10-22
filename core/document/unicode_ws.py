"""
core/document/unicode_ws.py — Zero-width character steganography for plain text.

Encodes each payload byte as 8 bits using three zero-width Unicode characters:
  - U+200B (ZWSP, Zero-Width Space)   = bit 0
  - U+200C (ZWNJ, Zero-Width Non-Joiner) = bit 1
  - U+200D (ZWJ, Zero-Width Joiner)   = byte separator marker

The encoded characters are inserted after every space in the carrier text.
The output looks completely identical in any text viewer.

WARNING: Some platforms (WhatsApp, Twitter, Instagram, some email clients)
strip zero-width characters. This method is safe for: files, web pages,
PDF content, DOCX body text, direct binary storage.

Wire format embedded in text:
  After each space: [8 ZW chars representing one byte][ZWJ separator]
  [ZWW][ZWW][ZWW][ZWW][ZWW][ZWW][ZWW][ZWW][ZWJ]
         bit7   |   bit6   |  ...  |  bit0  | sep

Special carrier: if carrier has no spaces, inserts at every 10th character.
"""
import hashlib
import struct

import numpy as np

from core.base import BaseEncoder
from core.bits import validate_payload_not_empty

ZWSP = "\u200B"   # zero-width space — encodes bit 0
ZWNJ = "\u200C"   # zero-width non-joiner — encodes bit 1
ZWJ  = "\u200D"   # zero-width joiner — byte separator

HEADER_BYTES = 4  # 4-byte big-endian uint32 length header
MAX_PAYLOAD = 10_000_000
_ZERO_WIDTH = (ZWSP, ZWNJ, ZWJ)


def _read_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Carrier is not valid UTF-8 text") from None


class UnicodeWSEncoder(BaseEncoder):
    name = "unicode"
    supported_extensions = [".txt"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        text = _read_text(carrier_bytes)
        n_spaces = text.count(" ")
        if n_spaces == 0:
            n_spaces = len(text) // 10
        # Each byte requires 9 ZW chars (8 bits + ZWJ separator)
        # Each insertion point holds 9 ZW chars = 1 byte
        return max(0, n_spaces - HEADER_BYTES)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, key: str | None = None, **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        text = _read_text(carrier_bytes)
        if any(ch in text for ch in _ZERO_WIDTH):
            raise ValueError("Carrier already contains zero-width characters; they would corrupt decoding")
        n_spaces = text.count(" ")
        use_nth = n_spaces > 0

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(
                f"Payload too large: {len(payload_bytes)} bytes, "
                f"text capacity: {cap} bytes ({n_spaces} insertion points)"
            )

        data = struct.pack(">I", len(payload_bytes)) + bytes(payload_bytes)
        # Build byte-level chunks: each byte → a 9-char ZW sequence
        byte_chunks = _encode_bytes_to_chunks(data)  # list of 9-char strings

        points = self._insertion_points(text, use_nth)
        if len(points) < len(byte_chunks):
            raise ValueError("Carrier does not provide enough insertion points for payload")

        ranked = self._rank_points(text, points, key)
        selected = sorted(ranked[:len(byte_chunks)])
        selected_set = set(selected)

        result = []
        chunk_idx = 0

        for char_count, ch in enumerate(text):
            result.append(ch)
            if chunk_idx < len(byte_chunks) and (char_count in selected_set):
                result.append(byte_chunks[chunk_idx])
                chunk_idx += 1

        return "".join(result).encode("utf-8")

    def _insertion_points(self, text: str, use_nth: bool) -> list[int]:
        points = []
        if use_nth:
            for i, ch in enumerate(text):
                if ch == " ":
                    points.append(i)
        else:
            for i in range(9, len(text), 10):
                points.append(i)
        return points

    def _rank_points(self, text: str, points: list[int], key: str | None) -> list[int]:
        scores = []
        punct = set(".,;:!?")
        for p in points:
            prev_ch = text[p - 1] if p > 0 else ""
            next_ch = text[p + 1] if (p + 1) < len(text) else ""
            score = 0.0

            # Prefer natural boundary-like spots where invisible markers blend better.
            if prev_ch in punct:
                score += 3.0
            if next_ch and next_ch.isupper():
                score += 1.0
            if prev_ch.isalnum() and next_ch.isalnum():
                score += 0.8
            if prev_ch.isdigit() or next_ch.isdigit():
                score -= 0.5

            scores.append(score)

        seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big") if key else 0
        rng = np.random.default_rng(seed)
        ties = rng.random(len(points), dtype=np.float32)

        # Highest score first, tie-broken by seeded noise for diffusion.
        order = np.lexsort((ties, -np.array(scores, dtype=np.float32)))
        return [points[i] for i in order]

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        text = _read_text(stego_bytes)

        # Extract only zero-width characters
        zw_chars = [ch for ch in text if ch in (ZWSP, ZWNJ, ZWJ)]
        return _decode_zwchars_to_bytes(zw_chars)


def _encode_bytes_to_chunks(data: bytes) -> list[str]:
    """Encode each byte as a 9-char ZW string (8 bit chars + ZWJ separator)."""
    chunks = []
    for byte in data:
        chars = []
        for bit_pos in range(7, -1, -1):
            bit = (byte >> bit_pos) & 1
            chars.append(ZWNJ if bit else ZWSP)
        chars.append(ZWJ)  # byte separator
        chunks.append("".join(chars))
    return chunks


def _decode_zwchars_to_bytes(zw_chars: list[str]) -> bytes:
    """Decode zero-width character sequence back to bytes."""
    bytes_found = []
    current_bits: list[int] = []

    for ch in zw_chars:
        if ch == ZWJ:
            if len(current_bits) == 8:
                val = 0
                for b in current_bits:
                    val = (val << 1) | b
                bytes_found.append(val)
            current_bits = []
        elif ch == ZWSP:
            current_bits.append(0)
        elif ch == ZWNJ:
            current_bits.append(1)

    if len(bytes_found) < HEADER_BYTES:
        raise ValueError("No hidden payload found in text (zero-width characters missing)")

    length = struct.unpack(">I", bytes(bytes_found[:HEADER_BYTES]))[0]
    if length == 0 or length > MAX_PAYLOAD:
        raise ValueError(f"Invalid text payload length: {length}")

    payload = bytes(bytes_found[HEADER_BYTES:HEADER_BYTES + length])
    if len(payload) < length:
        raise ValueError("Incomplete payload data in text")
    return payload
