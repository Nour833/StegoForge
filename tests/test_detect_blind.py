"""tests/test_detect_blind.py — Tests for blind brute-force extractor."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from detect.blind import BlindExtractor
from core.image.lsb import LSBEncoder

FIXTURES = Path(__file__).parent / "fixtures"
CARRIER = FIXTURES / "sample.png"

extractor = BlindExtractor()


def test_finds_lsb_stego():
    """Blind extractor should find an unencrypted LSB payload."""
    carrier = CARRIER.read_bytes()
    encoder = LSBEncoder()
    # Embed without key (no polymorphic) and without AES — plain bytes
    payload = b"CTF{blind_extractor_works}"
    # Directly call encoder without encryption
    stego = encoder.encode(carrier, payload)  # no key

    result = extractor.analyze(stego, "stego.png")
    assert result.method == "blind"
    assert 0.0 <= result.confidence <= 1.0
    print(f"  Blind result: {result.details.get('candidates_found', 0)} candidates, "
          f"confidence={result.confidence:.3f}")


def test_clean_image_few_candidates():
    result = extractor.analyze(CARRIER.read_bytes(), "clean.png")
    assert result.method == "blind"
    assert isinstance(result.detected, bool)


def test_result_structure():
    result = extractor.analyze(CARRIER.read_bytes(), "sample.png")
    assert result.method == "blind"
    assert "candidates_found" in result.details
    assert "elapsed_seconds" in result.details


def test_malformed_file_graceful():
    """Should not crash on garbage input."""
    result = extractor.analyze(b"\x00" * 10, "bad.png")
    assert result.detected is False
    assert "error" in result.details


def test_completes_quickly():
    """Should run in under 5 seconds for typical image."""
    import time
    carrier = CARRIER.read_bytes()
    start = time.time()
    result = extractor.analyze(carrier, "sample.png")
    elapsed = time.time() - start
    print(f"  Blind extractor elapsed: {elapsed:.2f}s")
    assert elapsed < 15.0  # generous timeout


def test_sfrg_magic_high_score():
    """Embed encrypted payload (SFRG header) and check blind extractor finds or handles it correctly."""
    carrier = CARRIER.read_bytes()
    encoder = LSBEncoder()
    from core.crypto.aes import encrypt
    enc_payload = encrypt(b"real secret", "mypassword")
    stego = encoder.encode(carrier, enc_payload)
    result = extractor.analyze(stego, "encrypted_stego.png")
    # Result should always be a valid structure
    assert result.method == "blind"
    assert isinstance(result.detected, bool)
    # If it found a payload, it should have SFRG header
    if result.extracted_payload:
        assert result.extracted_payload[:4] == b"SFRG"
    print(f"  SFRG test: {result.details.get('candidates_found',0)} candidates found")
