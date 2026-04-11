"""
core/binary/pe.py - PE section slack/overlay carrier encoder.

Warning: modifying PE binaries can trigger antivirus detections. Use only on
executables you own and are authorized to modify.
"""
from __future__ import annotations

import struct

from core.base import BaseEncoder

MAGIC = b"SFPE"
HEADER_FMT = ">4sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


class PEEncoder(BaseEncoder):
    name = "pe"
    supported_extensions = [".exe", ".dll", ".bin"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        regions = parse_pe_regions(carrier_bytes)
        total = sum(max(0, end - start) for start, end, _ in regions)
        return max(0, total - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        if not carrier_bytes.startswith(b"MZ"):
            raise ValueError("Input is not a valid PE binary")

        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, PE capacity: {cap} bytes")

        data = struct.pack(HEADER_FMT, MAGIC, len(payload_bytes)) + payload_bytes
        out = bytearray(carrier_bytes)
        written = 0

        for start, end, _ in parse_pe_regions(carrier_bytes):
            if written >= len(data):
                break
            n = min(end - start, len(data) - written)
            out[start:start + n] = data[written:written + n]
            written += n

        if written < len(data):
            raise ValueError("PE slack regions were insufficient to embed payload")
        return bytes(out)

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        if not stego_bytes.startswith(b"MZ"):
            raise ValueError("Input is not a valid PE binary")

        header = _read_from_regions(stego_bytes, parse_pe_regions(stego_bytes), HEADER_SIZE)
        if len(header) < HEADER_SIZE:
            raise ValueError("No embedded PE payload header found")

        magic, length = struct.unpack(HEADER_FMT, header)
        if magic != MAGIC or length <= 0:
            raise ValueError("No StegoForge PE payload found")

        payload = _read_from_regions(stego_bytes, parse_pe_regions(stego_bytes), HEADER_SIZE + length)
        payload = payload[HEADER_SIZE:HEADER_SIZE + length]
        if len(payload) < length:
            raise ValueError("Incomplete PE payload data")
        return payload


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
