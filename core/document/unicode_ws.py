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
import io
from core.base import BaseEncoder

ZWSP = "\u200B"   # zero-width space — encodes bit 0
ZWNJ = "\u200C"   # zero-width non-joiner — encodes bit 1
ZWJ  = "\u200D"   # zero-width joiner — byte separator

HEADER_BYTES = 4  # 4-byte big-endian uint32 length header


class UnicodeWSEncoder(BaseEncoder):
    name = "unicode"
    supported_extensions = [".txt"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        text = carrier_bytes.decode("utf-8", errors="replace")
        n_spaces = text.count(" ")
        if n_spaces == 0:
            n_spaces = len(text) // 10
        # Each byte requires 9 ZW chars (8 bits + ZWJ separator)
        # Each insertion point holds 9 ZW chars = 1 byte
        return max(0, n_spaces - HEADER_BYTES)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        text = carrier_bytes.decode("utf-8", errors="replace")
        n_spaces = text.count(" ")
        use_nth = n_spaces > 0

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(
                f"Payload too large: {len(payload_bytes)} bytes, "
                f"text capacity: {cap} bytes ({n_spaces} insertion points)"
            )

        import struct
        data = struct.pack(">I", len(payload_bytes)) + payload_bytes
        # Build byte-level chunks: each byte → a 9-char ZW sequence
        byte_chunks = _encode_bytes_to_chunks(data)  # list of 9-char strings

        result = []
        chunk_idx = 0
        char_count = 0

        for ch in text:
            result.append(ch)
            if chunk_idx < len(byte_chunks):
                insertion_point = (ch == " ") if use_nth else (char_count % 10 == 9)
                if insertion_point:
                    result.append(byte_chunks[chunk_idx])
                    chunk_idx += 1
            char_count += 1

        return "".join(result).encode("utf-8")

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        text = stego_bytes.decode("utf-8", errors="replace")

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
    import struct
    bytes_found = []
    current_bits = []

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
    if length == 0 or length > 10_000_000:
        raise ValueError(f"Invalid text payload length: {length}")

    payload = bytes(bytes_found[HEADER_BYTES:HEADER_BYTES + length])
    if len(payload) < length:
        raise ValueError("Incomplete payload data in text")
    return payload
