"""tests/test_crypto_aes.py — Tests for AES-256-GCM crypto module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.crypto.aes import encrypt, decrypt, is_encrypted, MAGIC


def test_encrypt_returns_magic():
    data = encrypt(b"hello world", "mypassword")
    assert data[:4] == MAGIC


def test_roundtrip():
    plaintext = b"StegoForge secret payload 1234567890"
    encrypted = encrypt(plaintext, "testkey")
    decrypted = decrypt(encrypted, "testkey")
    assert decrypted == plaintext


def test_wrong_key_raises():
    encrypted = encrypt(b"secret", "rightkey")
    with pytest.raises(ValueError):
        decrypt(encrypted, "wrongkey")


def test_missing_magic_raises():
    with pytest.raises(ValueError, match="No encrypted payload found"):
        decrypt(b"BADMAGICBYTES" * 10, "anykey")


def test_is_encrypted():
    enc = encrypt(b"test", "key")
    assert is_encrypted(enc) is True
    assert is_encrypted(b"random bytes") is False


def test_large_payload():
    plaintext = b"A" * 100_000
    enc = encrypt(plaintext, "bigkey")
    dec = decrypt(enc, "bigkey")
    assert dec == plaintext


def test_different_salts():
    """Two encryptions of same plaintext should produce different ciphertext."""
    enc1 = encrypt(b"same", "key")
    enc2 = encrypt(b"same", "key")
    assert enc1 != enc2  # different salts → different ciphertext


def test_decoy_roundtrip():
    from core.crypto.decoy import encode_dual, decode_dual
    real = b"real secret"
    decoy = b"innocent content"
    combined = encode_dual(decoy, "decoykey", real, "realkey")

    result_real = decode_dual(combined, "realkey")
    result_decoy = decode_dual(combined, "decoykey")

    assert result_real == real
    assert result_decoy == decoy
