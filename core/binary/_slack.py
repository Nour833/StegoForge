"""core/binary/_slack.py — shared slack-space embedding for executable carriers.

ELF and PE embedding differ only in how "slack" regions are found and in the
magic that tags the payload; everything else (2-bit-per-byte packing, region
ordering, key shuffling, bounds checks) lives here once.

Wire format: ``[4-byte magic][4-byte big-endian length][payload]`` written
MSB-first, 2 bits per slack byte (the low two bits), regions visited cheapest
first (padding before notes / overlay), optionally shuffled by the key.

Compatibility note: region ordering and the key shuffle
(``numpy.random.default_rng``) are exactly those of StegoForge <= 1.1.5.
"""
from __future__ import annotations

import hashlib
import struct

import numpy as np

from core.base import BaseEncoder
from core.bits import (
    bits_to_bytes_np,
    bytes_to_bits_np,
    pack_depth_chunks_np,
    unpack_depth_chunks_np,
    validate_payload_not_empty,
)
from core.config import get_config

BITS_PER_BYTE = 2
HEADER_FMT = ">4sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
Region = tuple[int, int, str]


def assert_regions_in_bounds(regions: list[Region], data_len: int) -> None:
    for start, end, _ in regions:
        if start < 0 or end < 0 or start > data_len or end > data_len or end < start:
            raise ValueError("Corrupted region table (out of bounds)")


def ordered_regions(regions: list[Region], cost_of) -> list[tuple[int, int]]:
    """Cheapest region first; ties prefer larger, then earlier regions."""
    weighted = []
    for start, end, kind in regions:
        if end > start:
            weighted.append((cost_of(kind), -(end - start), start, end))
    weighted.sort()
    return [(start, end) for _, _, start, end in weighted]


def ordered_positions(regions: list[tuple[int, int]], key: str | None, need: int) -> np.ndarray:
    """First ``need`` byte offsets of the slack visit order (all of them if keyed, then truncated)."""
    if not regions:
        return np.empty(0, dtype=np.int64)
    if not key:
        parts: list[np.ndarray] = []
        have = 0
        for start, end in regions:
            take = min(end - start, need - have)
            if take <= 0:
                break
            parts.append(np.arange(start, start + take, dtype=np.int64))
            have += take
        return np.concatenate(parts) if parts else np.empty(0, dtype=np.int64)

    total = sum(end - start for start, end in regions)
    if total > get_config().max_keyed_samples:
        raise ValueError(f"Slack area too large for a keyed embed ({total:,} bytes); use no key")
    arr = np.concatenate([np.arange(start, end, dtype=np.int64) for start, end in regions])
    seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    np.random.default_rng(seed).shuffle(arr)
    return arr[:need]


class SlackEncoder(BaseEncoder):
    """Base class for slack-space carriers. Subclasses set the class attributes."""

    magic: bytes = b""
    kind: str = ""                     # human name used in messages ("ELF", "PE")
    signature: bytes = b""             # file signature the carrier must start with

    @staticmethod
    def parse_regions(data: bytes) -> list[Region]:  # pragma: no cover - overridden
        raise NotImplementedError

    @staticmethod
    def region_cost(kind: str) -> float:  # pragma: no cover - overridden
        raise NotImplementedError

    def _regions(self, data: bytes) -> list[tuple[int, int]]:
        regions = self.parse_regions(data)
        assert_regions_in_bounds(regions, len(data))
        return ordered_regions(regions, self.region_cost)

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        total = sum(end - start for start, end in self._regions(carrier_bytes))
        return max(0, (total * BITS_PER_BYTE // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        if not carrier_bytes.startswith(self.signature):
            raise ValueError(f"Input is not a valid {self.kind} binary")
        validate_payload_not_empty(payload_bytes)
        regions = self._regions(carrier_bytes)
        total = sum(end - start for start, end in regions)
        cap = max(0, (total * BITS_PER_BYTE // 8) - HEADER_SIZE)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, {self.kind} capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, self.magic, len(payload_bytes)) + bytes(payload_bytes)
        chunks = pack_depth_chunks_np(bytes_to_bits_np(data), BITS_PER_BYTE)
        positions = ordered_positions(regions, kwargs.get("key"), len(chunks))
        if len(positions) < len(chunks):
            raise ValueError(f"{self.kind} slack regions were insufficient to embed payload")

        out = np.frombuffer(bytearray(carrier_bytes), dtype=np.uint8).copy()
        out[positions] = (out[positions] & np.uint8(0xFF ^ ((1 << BITS_PER_BYTE) - 1))) | chunks
        return out.tobytes()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        if not stego_bytes.startswith(self.signature):
            raise ValueError(f"Input is not a valid {self.kind} binary")
        regions = self._regions(stego_bytes)
        total = sum(end - start for start, end in regions)
        key = kwargs.get("key")
        buf = np.frombuffer(stego_bytes, dtype=np.uint8)
        low = np.uint8((1 << BITS_PER_BYTE) - 1)

        header_groups = HEADER_SIZE * 8 // BITS_PER_BYTE
        if total < header_groups:
            raise ValueError(f"No embedded {self.kind} payload header found")
        positions = ordered_positions(regions, key, header_groups)
        header = bits_to_bytes_np(unpack_depth_chunks_np(buf[positions] & low, BITS_PER_BYTE))
        magic, length = struct.unpack(HEADER_FMT, header)
        if magic != self.magic or length <= 0:
            raise ValueError(f"No StegoForge {self.kind} payload found")

        groups = (HEADER_SIZE + length) * 8 // BITS_PER_BYTE
        if groups > total:
            raise ValueError(f"Incomplete {self.kind} payload data")
        positions = ordered_positions(regions, key, groups)
        bits = unpack_depth_chunks_np(buf[positions] & low, BITS_PER_BYTE)
        return bits_to_bytes_np(bits[HEADER_SIZE * 8:])
