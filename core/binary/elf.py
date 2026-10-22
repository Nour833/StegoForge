"""
core/binary/elf.py — ELF slack-space carrier.

Payload bits go into the low 2 bits of bytes in (a) the padding gaps between
sections and (b) ``SHT_NOTE`` sections, cheapest regions first. A binary
modified this way still runs: padding is never executed and the note sections
(build-id, ABI tag) are metadata only. Verified by ``tests/test_binary_elf.py``.

The region-detection rules below define the on-disk format and must not change
without a format version (they decide which bytes a decoder reads).
"""
from __future__ import annotations

import struct

from core.binary._slack import SlackEncoder

MAGIC = b"SFEL"


class ELFEncoder(SlackEncoder):
    name = "elf"
    supported_extensions = [".elf", ".bin"]
    magic = MAGIC
    kind = "ELF"
    signature = b"\x7fELF"

    @staticmethod
    def parse_regions(data: bytes):
        return parse_elf_regions(data)

    @staticmethod
    def region_cost(kind: str) -> float:
        return 0.3 if kind == "section_padding" else 0.8


def parse_elf_regions(data: bytes):
    if len(data) < 64 or not data.startswith(b"\x7fELF"):
        return []

    ei_class = data[4]
    ei_data = data[5]
    endian = "<" if ei_data == 1 else ">"
    if ei_data not in (1, 2):
        return []

    try:
        if ei_class == 2:  # ELF64
            e_shoff = struct.unpack_from(endian + "Q", data, 40)[0]
            e_shentsize = struct.unpack_from(endian + "H", data, 58)[0]
            e_shnum = struct.unpack_from(endian + "H", data, 60)[0]
            e_phoff = struct.unpack_from(endian + "Q", data, 32)[0]
            e_phentsize = struct.unpack_from(endian + "H", data, 54)[0]
            e_phnum = struct.unpack_from(endian + "H", data, 56)[0]
            sh_flags_off, sh_addr_off = 8, 16
            sh_offset_off = 24
            sh_size_off = 32
            sh_type_off = 4
            ph_offset_off, ph_vaddr_off, ph_filesz_off = 8, 16, 32
            uoff = "Q"
        elif ei_class == 1:  # ELF32
            e_shoff = struct.unpack_from(endian + "I", data, 32)[0]
            e_shentsize = struct.unpack_from(endian + "H", data, 46)[0]
            e_shnum = struct.unpack_from(endian + "H", data, 48)[0]
            e_phoff = struct.unpack_from(endian + "I", data, 28)[0]
            e_phentsize = struct.unpack_from(endian + "H", data, 42)[0]
            e_phnum = struct.unpack_from(endian + "H", data, 44)[0]
            sh_flags_off, sh_addr_off = 8, 12
            sh_offset_off = 16
            sh_size_off = 20
            sh_type_off = 4
            ph_offset_off, ph_vaddr_off, ph_filesz_off = 4, 8, 16
            uoff = "I"
        else:
            return []
    except struct.error:
        return []

    if e_shnum > 256 or e_shentsize == 0:
        return []

    # Where the loader finds each PT_LOAD segment: (file offset, virtual address, file size).
    loads = []
    if e_phentsize > 0 and e_phnum <= 256:
        for i in range(e_phnum):
            off = e_phoff + i * e_phentsize
            try:
                if struct.unpack_from(endian + "I", data, off)[0] != 1:  # PT_LOAD
                    continue
                loads.append((
                    struct.unpack_from(endian + uoff, data, off + ph_offset_off)[0],
                    struct.unpack_from(endian + uoff, data, off + ph_vaddr_off)[0],
                    struct.unpack_from(endian + uoff, data, off + ph_filesz_off)[0],
                ))
            except struct.error:
                break

    sections = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        if off + e_shentsize > len(data):
            break
        try:
            sh_type = struct.unpack_from(endian + "I", data, off + sh_type_off)[0]
            sh_flags = struct.unpack_from(endian + uoff, data, off + sh_flags_off)[0]
            sh_addr = struct.unpack_from(endian + uoff, data, off + sh_addr_off)[0]
            sh_offset = struct.unpack_from(endian + uoff, data, off + sh_offset_off)[0]
            sh_size = struct.unpack_from(endian + uoff, data, off + sh_size_off)[0]
        except struct.error:
            break
        # Clamp to file bounds — never trust on-disk offsets.
        sh_offset = max(0, min(int(sh_offset), len(data)))
        sh_size = max(0, min(int(sh_size), len(data) - sh_offset))
        if sh_size > 0 and sh_offset < len(data):
            sections.append((int(sh_offset), int(sh_offset + sh_size), int(sh_type)))
        # Post-link rewriters (BOLT) can leave a section header whose offset disagrees with where the
        # loader maps its address. The bytes at the mapped place are live data, not padding.
        if sh_size > 0 and sh_flags & 0x2 and sh_type != 8:  # SHF_ALLOC, not NOBITS
            for p_offset, p_vaddr, p_filesz in loads:
                if p_vaddr <= sh_addr < p_vaddr + p_filesz:
                    mapped = int(p_offset + sh_addr - p_vaddr)
                    if mapped != sh_offset and mapped + sh_size <= len(data):
                        sections.append((mapped, mapped + int(sh_size), int(sh_type)))
                    break

    sections.sort(key=lambda x: x[0])
    regions = []

    for idx in range(len(sections) - 1):
        cur_end = sections[idx][1]
        nxt_start = sections[idx + 1][0]
        if nxt_start > cur_end:
            regions.append((cur_end, min(nxt_start, len(data)), "section_padding"))

    # Include NOTE sections as optional embedding area (clamped to file length).
    for start, end, sh_type in sections:
        if sh_type == 7 and end > start:
            regions.append((start, min(end, len(data)), "notes"))

    # Drop degenerate regions.
    regions = [(s, e, t) for s, e, t in regions if e > s and s < len(data)]
    return regions
