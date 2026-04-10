"""
core/crypto/aes.py — AES-256-GCM encryption/decryption.

Wire format for encrypted payload:
  [4 bytes magic: b'SFRG']
  [16 bytes Argon2 salt]
  [12 bytes AES-GCM nonce]
  [N bytes ciphertext + 16 byte GCM tag appended by AESGCM]

On decode: if magic not found, raise ValueError("No encrypted payload found").
"""
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from .kdf import derive_key

MAGIC = b'SFRG'
MAGIC_LEN = 4
SALT_LEN = 16
NONCE_LEN = 12
HEADER_LEN = MAGIC_LEN + SALT_LEN + NONCE_LEN  # 32 bytes total


def encrypt(plaintext: bytes, password: str) -> bytes:
    """
    Encrypt plaintext with AES-256-GCM using Argon2id key derivation.

    Returns the wire-format bytes including magic, salt, nonce, and ciphertext.
    """
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return MAGIC + salt + nonce + ciphertext


def decrypt(data: bytes, password: str) -> bytes:
    """
    Decrypt AES-256-GCM ciphertext.

    Raises:
        ValueError: If magic header is missing or decryption fails (wrong password).
    """
    if not data.startswith(MAGIC):
        raise ValueError("No encrypted payload found")
    salt = data[MAGIC_LEN:MAGIC_LEN + SALT_LEN]
    nonce = data[MAGIC_LEN + SALT_LEN:HEADER_LEN]
    ciphertext = data[HEADER_LEN:]
    key = derive_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError("Decryption failed — wrong password or corrupted data")


def is_encrypted(data: bytes) -> bool:
    """Return True if data starts with the SFRG magic header."""
    return data[:MAGIC_LEN] == MAGIC
