"""tests/test_document_pdf.py — Tests for PDF steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.document.pdf import PDFEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.pdf"

encoder = PDFEncoder()


def test_roundtrip():
    carrier = CARRIER.read_bytes()
    payload = b"PDF steganography test payload!"
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload


def test_output_is_valid_pdf():
    """Stego output should be a valid PDF."""
    from pypdf import PdfReader
    import io
    carrier = CARRIER.read_bytes()
    stego = encoder.encode(carrier, b"test payload")
    reader = PdfReader(io.BytesIO(stego))
    assert len(reader.pages) > 0


def test_no_payload_raises():
    carrier = CARRIER.read_bytes()
    with pytest.raises(ValueError, match="No StegoForge payload"):
        encoder.decode(carrier)


def test_roundtrip_binary():
    carrier = CARRIER.read_bytes()
    payload = bytes(range(256))
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload


def test_large_payload():
    carrier = CARRIER.read_bytes()
    payload = b"X" * 50_000
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload
