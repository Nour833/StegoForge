"""tests/test_binary_elf.py - Tests for ELF binary carrier encoder."""
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.binary.elf import ELFEncoder


def _fake_elf() -> bytes:
    # Minimal fake ELF64 with section-like layout and padding slack.
    data = bytearray(4096)
    data[0:4] = b"\x7fELF"
    data[4] = 2  # ELF64
    data[5] = 1  # little-endian

    e_shoff = 256
    e_shentsize = 64
    e_shnum = 3
    struct.pack_into("<Q", data, 40, e_shoff)
    struct.pack_into("<H", data, 58, e_shentsize)
    struct.pack_into("<H", data, 60, e_shnum)

    # Section 0
    off = e_shoff
    struct.pack_into("<I", data, off + 4, 1)
    struct.pack_into("<Q", data, off + 24, 512)
    struct.pack_into("<Q", data, off + 32, 200)

    # Section 1 (NOTE)
    off = e_shoff + 64
    struct.pack_into("<I", data, off + 4, 7)
    struct.pack_into("<Q", data, off + 24, 1024)
    struct.pack_into("<Q", data, off + 32, 128)

    # Section 2
    off = e_shoff + 128
    struct.pack_into("<I", data, off + 4, 1)
    struct.pack_into("<Q", data, off + 24, 2048)
    struct.pack_into("<Q", data, off + 32, 200)

    return bytes(data)


def test_roundtrip():
    enc = ELFEncoder()
    carrier = _fake_elf()
    payload = b"ELF payload bytes"
    stego = enc.encode(carrier, payload)
    out = enc.decode(stego)
    assert out == payload


def test_capacity_positive():
    enc = ELFEncoder()
    cap = enc.capacity(_fake_elf())
    assert cap > 0


def test_roundtrip_with_key():
    enc = ELFEncoder()
    carrier = _fake_elf()
    payload = b"ELF payload with key"
    stego = enc.encode(carrier, payload, key="elf-key")
    out = enc.decode(stego, key="elf-key")
    assert out == payload


def test_wrong_key_fails():
    enc = ELFEncoder()
    carrier = _fake_elf()
    payload = b"ELF key mismatch"
    stego = enc.encode(carrier, payload, key="right-key")
    try:
        _ = enc.decode(stego, key="wrong-key")
    except ValueError:
        return
    raise AssertionError("Decoding with wrong key unexpectedly succeeded")
