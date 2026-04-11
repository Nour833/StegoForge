"""tests/test_document_linguistic.py - Tests for linguistic steganography."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.document.linguistic import LinguisticEncoder


def _cover_text() -> bytes:
    # Repeat eligible synonyms to provide useful capacity.
    words = []
    base = [
        "quick", "small", "big", "smart", "begin", "end", "buy", "ask",
        "help", "hard", "easy", "calm", "loud", "happy", "sad", "error",
    ]
    for _ in range(60):
        words.extend(base)
    return (" ".join(words) + ".").encode("utf-8")


def test_roundtrip():
    enc = LinguisticEncoder()
    cover = _cover_text()
    payload = b"linguistic payload"
    stego = enc.encode(cover, payload)
    out = enc.decode(stego)
    assert out == payload


def test_capacity_positive():
    enc = LinguisticEncoder()
    assert enc.capacity(_cover_text()) > 0
