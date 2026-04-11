"""tests/test_image_fingerprint.py - Tests for PRNU-aware fingerprint encoder."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.image.fingerprint import FingerprintEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.png"


def test_roundtrip():
    enc = FingerprintEncoder()
    carrier = CARRIER.read_bytes()
    payload = b"fingerprint preserve payload"
    stego = enc.encode(carrier, payload)
    out = enc.decode(stego)
    assert out == payload


def test_capacity_positive():
    enc = FingerprintEncoder()
    cap = enc.capacity(CARRIER.read_bytes())
    assert cap > 0
