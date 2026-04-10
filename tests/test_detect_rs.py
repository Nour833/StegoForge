"""tests/test_detect_rs.py — Tests for RS analysis detector."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from detect.rs import RSDetector
from core.image.lsb import LSBEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.png"

detector = RSDetector()


def test_clean_image():
    result = detector.analyze(CARRIER.read_bytes(), "sample.png")
    assert 0.0 <= result.confidence <= 1.0
    assert "estimated_payload_fraction" in result.details
    print(f"  Clean image RS confidence: {result.confidence:.3f}, "
          f"fraction: {result.details['estimated_payload_fraction']:.3f}")


def test_stego_has_fraction():
    carrier = CARRIER.read_bytes()
    encoder = LSBEncoder()
    cap = encoder.capacity(carrier)
    payload = bytes([i % 256 for i in range(cap // 2)])
    stego = encoder.encode(carrier, payload)
    result = detector.analyze(stego, "stego.png")
    print(f"  Stego RS fraction: {result.details['estimated_payload_fraction']:.3f}")
    assert 0.0 <= result.details["estimated_payload_fraction"] <= 1.0


def test_result_structure():
    result = detector.analyze(CARRIER.read_bytes(), "sample.png")
    assert result.method == "rs"
    assert "regular_groups" in result.details
    assert "singular_groups" in result.details
    assert "total_groups" in result.details
    assert "interpretation" in result.details


def test_bad_image_graceful():
    result = detector.analyze(b"garbage", "bad.png")
    assert result.detected is False
