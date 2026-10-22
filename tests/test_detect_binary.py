"""tests/test_detect_binary.py - Tests for binary anomaly detector."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from detect.binary import BinaryDetector
from core.binary.elf import ELFEncoder
from core.binary.pe import PEEncoder
from tests.test_binary_elf import _fake_elf
from tests.test_binary_pe import _fake_pe


def test_detector_confidence_range_elf():
    det = BinaryDetector()
    r = det.analyze(_fake_elf(), "sample.elf")
    assert 0.0 <= r.confidence <= 1.0


def test_detector_confidence_range_pe():
    det = BinaryDetector()
    r = det.analyze(_fake_pe(), "sample.exe")
    assert 0.0 <= r.confidence <= 1.0


def test_detector_on_stego_binary():
    det = BinaryDetector()
    carrier = _fake_elf()
    stego = ELFEncoder().encode(carrier, b"binary hidden payload")
    r = det.analyze(stego, "stego.elf")
    assert r.method == "binary"
    assert 0.0 <= r.confidence <= 1.0


# ── false-positive regression: real, untouched system binaries ───────────────

import os  # noqa: E402
import shutil  # noqa: E402

import pytest  # noqa: E402


def _system_elfs() -> list[str]:
    names = [os.path.realpath(sys.executable)] + [shutil.which(n) for n in ("ls", "cat", "bash", "sh")]
    seen, found = set(), []
    for path in names:
        if not path:
            continue
        path = os.path.realpath(path)
        if path in seen or not os.path.isfile(path):
            continue
        seen.add(path)
        with open(path, "rb") as fh:
            if fh.read(4) == b"\x7fELF":
                found.append(path)
    return found


@pytest.mark.parametrize("path", _system_elfs() or [pytest.param("", marks=pytest.mark.skip("no system ELF"))])
def test_clean_system_elf_is_not_flagged(path):
    """NOTE sections (build-id, GNU properties) are real data, not slack."""
    r = BinaryDetector().analyze(Path(path).read_bytes(), path)
    assert not r.detected
    assert r.confidence == 0.0
    assert r.extracted_payload is None


def test_data_in_notes_and_overlay_is_not_evidence():
    carrier = bytearray(_fake_elf())
    carrier[1024:1100] = bytes(range(1, 77))  # the fake ELF's NOTE section
    assert not BinaryDetector().analyze(bytes(carrier), "n.elf").detected
    pe = bytearray(_fake_pe()) + bytes(range(1, 200))  # overlay beyond the last section
    assert not BinaryDetector().analyze(bytes(pe), "o.exe").detected


def test_uniform_fill_padding_is_benign():
    pe = bytearray(_fake_pe())
    pe[0x400 + 300:0x400 + 512] = b"\xcc" * 212  # MSVC-style int3 fill
    assert not BinaryDetector().analyze(bytes(pe), "fill.exe").detected


def test_stego_elf_and_pe_are_detected_and_extracted():
    for carrier, enc, name in ((_fake_elf(), ELFEncoder(), "s.elf"), (_fake_pe(), PEEncoder(), "s.exe")):
        r = BinaryDetector().analyze(enc.encode(carrier, b"found me"), name)
        assert r.detected and r.confidence == 1.0
        assert r.extracted_payload == b"found me"


def test_padding_with_two_bit_pattern_is_flagged_without_a_valid_header():
    """Slack carrying a foreign/keyed 2-bit embed is still caught from the padding itself."""
    carrier = bytearray(_fake_elf())
    carrier[712:760] = bytes((i * 7 + 1) % 4 for i in range(48))  # gap after section 0
    r = BinaryDetector().analyze(bytes(carrier), "k.elf")
    assert r.detected and r.confidence >= 0.8 and r.extracted_payload is None
    assert any("2-bit" in f["description"] for f in r.findings)


# ── layouts produced by post-link rewriters (BOLT) and by padding with a repeated byte ───────────

def _with_load_segment(data: bytearray) -> None:
    """One PT_LOAD mapping file offset 0 at 0x400000, right after the ELF header."""
    import struct

    struct.pack_into("<Q", data, 32, 64)     # e_phoff
    struct.pack_into("<H", data, 54, 56)     # e_phentsize
    struct.pack_into("<H", data, 56, 1)      # e_phnum
    struct.pack_into("<I", data, 64, 1)      # PT_LOAD
    struct.pack_into("<Q", data, 72, 0)      # p_offset
    struct.pack_into("<Q", data, 80, 0x400000)  # p_vaddr
    struct.pack_into("<Q", data, 96, 4096)   # p_filesz


def _rewritten_string_table(with_segments: bool) -> bytes:
    """Section 2 is a live string table at file offset 1536 whose header (like BOLT's) says offset 3000."""
    import struct

    data = bytearray(_fake_elf())
    sec = 256 + 128
    struct.pack_into("<I", data, sec + 4, 3)                 # SHT_STRTAB
    struct.pack_into("<Q", data, sec + 8, 0x2)               # SHF_ALLOC
    struct.pack_into("<Q", data, sec + 16, 0x400000 + 1536)  # where the loader maps it
    struct.pack_into("<Q", data, sec + 24, 3000)             # stale file offset
    struct.pack_into("<Q", data, sec + 32, 200)
    data[1536:1736] = (b"__gmon_start__\0ceil\0log10\0" * 8)[:200]
    if with_segments:
        _with_load_segment(data)
    return bytes(data)


def test_section_header_that_contradicts_the_loader_does_not_expose_live_data():
    assert BinaryDetector().analyze(_rewritten_string_table(True), "bolt.elf").detected is False


def test_the_same_bytes_in_a_real_gap_are_still_evidence():
    """Control for the test above: without program headers nothing says the bytes are live."""
    assert BinaryDetector().analyze(_rewritten_string_table(False), "gap.elf").detected is True


def test_repeated_nonzero_fill_with_a_stray_byte_is_benign():
    carrier = bytearray(_fake_elf())
    carrier[712:1000] = b"X" * 288
    carrier[900] = 0
    assert not BinaryDetector().analyze(bytes(carrier), "fill.elf").detected


def test_a_short_payload_in_zero_padding_is_still_evidence():
    carrier = bytearray(_fake_elf())
    carrier[712:732] = bytes((i * 37 + 11) % 251 + 1 for i in range(20))
    r = BinaryDetector().analyze(bytes(carrier), "short.elf")
    assert r.detected and r.confidence >= 0.5
