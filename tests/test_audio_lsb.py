"""tests/test_audio_lsb.py — Tests for audio LSB steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.audio.lsb import AudioLSBEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.wav"

encoder = AudioLSBEncoder()


def test_roundtrip():
    carrier = CARRIER.read_bytes()
    payload = b"Audio LSB test payload!"
    stego = encoder.encode(carrier, payload, ext=".wav")
    result = encoder.decode(stego, ext=".wav")
    assert result == payload


def test_capacity():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier, ext=".wav")
    assert cap > 0
    print(f"  Audio LSB capacity: {cap:,} bytes")


def test_payload_too_large():
    carrier = CARRIER.read_bytes()
    cap = encoder.capacity(carrier, ext=".wav")
    with pytest.raises(ValueError, match="Payload too large"):
        encoder.encode(carrier, b"X" * (cap + 1), ext=".wav")


def test_roundtrip_binary():
    carrier = CARRIER.read_bytes()
    payload = bytes(range(256)) * 5
    stego = encoder.encode(carrier, payload, ext=".wav")
    result = encoder.decode(stego, ext=".wav")
    assert result == payload


def test_output_is_wav():
    """Output should be a valid WAV file."""
    import wave
    import io as sio
    carrier = CARRIER.read_bytes()
    stego = encoder.encode(carrier, b"test", ext=".wav")
    with wave.open(sio.BytesIO(stego)) as wf:
        assert wf.getnframes() > 0
