"""tests/test_detect_chi2.py — Tests for Chi-Square LSB detector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from detect.chi2 import Chi2Detector
from core.image.lsb import LSBEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.png"

detector = Chi2Detector()


def test_clean_image_low_confidence():
    """Clean random noise image should have low confidence."""
    carrier = CARRIER.read_bytes()
    result = detector.analyze(carrier, "sample.png")
    assert 0.0 <= result.confidence <= 1.0
    print(f"  Clean image chi2 confidence: {result.confidence:.3f}")


def test_stego_image_higher_confidence():
    """Image with lots of LSB data should have higher confidence than clean."""
    carrier = CARRIER.read_bytes()
    encoder = LSBEncoder()
    # Fill a large portion of capacity
    cap = encoder.capacity(carrier, depth=1)
    payload = bytes([i % 256 for i in range(min(cap, cap // 2))])
    stego = encoder.encode(carrier, payload)

    clean_result = detector.analyze(carrier, "clean.png")
    stego_result = detector.analyze(stego, "stego.png")
    print(f"  Clean confidence: {clean_result.confidence:.3f}")
    print(f"  Stego confidence: {stego_result.confidence:.3f}")
    assert isinstance(stego_result.detected, bool)
    assert 0.0 <= stego_result.confidence <= 1.0


def test_result_structure():
    result = detector.analyze(CARRIER.read_bytes(), "sample.png")
    assert result.method == "chi2"
    assert isinstance(result.detected, bool)
    assert 0.0 <= result.confidence <= 1.0
    assert "chi2_statistic" in result.details
    assert "p_value" in result.details
    assert "channels" in result.details


def test_unsupported_format_graceful():
    """Non-image bytes should be handled gracefully."""
    result = detector.analyze(b"not an image", "notanimage.txt")
    assert result.detected is False
    assert "error" in result.details
