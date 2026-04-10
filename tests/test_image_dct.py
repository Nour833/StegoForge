"""tests/test_image_dct.py — Tests for DCT JPEG steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.image.dct import DCTEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.jpg"

encoder = DCTEncoder()


def test_roundtrip():
    carrier = CARRIER.read_bytes()
    payload = b"DCT test payload!"
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload


def test_capacity():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier)
    assert cap > 0
    print(f"  DCT capacity: {cap:,} bytes")


def test_payload_too_large():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier)
    with pytest.raises(ValueError, match="Payload too large"):
        encoder.encode(carrier, b"X" * (cap + 1))


def test_output_is_jpg():
    """Output must be a valid JPEG."""
    import io
    from PIL import Image
    carrier = CARRIER.read_bytes()
    stego = encoder.encode(carrier, b"test")
    img = Image.open(io.BytesIO(stego))
    assert img.format == "JPEG"


def test_roundtrip_binary():
    carrier = CARRIER.read_bytes()
    payload = bytes(range(128))
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload
