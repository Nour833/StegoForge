"""tests/test_document_office.py — Tests for DOCX/XLSX steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import zipfile
import io
from core.document.office import OfficeEncoder

FIXTURES = Path(__file__).parent / "fixtures"

encoder = OfficeEncoder()


def test_docx_roundtrip():
    carrier = (FIXTURES / "sample.docx").read_bytes()
    payload = b"DOCX steganography test!"
    stego = encoder.encode(carrier, payload, filename="sample.docx")
    result = encoder.decode(stego, filename="sample.docx")
    assert result == payload


def test_xlsx_roundtrip():
    carrier = (FIXTURES / "sample.xlsx").read_bytes()
    payload = b"XLSX steganography test!"
    stego = encoder.encode(carrier, payload, filename="sample.xlsx")
    result = encoder.decode(stego, filename="sample.xlsx")
    assert result == payload


def test_docx_stego_is_valid_zip():
    carrier = (FIXTURES / "sample.docx").read_bytes()
    stego = encoder.encode(carrier, b"test", filename="sample.docx")
    # Should open as valid ZIP without error
    with zipfile.ZipFile(io.BytesIO(stego), "r") as zf:
        names = zf.namelist()
        assert "word/document.xml" in names
        assert "word/custom/stegodata.xml" in names


def test_no_payload_raises():
    carrier = (FIXTURES / "sample.docx").read_bytes()
    with pytest.raises(ValueError):
        encoder.decode(carrier, filename="sample.docx")


def test_roundtrip_large():
    carrier = (FIXTURES / "sample.docx").read_bytes()
    payload = b"A" * 100_000
    stego = encoder.encode(carrier, payload, filename="sample.docx")
    result = encoder.decode(stego, filename="sample.docx")
    assert result == payload
