"""
core/image/wetpaper.py - Reed-Solomon wet paper style redundancy wrapper.

This module wraps already-encrypted payload bytes with error-correction coding
so payload recovery can tolerate moderate lossy transformations.
"""
import struct

MAGIC = b"WETP"
HEADER_FMT = ">4sBII"  # magic, nsym, original_len, encoded_len
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def _require_reedsolo():
    try:
        from reedsolo import RSCodec  # type: ignore
        return RSCodec
    except Exception as exc:
        raise ValueError(
            "wet paper mode requires reedsolo. Install with: pip install reedsolo"
        ) from exc


def encode_wet_paper(payload_bytes: bytes, redundancy_bytes: int = 32) -> bytes:
    RSCodec = _require_reedsolo()
    nsym = int(max(4, min(128, redundancy_bytes)))
    rsc = RSCodec(nsym)
    encoded = bytes(rsc.encode(payload_bytes))
    header = struct.pack(HEADER_FMT, MAGIC, nsym, len(payload_bytes), len(encoded))
    return header + encoded


def decode_wet_paper(data: bytes) -> tuple[bytes, int, bool]:
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        return data, 0, False

    RSCodec = _require_reedsolo()
    magic, nsym, original_len, encoded_len = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    if magic != MAGIC:
        return data, 0, False

    blob = data[HEADER_SIZE:HEADER_SIZE + encoded_len]
    if len(blob) < encoded_len:
        raise ValueError("Corrupted wet paper payload header")

    rsc = RSCodec(nsym)
    decoded = rsc.decode(blob)

    corrected = 0
    if isinstance(decoded, tuple):
        msg = bytes(decoded[0])
        if len(decoded) >= 3 and hasattr(decoded[2], "__len__"):
            corrected = len(decoded[2])
    else:
        msg = bytes(decoded)

    if original_len <= 0 or original_len > len(msg):
        raise ValueError("Invalid wet paper decoded length")

    return msg[:original_len], corrected, True


def is_wet_paper_blob(data: bytes) -> bool:
    return len(data) >= 4 and data[:4] == MAGIC
