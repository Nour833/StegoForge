"""
core/binary/elf.py - ELF slack/notes carrier encoder.
"""
from __future__ import annotations

import struct

from core.base import BaseEncoder

MAGIC = b"SFEL"
HEADER_FMT = ">4sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


class ELFEncoder(BaseEncoder):
    name = "elf"
    supported_extensions = [".elf", ".bin"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        regions = parse_elf_regions(carrier_bytes)
        total = sum(max(0, end - start) for start, end, _ in regions)
        return max(0, total - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        if not carrier_bytes.startswith(b"\x7fELF"):
            raise ValueError("Input is not a valid ELF binary")

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, ELF capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, MAGIC, len(payload_bytes)) + payload_bytes
        out = bytearray(carrier_bytes)
        written = 0

        for start, end, _ in parse_elf_regions(carrier_bytes):
            if written >= len(data):
                break
            n = min(end - start, len(data) - written)
            out[start:start + n] = data[written:written + n]
            written += n

        if written < len(data):
            raise ValueError("ELF slack regions were insufficient to embed payload")
        return bytes(out)

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        if not stego_bytes.startswith(b"\x7fELF"):
            raise ValueError("Input is not a valid ELF binary")

        data = _read_from_regions(stego_bytes, parse_elf_regions(stego_bytes), HEADER_SIZE)
        if len(data) < HEADER_SIZE:
            raise ValueError("No embedded ELF payload header found")

        magic, length = struct.unpack(HEADER_FMT, data)
        if magic != MAGIC or length <= 0:
            raise ValueError("No StegoForge ELF payload found")

        payload = _read_from_regions(stego_bytes, parse_elf_regions(stego_bytes), HEADER_SIZE + length)
        payload = payload[HEADER_SIZE:HEADER_SIZE + length]
        if len(payload) < length:
            raise ValueError("Incomplete ELF payload data")
        return payload


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
