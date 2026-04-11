"""
protocol/keyexchange.py - Steganographic X25519 key exchange.

Security note:
The local private key file is encrypted with a local passphrase. If this file
or passphrase is compromised, an attacker can derive session secrets from any
intercepted peer public key carrier.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.crypto.kdf import derive_key

MAGIC = b"SKX1"
SALT_LEN = 16
NONCE_LEN = 12


def generate_ephemeral_keypair() -> tuple[bytes, bytes]:
    priv = X25519PrivateKey.generate()
    pub = priv.public_key()
    priv_raw = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return priv_raw, pub_raw


def encrypt_private_key(private_key_raw: bytes, passphrase: str) -> bytes:
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(passphrase, salt)
    ct = AESGCM(key).encrypt(nonce, private_key_raw, None)
    return MAGIC + salt + nonce + ct


def decrypt_private_key(blob: bytes, passphrase: str) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("Invalid keyx private key file format")
    salt = blob[4:4 + SALT_LEN]
    nonce = blob[4 + SALT_LEN:4 + SALT_LEN + NONCE_LEN]
    ct = blob[4 + SALT_LEN + NONCE_LEN:]
    key = derive_key(passphrase, salt)
    try:
        return AESGCM(key).decrypt(nonce, ct, None)
    except Exception as exc:
        raise ValueError("Failed to decrypt local private key file") from exc


def save_private_key_file(path: str, private_key_raw: bytes, passphrase: str) -> str:
    blob = encrypt_private_key(private_key_raw, passphrase)
    p = Path(path)
    p.write_bytes(blob)
    return str(p)


def load_private_key_file(path: str, passphrase: str) -> bytes:
    return decrypt_private_key(Path(path).read_bytes(), passphrase)


def derive_shared_secret(private_key_raw: bytes, peer_public_raw: bytes) -> bytes:
    priv = X25519PrivateKey.from_private_bytes(private_key_raw)
    pub = X25519PublicKey.from_public_bytes(peer_public_raw)
    return priv.exchange(pub)


def derive_session_key_hex(shared_secret: bytes) -> str:
    # Reuse Argon2 KDF style hardening with deterministic salt from shared secret.
    salt = shared_secret[:16]
    out = derive_key(shared_secret.hex(), salt)
    return out.hex()
