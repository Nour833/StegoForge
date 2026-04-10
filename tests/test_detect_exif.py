"""tests/test_detect_exif.py — Tests for EXIF/metadata forensics detector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from detect.exif import EXIFDetector

FIXTURES = Path(__file__).parent / "fixtures"

detector = EXIFDetector()


def test_clean_png():
    result = detector.analyze((FIXTURES / "sample.png").read_bytes(), "sample.png")
    assert result.method == "exif"
    assert isinstance(result.detected, bool)


def test_pdf_with_stego_detected():
    """PDF with /StegoData key should be detected."""
    from core.document.pdf import PDFEncoder
    carrier = (FIXTURES / "sample.pdf").read_bytes()
    stego = PDFEncoder().encode(carrier, b"hidden payload")
    result = detector.analyze(stego, "stego.pdf")
    assert result.detected is True
    assert result.confidence > 0.1
    # Should find the /StegoData finding
    high_findings = [f for f in result.findings if f.get("suspicion") == "high"]
    assert len(high_findings) > 0


def test_docx_with_stego_detected():
    """DOCX with stegodata.xml should be detected."""
    from core.document.office import OfficeEncoder
    carrier = (FIXTURES / "sample.docx").read_bytes()
    stego = OfficeEncoder().encode(carrier, b"hidden", filename="sample.docx")
    result = detector.analyze(stego, "stego.docx")
    assert result.detected is True


def test_txt_with_zwchars_detected():
    """Text with zero-width chars should be detected as high suspicion."""
    from core.document.unicode_ws import UnicodeWSEncoder
    carrier = (FIXTURES / "sample.txt").read_bytes()
    stego = UnicodeWSEncoder().encode(carrier, b"secret")
    result = detector.analyze(stego, "stego.txt")
    assert result.detected is True
    assert result.confidence > 0.3


def test_result_structure():
    result = detector.analyze((FIXTURES / "sample.png").read_bytes(), "sample.png")
    assert result.method == "exif"
    assert isinstance(result.findings, list)
    assert "findings_count" in result.details


def test_bad_file_graceful():
    result = detector.analyze(b"\x00\xff\xfe\xfd", "unknown.bin")
    assert isinstance(result.detected, bool)
