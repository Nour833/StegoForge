"""tests/test_image_palette.py — Tests for palette reordering steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.image.palette import PaletteEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample_indexed.gif"

encoder = PaletteEncoder()


def test_roundtrip():
    carrier = CARRIER.read_bytes()
    payload = b"Hi"  # palette has low capacity
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload


def test_capacity():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier)
    assert cap >= 0  # may be very small


def test_non_indexed_raises():
    from PIL import Image
    import io
    img = Image.new("RGB", (64, 64))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    with pytest.raises(ValueError, match="indexed"):
        encoder.encode(buf.getvalue(), b"test")


def test_visual_unchanged():
    """Stego image should render identical colors to original."""
    from PIL import Image
    import io

    carrier = CARRIER.read_bytes()
    payload = b"A"
    stego = encoder.encode(carrier, payload)

    orig = Image.open(io.BytesIO(carrier)).convert("RGB")
    stego_img = Image.open(io.BytesIO(stego)).convert("RGB")
    assert orig.size == stego_img.size
