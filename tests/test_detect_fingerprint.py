"""tests/test_detect_fingerprint.py - Tests for PRNU inconsistency detector."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from detect.fingerprint import FingerprintDetector
from core.image.fingerprint import FingerprintEncoder

FIXTURES = Path(__file__).parent / "fixtures"


def test_confidence_range():
    det = FingerprintDetector()
    img = (FIXTURES / "sample.png").read_bytes()
    r = det.analyze(img, "sample.png")
    assert 0.0 <= r.confidence <= 1.0


def test_detect_output_structure_on_stego():
    det = FingerprintDetector()
    enc = FingerprintEncoder()
    carrier = (FIXTURES / "sample.png").read_bytes()
    stego = enc.encode(carrier, b"secret")
    r = det.analyze(stego, "sample_stego.png")
    assert r.method == "fingerprint"
    assert 0.0 <= r.confidence <= 1.0
    assert "interpretation" in r.details
