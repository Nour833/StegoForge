"""
core/crypto/aes.py — AES-256-GCM envelopes (Argon2id key derivation).

Wire formats
============

v1 — legacy, written by StegoForge <= 1.1.5 (always readable)::

    'SFRG' | salt(16) | nonce(12) | ciphertext+tag(16)
    KDF profile "legacy" (Argon2id t=2), no AAD.

v3 — the format for every new standard embed::

    'SFRG' | 0x03 | flags(1) | salt(16) | nonce(12) | ciphertext+tag(16)
    KDF profile "v3" (Argon2id t=3, NFC passphrase).
    AAD = b"stegoforge|v3|" + version + flags + method
    flags bit 0: the plaintext carries ISO/IEC 7816-4 padding (0x80 0x00 ...).

The header, the flags and the carrier method are authenticated, so a payload
cannot be replayed into a different method and the padding flag can never be
flipped. Padding is signalled by the flag instead of being guessed at decode
time: guessing silently truncated any unpadded payload that happened to end in
bytes such as 0x01.

obfuscated — ``--no-magic``; carries *no* fixed bytes at all::

    salt(16) | nonce(12) | ciphertext+tag(16)
    KDF profile "v3", AAD = b"stegoforge|obf|" + method, always padded.

There is deliberately no key-derived marker: a marker derived from the
passphrase with a fast hash would let an attacker test passphrases at
SHA-256 speed and bypass the Argon2 work factor entirely. A decoder simply
tries the authenticated decryption; GCM is the only oracle.
"""
from __future__ import annotations

import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.errors import DecryptionError

from .kdf import SALT_LEN, derive_key

MAGIC = b"SFRG"
MAGIC_LEN = len(MAGIC)
NONCE_LEN = 12
TAG_LEN = 16
VERSION_V3 = 0x03
FLAG_PADDED = 0x01

HEADER_LEN_V1 = MAGIC_LEN + SALT_LEN + NONCE_LEN          # 32
HEADER_LEN_V3 = MAGIC_LEN + 2 + SALT_LEN + NONCE_LEN      # 34
OBF_HEADER_LEN = SALT_LEN + NONCE_LEN                     # 28
OBF_PAD_BLOCK = 16
MAX_PAD_BLOCK = 65536

_FAIL = "Decryption failed — wrong password or corrupted data"


# ── ISO/IEC 7816-4 padding ────────────────────────────────────────────────────

