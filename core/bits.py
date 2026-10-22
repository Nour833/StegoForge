"""core/bits.py — shared bit-manipulation helpers (single source of truth).

Wire format used by every encoder: MSB-first bits. The ``*_np`` helpers work on
``uint8`` arrays of 0/1 values and are what the encoders use; the list-based
helpers remain for callers that work on small chunks.
"""
from __future__ import annotations

import numpy as np

from core.errors import DepthError, EmptyPayloadError

MIN_DEPTH = 1
MAX_DEPTH = 4


def validate_depth(depth: int) -> int:
    """Validate LSB depth. Returns depth or raises DepthError."""
    if not isinstance(depth, int) or isinstance(depth, bool):
        raise DepthError(f"Depth must be an integer 1-4, got {depth!r}")
    if not MIN_DEPTH <= depth <= MAX_DEPTH:
        raise DepthError(f"Depth must be 1-4, got {depth}")
    return depth


def validate_payload_not_empty(payload: bytes, *, what: str = "Payload") -> None:
    """Reject empty payloads with a clear error (encode-side policy)."""
    if len(payload) == 0:
        raise EmptyPayloadError(f"{what} is empty — refusing to embed zero-length payload")


# ── numpy-native helpers ──────────────────────────────────────────────────────

def bytes_to_bits_np(data: bytes) -> np.ndarray:
    """Expand bytes to an MSB-first ``uint8`` array of 0/1."""
    if not data:
        return np.empty(0, dtype=np.uint8)
    return np.unpackbits(np.frombuffer(bytes(data), dtype=np.uint8))


def bits_to_bytes_np(bits: np.ndarray) -> bytes:
    """Pack an MSB-first 0/1 array to bytes, ignoring a trailing partial byte."""
    n_full = (len(bits) // 8) * 8
    if n_full == 0:
        return b""
    return np.packbits(np.asarray(bits[:n_full], dtype=np.uint8)).tobytes()


def pack_depth_chunks_np(bits: np.ndarray, depth: int) -> np.ndarray:
    """Group bits into ``depth``-bit values (MSB-first), zero-padding the tail.

    The tail is padded so a decoder, which always reads whole ``depth``-bit
    groups, stays in sync with the encoder (the historic depth-3/4 bug).
    """
    validate_depth(depth)
    bits = np.asarray(bits, dtype=np.uint8)
    pad = (-len(bits)) % depth
    if pad:
        bits = np.concatenate([bits, np.zeros(pad, dtype=np.uint8)])
    weights = (1 << np.arange(depth - 1, -1, -1)).astype(np.uint16)
    return (bits.reshape(-1, depth).astype(np.uint16) @ weights).astype(np.uint8)


def unpack_depth_chunks_np(values: np.ndarray, depth: int, nbits: int | None = None) -> np.ndarray:
    """Inverse of :func:`pack_depth_chunks_np`: expand values to MSB-first bits."""
    validate_depth(depth)
    shifts = np.arange(depth - 1, -1, -1, dtype=np.uint8)
    bits = ((np.asarray(values, dtype=np.uint8)[:, None] >> shifts) & 1).reshape(-1).astype(np.uint8)
    return bits if nbits is None else bits[:nbits]


# ── list-based helpers (small chunks, legacy callers) ─────────────────────────

def bytes_to_bits(data: bytes) -> list[int]:
    """Expand bytes to an MSB-first bit list."""
    return bytes_to_bits_np(data).tolist()


def bits_to_bytes(bits: list[int] | np.ndarray) -> bytes:
    """Pack MSB-first bits to bytes, ignoring a trailing incomplete byte."""
    return bits_to_bytes_np(np.asarray(bits, dtype=np.uint8))


def bits_to_int(bits: list[int] | np.ndarray) -> int:
    """Pack a short bit chunk (<=8 bits) to an int, MSB-first."""
    val = 0
    for b in bits:
        val = (val << 1) | (1 if b else 0)
    return val


def pack_depth_chunks(bits: list[int], depth: int) -> list[int]:
    """List form of :func:`pack_depth_chunks_np`."""
    return pack_depth_chunks_np(np.asarray(bits, dtype=np.uint8), depth).tolist()
