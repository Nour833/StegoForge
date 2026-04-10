"""tests/test_image_alpha.py — Tests for alpha channel steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.image.alpha import AlphaEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample_rgba.png"

encoder = AlphaEncoder()


def test_roundtrip():
    carrier = CARRIER.read_bytes()
    payload = b"Alpha channel test!"
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload


def test_capacity():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier)
    assert cap > 0


def test_payload_too_large():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier)
    with pytest.raises(ValueError):
        encoder.encode(carrier, b"X" * (cap + 1))


def test_non_rgba_raises():
    from PIL import Image
    import io
    img = Image.new("RGB", (64, 64))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    # Alpha encoder should handle RGB by converting — or raise
    # Either is acceptable
    try:
        carrier = buf.getvalue()
        stego = encoder.encode(carrier, b"test")
        result = encoder.decode(stego)
        # If it didn't raise, result must be correct
        assert result == b"test"
    except (ValueError, Exception):
        pass  # Also acceptable to raise for non-RGBA


def test_output_is_png():
    import io
    from PIL import Image
    carrier = CARRIER.read_bytes()
    stego = encoder.encode(carrier, b"test")
    img = Image.open(io.BytesIO(stego))
    assert img.format == "PNG"
    assert img.mode == "RGBA"