def iso_pad(data: bytes, block: int) -> bytes:
    """Pad ``data`` with 0x80 then zeros to a multiple of ``block`` (always >= 1 byte)."""
    if not 1 <= int(block) <= MAX_PAD_BLOCK:
        raise ValueError(f"pad block must be 1-{MAX_PAD_BLOCK}")
    total = -(-(len(data) + 1) // block) * block
    return bytes(data) + b"\x80" + b"\x00" * (total - len(data) - 1)


def iso_pad_to(data: bytes, total_len: int) -> bytes:
    """Pad ``data`` to exactly ``total_len`` bytes (needs at least one spare byte)."""
    if total_len < len(data) + 1:
        raise ValueError("target length too small for padding")
    return bytes(data) + b"\x80" + b"\x00" * (total_len - len(data) - 1)


def iso_unpad(padded: bytes) -> bytes:
    """Strip ISO/IEC 7816-4 padding; raises ValueError if it is malformed."""
    stripped = bytes(padded).rstrip(b"\x00")
    if not stripped or stripped[-1] != 0x80:
        raise ValueError("invalid padding")
    return stripped[:-1]


# ── helpers ───────────────────────────────────────────────────────────────────

def _method_bytes(method: str | None) -> bytes:
    return (method or "").strip().lower().encode("utf-8")


def _aad_v3(flags: int, method: str | None) -> bytes:
    return b"stegoforge|v3|" + bytes([VERSION_V3, flags]) + _method_bytes(method)


def _aad_obf(method: str | None) -> bytes:
    return b"stegoforge|obf|" + _method_bytes(method)


def _decrypt_failed() -> DecryptionError:
    return DecryptionError(_FAIL)


# ── v3 envelope ───────────────────────────────────────────────────────────────

def encrypt_envelope(plaintext: bytes, password: str, method: str | None = None, pad_block: int = 0) -> bytes:
    """Encrypt into a v3 envelope bound to ``method``; optionally pad to ``pad_block``."""
    flags = 0
    data = bytes(plaintext)
    if pad_block:
        data = iso_pad(data, int(pad_block))
        flags |= FLAG_PADDED
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(password, salt, profile="v3")
    ct = AESGCM(key).encrypt(nonce, data, _aad_v3(flags, method))
    return MAGIC + bytes([VERSION_V3, flags]) + salt + nonce + ct


def _open_v3(data: bytes, password: str, method: str | None) -> bytes:
    if len(data) < HEADER_LEN_V3 + TAG_LEN:
        raise _decrypt_failed()
    flags = data[MAGIC_LEN + 1]
    salt = data[MAGIC_LEN + 2:MAGIC_LEN + 2 + SALT_LEN]
    nonce = data[MAGIC_LEN + 2 + SALT_LEN:HEADER_LEN_V3]
    try:
        key = derive_key(password, salt, profile="v3")
        plain = AESGCM(key).decrypt(nonce, data[HEADER_LEN_V3:], _aad_v3(flags, method))
        return iso_unpad(plain) if flags & FLAG_PADDED else plain
    except Exception:
        raise _decrypt_failed() from None


def decrypt_envelope(data: bytes, password: str, method: str | None = None, *, require_v3: bool = False) -> bytes:
    """Decrypt a v3 envelope, or a legacy v1 blob unless ``require_v3``.

    Raises:
        DecryptionError: (a ``ValueError``) with one generic message for every
            failure mode, so callers cannot tell truncation from a wrong key.
    """
    data = bytes(data)
    if not data.startswith(MAGIC):
        raise _decrypt_failed()
    looks_v3 = (
        len(data) >= HEADER_LEN_V3 + TAG_LEN
        and data[MAGIC_LEN] == VERSION_V3
        and data[MAGIC_LEN + 1] & ~FLAG_PADDED == 0
    )
    if looks_v3:
        try:
            return _open_v3(data, password, method)
        except DecryptionError:
            if require_v3:
                raise
            # ~1 in 256 legacy blobs start their salt with 0x03: fall through.
    if require_v3:
        raise _decrypt_failed()
    return decrypt(data, password)


# ── obfuscated (no fixed bytes) ───────────────────────────────────────────────

def seal_obfuscated_padded(padded: bytes, password: str, method: str | None = None) -> bytes:
    """Encrypt already-padded plaintext into ``salt | nonce | ciphertext+tag``."""
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(password, salt, profile="v3")
    return salt + nonce + AESGCM(key).encrypt(nonce, bytes(padded), _aad_obf(method))


def open_obfuscated_padded(blob: bytes, password: str, method: str | None = None) -> bytes:
    """Authenticate and decrypt an obfuscated blob; returns the *padded* plaintext."""
    blob = bytes(blob)
    if len(blob) < OBF_HEADER_LEN + TAG_LEN + 1:
        raise _decrypt_failed()
    salt = blob[:SALT_LEN]
    nonce = blob[SALT_LEN:OBF_HEADER_LEN]
    try:
        key = derive_key(password, salt, profile="v3")
        return AESGCM(key).decrypt(nonce, blob[OBF_HEADER_LEN:], _aad_obf(method))
    except Exception:
        raise _decrypt_failed() from None


def encrypt_obfuscated(plaintext: bytes, password: str, method: str | None = None,
                       pad_block: int = OBF_PAD_BLOCK) -> bytes:
    """``--no-magic`` encryption: header-less, always padded (default 16-byte blocks)."""
    return seal_obfuscated_padded(iso_pad(plaintext, int(pad_block or OBF_PAD_BLOCK)), password, method)


def decrypt_obfuscated(blob: bytes, password: str, method: str | None = None) -> bytes:
    padded = open_obfuscated_padded(blob, password, method)
    try:
        return iso_unpad(padded)
    except ValueError:
        raise _decrypt_failed() from None


# ── unified decoder ───────────────────────────────────────────────────────────

def decrypt_any(data: bytes, password: str, method: str | None = None, *, require_v3: bool = False) -> bytes:
    """Decrypt any StegoForge single-payload blob (v3, legacy v1, obfuscated)."""
    if bytes(data[:MAGIC_LEN]) == MAGIC:
        try:
            return decrypt_envelope(data, password, method, require_v3=require_v3)
        except DecryptionError:
            pass  # an obfuscated blob can begin with 'SFRG' by chance (2**-32)
    return decrypt_obfuscated(data, password, method)


# ── legacy v1 (kept: interop and the regression vectors) ──────────────────────

def encrypt(plaintext: bytes, password: str) -> bytes:
    """Encrypt into the legacy v1 format. New embeds use :func:`encrypt_envelope`."""
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(password, salt, profile="legacy")
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, bytes(plaintext), None)


def decrypt(data: bytes, password: str) -> bytes:
    """Decrypt a legacy v1 blob (anything StegoForge <= 1.1.5 wrote).

    Raises:
        DecryptionError: one generic message for every failure mode.
    """
    data = bytes(data)
    if len(data) < HEADER_LEN_V1 + TAG_LEN or not data.startswith(MAGIC):
        raise _decrypt_failed()
    salt = data[MAGIC_LEN:MAGIC_LEN + SALT_LEN]
    nonce = data[MAGIC_LEN + SALT_LEN:HEADER_LEN_V1]
    try:
        key = derive_key(password, salt, profile="legacy")
        return AESGCM(key).decrypt(nonce, data[HEADER_LEN_V1:], None)
    except Exception:
        raise _decrypt_failed() from None


def is_encrypted(data: bytes) -> bool:
    """Return True if ``data`` starts with the ``SFRG`` envelope magic."""
    return bytes(data[:MAGIC_LEN]) == MAGIC
