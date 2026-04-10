"""tests/test_audio_spectrogram.py — Tests for audio spectrogram steganography."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.audio.spectrogram import SpectrogramEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.wav"

encoder = SpectrogramEncoder()


def test_encode_text():
    """Encoding text should produce a valid WAV file."""
    import wave
    import io
    carrier = CARRIER.read_bytes()
    payload = b"STEGOFORGE"
    stego = encoder.encode(carrier, payload, ext=".wav")
    assert len(stego) > 0
    # Should be valid WAV
    with wave.open(io.BytesIO(stego)) as wf:
        assert wf.getnframes() > 0


def test_decode_returns_png():
    """Decode should return a spectrogram image as PNG."""
    carrier = CARRIER.read_bytes()
    payload = b"HELLO WORLD"
    stego = encoder.encode(carrier, payload, ext=".wav")
    spec_png = encoder.decode(stego, ext=".wav")
    # Should start with PNG magic
    assert spec_png[:4] == b"\x89PNG", "Decode should return a PNG spectrogram image"


def test_carrier_length_preserved():
    """Stego file should have similar duration to original."""
    import wave
    import io as sio
    carrier = CARRIER.read_bytes()
    payload = b"test"
    stego = encoder.encode(carrier, payload, ext=".wav")
    with wave.open(sio.BytesIO(carrier)) as wf:
        orig_dur = wf.getnframes() / wf.getframerate()
    with wave.open(sio.BytesIO(stego)) as wf:
        stego_dur = wf.getnframes() / wf.getframerate()
    assert abs(orig_dur - stego_dur) < 1.0


def test_encode_image_payload():
    """Encoded PNG image should produce valid stego audio."""
    import io
    from PIL import Image
    import wave

    img = Image.new("L", (32, 32))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    payload = buf.getvalue()

    carrier = CARRIER.read_bytes()
    stego = encoder.encode(carrier, payload, ext=".wav")
    with wave.open(io.BytesIO(stego)) as wf:
        assert wf.getnframes() > 0
