"""tests/test_image_lsb.py — Tests for Image LSB steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.image.lsb import LSBEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.png"

encoder = LSBEncoder()


def test_roundtrip_basic():
    carrier = CARRIER.read_bytes()
    payload = b"Hello, StegoForge!"
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload


def test_roundtrip_binary():
    carrier = CARRIER.read_bytes()
    payload = bytes(range(256)) * 10
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload


def test_capacity():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier, depth=1)
    assert cap > 0
    print(f"  LSB capacity at depth=1: {cap:,} bytes")


def test_capacity_increases_with_depth():
    carrier = CARRIER.read_bytes()
    cap1 = encoder.capacity(carrier, depth=1)
    cap2 = encoder.capacity(carrier, depth=2)
    cap4 = encoder.capacity(carrier, depth=4)
    assert cap2 >= cap1 * 1.5
    assert cap4 >= cap1 * 3


def test_payload_too_large_raises():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier, depth=1)
    big_payload = b"X" * (cap + 1)
    with pytest.raises(ValueError, match="Payload too large"):
        encoder.encode(carrier, big_payload)


def test_wrong_data_raises():
    carrier = CARRIER.read_bytes()
    stego = encoder.encode(carrier, b"a" * 10)
    # Corrupt the first bytes to break the header
    corrupted = b"\x00" * 40 + stego[40:]
    # Should raise ValueError, UnidentifiedImageError, or MemoryError
    try:
        encoder.decode(corrupted)
        pytest.fail("decode should have raised on corrupted data")
    except (ValueError, MemoryError, Exception):
        pass  # Any exception is acceptable for corrupted input


def test_polymorphic_traversal():
    carrier = CARRIER.read_bytes()
    payload = b"polymorphic test payload"
    stego = encoder.encode(carrier, payload, key="mykey")
    result = encoder.decode(stego, key="mykey")
    assert result == payload


def test_depth_2_roundtrip():
    carrier = CARRIER.read_bytes()
    payload = b"depth 2 test" * 100
    stego = encoder.encode(carrier, payload, depth=2)
    result = encoder.decode(stego, depth=2)
    assert result == payload


def test_large_payload_at_capacity():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier, depth=1)
    max_payload = bytes([i % 256 for i in range(cap)])
    stego = encoder.encode(carrier, max_payload)
    result = encoder.decode(stego)
    assert result == max_payload


def test_output_is_valid_png():
    """Stego output should be a valid PNG file."""
    from PIL import Image
    import io
    carrier = CARRIER.read_bytes()
    stego = encoder.encode(carrier, b"test")
    img = Image.open(io.BytesIO(stego))
    assert img.format == "PNG"


def test_bmp_roundtrip():
    bmp = FIXTURES / "sample.bmp"
    if not bmp.exists():
        # Re-generate if missing (shouldn't happen after generate_fixtures.py)
        from tests.generate_fixtures import gen_bmp, ensure_dir
        ensure_dir()
        gen_bmp()
    carrier = bmp.read_bytes()
    payload = b"BMP test payload"
    stego = encoder.encode(carrier, payload)
    result = encoder.decode(stego)
    assert result == payload
