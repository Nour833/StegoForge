"""tests/test_guess.py — payload-type sniffing must not mistake text for a binary format."""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.guess import guess_payload_ext, guess_payload_type

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("text", [
    b"BMW sales notes for Q3\n",
    b"MZ-3 service report: all clear\n",
    b"RIFF is a container format used by...\n",
    b"ID3 tags are metadata for MP3 files\n",
    b"GIF89 stands for something else\n",
    b"%PDF is the magic of a PDF file\n",
    b"plain ascii note",
    "naive café résumé text".encode(),
])
def test_text_that_starts_like_a_magic_number_is_text(text):
    assert guess_payload_ext(text) == ".txt"
    assert guess_payload_type(text) == ("text/plain", ".txt")


@pytest.mark.parametrize("name, ext", [
    ("sample.png", ".png"), ("sample.jpg", ".jpg"), ("sample.bmp", ".bmp"), ("sample.wav", ".wav"),
    ("sample.pdf", ".pdf"), ("sample.docx", ".zip"), ("sample_indexed.gif", ".gif"), ("sample.txt", ".txt"),
])
def test_real_files_are_recognised(name, ext):
    assert guess_payload_ext((FIXTURES / name).read_bytes()) == ext


def test_real_pe_and_elf_headers():
    pe = bytearray(0x100)
    pe[:2] = b"MZ"
    struct.pack_into("<I", pe, 0x3C, 0x80)
    pe[0x80:0x84] = b"PE\x00\x00"
    assert guess_payload_ext(bytes(pe)) == ".exe"
    assert guess_payload_ext(b"\x7fELF" + bytes(60)) == ".elf"
    assert guess_payload_ext(b"MZ" + bytes(200)) == ".bin"  # DOS stub without a PE header


def test_binary_noise_and_encrypted_blobs():
    assert guess_payload_ext(bytes(range(256)) * 4) == ".bin"
    assert guess_payload_ext(b"SFRG\x03\x01" + bytes(40)) == ".sfrg"
    assert guess_payload_type(b"\x00\x01\x02")[0] == "application/octet-stream"


def test_wav_riff_requires_the_wave_form_type():
    assert guess_payload_ext(b"RIFF\x00\x00\x00\x00WAVEfmt " + bytes(30)) == ".wav"
    assert guess_payload_ext(b"RIFF\x00\x00\x00\x00ABCDfmt " + bytes(30)) == ".bin"


def test_mp4_by_ftyp_box():
    assert guess_payload_ext(b"\x00\x00\x00\x18ftypisom" + bytes(20)) == ".mp4"


def test_web_and_cli_share_one_implementation():
    from stegoforge import _guess_payload_ext
    from web.app import _detect_payload_type

    sample = b"BMW sales notes\n"
    assert _guess_payload_ext(sample) == _detect_payload_type(sample)[1] == ".txt"
