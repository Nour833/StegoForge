"""
core/binary/pe.py — PE section-slack / overlay carrier.

Payload bits go into the low 2 bits of bytes in (a) the unused tail of each
section's raw data and (b) the overlay appended after the last section.

Warning: modifying a PE file invalidates any Authenticode signature, can trigger
antivirus heuristics, and corrupts self-extracting installers whose payload lives
in the overlay. Use only on executables you own and are authorised to modify.

The region-detection rules below define the on-disk format and must not change
without a format version.
"""
from __future__ import annotations

import struct

from core.binary._slack import SlackEncoder

MAGIC = b"SFPE"


class PEEncoder(SlackEncoder):
    name = "pe"
    supported_extensions = [".exe", ".dll", ".bin"]
    magic = MAGIC
    kind = "PE"
    signature = b"MZ"

    @staticmethod
    def parse_regions(data: bytes):
        return parse_pe_regions(data)

    @staticmethod
    def region_cost(kind: str) -> float:
        return 0.35 if kind.startswith("section_slack") else 0.9


def parse_pe_regions(data: bytes):
    if len(data) < 0x100 or data[:2] != b"MZ":
        return []

    try:
        pe_off = struct.unpack_from("<I", data, 0x3C)[0]
    except struct.error:
        return []
    if pe_off + 0x18 >= len(data) or data[pe_off:pe_off + 4] != b"PE\x00\x00":
        return []

    try:
        num_sections = struct.unpack_from("<H", data, pe_off + 6)[0]
        size_opt = struct.unpack_from("<H", data, pe_off + 20)[0]
    except struct.error:
        return []
    if num_sections > 96:
        return []
    sec_off = pe_off + 24 + size_opt

    sections = []
    for i in range(num_sections):
        off = sec_off + i * 40
        if off + 40 > len(data):
            break
        try:
            name = data[off:off + 8].rstrip(b"\x00").decode("ascii", errors="ignore") or f"sec{i}"
            vsize = struct.unpack_from("<I", data, off + 8)[0]
            raw_size = struct.unpack_from("<I", data, off + 16)[0]
            raw_ptr = struct.unpack_from("<I", data, off + 20)[0]
        except struct.error:
            break

        if raw_size == 0 or raw_ptr >= len(data):
            continue

        used = min(raw_size, vsize if vsize > 0 else raw_size)
        used_end = raw_ptr + used
        raw_end = min(len(data), raw_ptr + raw_size)
        sections.append((raw_ptr, raw_end, used_end, name))

    regions = []
    max_end = 0
    for _raw_ptr, raw_end, used_end, name in sections:
        if raw_end > used_end:
            regions.append((used_end, raw_end, f"section_slack:{name}"))
        max_end = max(max_end, raw_end)

    if len(data) > max_end:
        regions.append((max_end, len(data), "overlay"))

    return regions
