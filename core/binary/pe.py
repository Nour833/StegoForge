"""
core/binary/pe.py - PE section slack/overlay carrier encoder.

Warning: modifying PE binaries can trigger antivirus detections. Use only on
executables you own and are authorized to modify.
"""
from __future__ import annotations

import hashlib
import struct
import numpy as np

from core.base import BaseEncoder

MAGIC = b"SFPE"
HEADER_FMT = ">4sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
BITS_PER_BYTE = 2


class PEEncoder(BaseEncoder):
    name = "pe"
    supported_extensions = [".exe", ".dll", ".bin"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        regions = parse_pe_regions(carrier_bytes)
        total = sum(max(0, end - start) for start, end, _ in regions)
        return max(0, (total * BITS_PER_BYTE // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        if not carrier_bytes.startswith(b"MZ"):
            raise ValueError("Input is not a valid PE binary")

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, PE capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, MAGIC, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)
        out = bytearray(carrier_bytes)
        key = kwargs.get("key")
        positions = _ordered_positions(parse_pe_regions(carrier_bytes), key)

        if len(bits) > len(positions) * BITS_PER_BYTE:
            raise ValueError("PE slack regions were insufficient to embed payload")

        bit_idx = 0
        mask = 0xFF ^ ((1 << BITS_PER_BYTE) - 1)
        for pos in positions:
            if bit_idx >= len(bits):
                break
            chunk = bits[bit_idx:bit_idx + BITS_PER_BYTE]
            while len(chunk) < BITS_PER_BYTE:
                chunk.append(0)
            val = _bits_to_int(chunk)
            out[pos] = (out[pos] & mask) | val
            bit_idx += BITS_PER_BYTE

        if bit_idx < len(bits):
            raise ValueError("PE slack regions were insufficient to embed payload")
        return bytes(out)

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        if not stego_bytes.startswith(b"MZ"):
            raise ValueError("Input is not a valid PE binary")

        regions = parse_pe_regions(stego_bytes)
        positions = _ordered_positions(regions, kwargs.get("key"))

        header_bits_needed = HEADER_SIZE * 8
        bits = []
        for pos in positions:
            if len(bits) >= header_bits_needed:
                break
            v = stego_bytes[pos]
            for b in range(BITS_PER_BYTE - 1, -1, -1):
                bits.append((v >> b) & 1)

        if len(bits) < header_bits_needed:
            raise ValueError("No embedded PE payload header found")

        header = _bits_to_bytes(bits[:header_bits_needed])
        magic, length = struct.unpack(HEADER_FMT, header)
        if magic != MAGIC or length <= 0:
            raise ValueError("No StegoForge PE payload found")

        total_bits = (HEADER_SIZE + length) * 8
        bits = []
        for pos in positions:
            if len(bits) >= total_bits:
                break
            v = stego_bytes[pos]
            for b in range(BITS_PER_BYTE - 1, -1, -1):
                bits.append((v >> b) & 1)

        payload = _bits_to_bytes(bits[HEADER_SIZE * 8:total_bits])
        if len(payload) < length:
            raise ValueError("Incomplete PE payload data")
        return payload[:length]


def parse_pe_regions(data: bytes):
    if len(data) < 0x100 or data[:2] != b"MZ":
        return []

    pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_off + 0x18 >= len(data) or data[pe_off:pe_off + 4] != b"PE\x00\x00":
        return []

    num_sections = struct.unpack_from("<H", data, pe_off + 6)[0]
    size_opt = struct.unpack_from("<H", data, pe_off + 20)[0]
    sec_off = pe_off + 24 + size_opt

    sections = []
    for i in range(num_sections):
        off = sec_off + i * 40
        if off + 40 > len(data):
            break
        name = data[off:off + 8].rstrip(b"\x00").decode("ascii", errors="ignore") or f"sec{i}"
        vsize = struct.unpack_from("<I", data, off + 8)[0]
        raw_size = struct.unpack_from("<I", data, off + 16)[0]
        raw_ptr = struct.unpack_from("<I", data, off + 20)[0]

        if raw_size == 0 or raw_ptr >= len(data):
            continue

        used = min(raw_size, vsize if vsize > 0 else raw_size)
        used_end = raw_ptr + used
        raw_end = min(len(data), raw_ptr + raw_size)
        sections.append((raw_ptr, raw_end, used_end, name))

    regions = []
    max_end = 0
    for raw_ptr, raw_end, used_end, name in sections:
        if raw_end > used_end:
            regions.append((used_end, raw_end, f"section_slack:{name}"))
        max_end = max(max_end, raw_end)

    if len(data) > max_end:
        regions.append((max_end, len(data), "overlay"))

    return regions


def _read_from_regions(data: bytes, regions, size: int) -> bytes:
    out = bytearray()
    for start, end, _ in regions:
        if len(out) >= size:
            break
        take = min(end - start, size - len(out))
        out.extend(data[start:start + take])
    return bytes(out)


def _ordered_positions(regions, key: str | None):
    weighted = []
    for start, end, region_type in regions:
        region_len = max(0, end - start)
        if region_len == 0:
            continue
        base_cost = 0.35 if str(region_type).startswith("section_slack") else 0.9
        weighted.append((start, end, region_type, base_cost, region_len))

    weighted.sort(key=lambda x: (x[3], -x[4], x[0]))
    positions = []
    for start, end, _, _, _ in weighted:
        positions.extend(range(start, end))

    if not key or not positions:
        return positions

    seed = int.from_bytes(hashlib.sha256(key.encode("utf-8")).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    arr = np.array(positions, dtype=np.int64)
    rng.shuffle(arr)
    return arr.tolist()


def _bytes_to_bits(data: bytes) -> list[int]:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_int(bits: list[int]) -> int:
    v = 0
    for b in bits:
        v = (v << 1) | b
    return v


def _bits_to_bytes(bits: list[int]) -> bytes:
    out = []
    for i in range(0, len(bits) - 7, 8):
        v = 0
        for b in bits[i:i + 8]:
            v = (v << 1) | b
        out.append(v)
    return bytes(out)
