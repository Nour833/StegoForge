"""tests/test_audio_phase.py — Tests for audio phase coding steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.audio.phase import PhaseEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.wav"

encoder = PhaseEncoder()


def test_roundtrip():
    carrier = CARRIER.read_bytes()
    payload = b"Phase test!"
    stego = encoder.encode(carrier, payload, ext=".wav")
    result = encoder.decode(stego, ext=".wav")
    assert result == payload


def test_capacity():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier, ext=".wav")
    assert cap > 0
    print(f"  Phase capacity: {cap:,} bytes")


def test_payload_too_large():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier, ext=".wav")
    with pytest.raises(ValueError):
        encoder.encode(carrier, b"X" * (cap + 1), ext=".wav")


def test_roundtrip_longer_text():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier, ext=".wav")
    payload = b"P" * min(cap, 32)
    stego = encoder.encode(carrier, payload, ext=".wav")
    result = encoder.decode(stego, ext=".wav")
    assert result == payload
