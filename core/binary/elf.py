"""
core/binary/elf.py - ELF slack/notes carrier encoder.
"""
from __future__ import annotations

import hashlib
import struct
import numpy as np

from core.base import BaseEncoder

MAGIC = b"SFEL"
HEADER_FMT = ">4sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
BITS_PER_BYTE = 2


class ELFEncoder(BaseEncoder):
    name = "elf"
    supported_extensions = [".elf", ".bin"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        regions = parse_elf_regions(carrier_bytes)
        total = sum(max(0, end - start) for start, end, _ in regions)
        return max(0, (total * BITS_PER_BYTE // 8) - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        if not carrier_bytes.startswith(b"\x7fELF"):
            raise ValueError("Input is not a valid ELF binary")

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, ELF capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, MAGIC, len(payload_bytes)) + payload_bytes
        bits = _bytes_to_bits(data)
        out = bytearray(carrier_bytes)
        key = kwargs.get("key")
        positions = _ordered_positions(parse_elf_regions(carrier_bytes), key)

        if len(bits) > len(positions) * BITS_PER_BYTE:
            raise ValueError("ELF slack regions were insufficient to embed payload")

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
            raise ValueError("ELF slack regions were insufficient to embed payload")
        return bytes(out)

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        if not stego_bytes.startswith(b"\x7fELF"):
            raise ValueError("Input is not a valid ELF binary")

        regions = parse_elf_regions(stego_bytes)
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
            raise ValueError("No embedded ELF payload header found")

        header = _bits_to_bytes(bits[:header_bits_needed])
        magic, length = struct.unpack(HEADER_FMT, header)
        if magic != MAGIC or length <= 0:
            raise ValueError("No StegoForge ELF payload found")

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
            raise ValueError("Incomplete ELF payload data")
        return payload[:length]


def parse_elf_regions(data: bytes):
    if len(data) < 64 or not data.startswith(b"\x7fELF"):
        return []

    ei_class = data[4]
    ei_data = data[5]
    endian = "<" if ei_data == 1 else ">"

    if ei_class == 2:  # ELF64
        e_shoff = struct.unpack_from(endian + "Q", data, 40)[0]
        e_shentsize = struct.unpack_from(endian + "H", data, 58)[0]
        e_shnum = struct.unpack_from(endian + "H", data, 60)[0]
        sh_offset_off = 24
        sh_size_off = 32
        sh_type_off = 4
        uoff = "Q"
    elif ei_class == 1:  # ELF32
        e_shoff = struct.unpack_from(endian + "I", data, 32)[0]
        e_shentsize = struct.unpack_from(endian + "H", data, 46)[0]
        e_shnum = struct.unpack_from(endian + "H", data, 48)[0]
        sh_offset_off = 16
        sh_size_off = 20
        sh_type_off = 4
        uoff = "I"
    else:
        return []

    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        if off + e_shentsize > len(data):
            break
        sh_type = struct.unpack_from(endian + "I", data, off + sh_type_off)[0]
        sh_offset = struct.unpack_from(endian + uoff, data, off + sh_offset_off)[0]
        sh_size = struct.unpack_from(endian + uoff, data, off + sh_size_off)[0]
        if sh_size > 0 and sh_offset < len(data):
            sections.append((int(sh_offset), int(sh_offset + sh_size), int(sh_type)))

    sections.sort(key=lambda x: x[0])
    regions = []

    for idx in range(len(sections) - 1):
        cur_end = sections[idx][1]
        nxt_start = sections[idx + 1][0]
        if nxt_start > cur_end:
            regions.append((cur_end, nxt_start, "section_padding"))

    # Include NOTE sections as optional embedding area.
    for start, end, sh_type in sections:
        if sh_type == 7 and end > start:
            regions.append((start, end, "notes"))

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
        base_cost = 0.3 if region_type == "section_padding" else 0.8
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
