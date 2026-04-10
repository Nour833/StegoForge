"""tests/test_document_unicode.py — Tests for Unicode zero-width steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.document.unicode_ws import UnicodeWSEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.txt"

encoder = UnicodeWSEncoder()

ZWSP = "\u200B"
ZWNJ = "\u200C"
ZWJ  = "\u200D"


def test_roundtrip():
    carrier = CARRIER.read_bytes()
    payload = b"Zero-width test!"
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload


def test_invisible_to_human():
    """Stego text should look the same as original when stripped of ZW chars."""
    carrier = CARRIER.read_bytes()
    payload = b"secret"
    stego = encoder.encode(carrier, payload)
    stego_text = stego.decode("utf-8")
    # Removing zero-width chars should give back the original text
    cleaned = stego_text.replace(ZWSP, "").replace(ZWNJ, "").replace(ZWJ, "")
    original = carrier.decode("utf-8")
    assert cleaned == original


def test_capacity():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier)
    assert cap > 0


def test_contains_zero_width_chars():
    carrier = CARRIER.read_bytes()
    payload = b"test"
    stego = encoder.encode(carrier, payload)
    text = stego.decode("utf-8")
    zw_count = sum(1 for c in text if c in (ZWSP, ZWNJ, ZWJ))
    assert zw_count > 0


def test_payload_too_large():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier)
    with pytest.raises(ValueError):
        encoder.encode(carrier, b"X" * (cap + 100))


def test_roundtrip_binary():
    carrier = CARRIER.read_bytes()
    payload = bytes(range(128))  # all values 0-127
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload
