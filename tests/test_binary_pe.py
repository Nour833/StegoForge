"""tests/test_binary_pe.py - Tests for PE binary carrier encoder."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.binary.pe import PEEncoder


def _fake_pe() -> bytes:
    data = bytearray(8192)
    data[0:2] = b"MZ"
    pe_off = 0x80
    struct.pack_into("<I", data, 0x3C, pe_off)
    data[pe_off:pe_off + 4] = b"PE\x00\x00"

    # COFF header
    struct.pack_into("<H", data, pe_off + 6, 1)   # num sections
    struct.pack_into("<H", data, pe_off + 20, 224)  # opt header size

    sec_off = pe_off + 24 + 224
    data[sec_off:sec_off + 8] = b".text\x00\x00\x00"
    struct.pack_into("<I", data, sec_off + 8, 300)    # virtual size
    struct.pack_into("<I", data, sec_off + 16, 512)   # raw size
    struct.pack_into("<I", data, sec_off + 20, 0x400) # raw ptr

    # Fill used region with non-zero to distinguish slack.
    for i in range(0x400, 0x400 + 300):
        data[i] = 0x90

    return bytes(data)


def test_roundtrip():
    enc = PEEncoder()
    carrier = _fake_pe()
    payload = b"PE payload bytes"
    stego = enc.encode(carrier, payload)
    out = enc.decode(stego)
    assert out == payload


def test_capacity_positive():
    enc = PEEncoder()
    cap = enc.capacity(_fake_pe())
    assert cap > 0
