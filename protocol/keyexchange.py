"""
protocol/keyexchange.py - Steganographic X25519 key exchange (v1/v2).

v1: raw X25519 exchange + HKDF-SHA256(info=b"stegoforge-keyx-v1").
v2: peer-bound HKDF(info includes both public keys) + optional Ed25519
  signatures for MITM resistance. v1 still accepted for compatibility.

Security note:
The local private key file is encrypted with a local passphrase. If this file
or passphrase is compromised, an attacker can derive session secrets from any
intercepted peer public key carrier. v2 signatures mitigate active MITM but
require out-of-band identity verification.
"""
from __future__ import annotations

import contextlib
import logging

import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from core.crypto.kdf import derive_key

log = logging.getLogger(__name__)

MAGIC = b"SKX1"        # private-key files written by StegoForge <= 1.1.5 (legacy KDF profile), read-only
MAGIC_V2 = b"SKX2"
MAGIC_V3 = b"SKX3"     # current private-key files (v3 KDF profile, header authenticated)
PROTOCOL_VERSION = 2
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
    key = derive_key(passphrase, salt, profile="v3")
    ct = AESGCM(key).encrypt(nonce, private_key_raw, MAGIC_V3)
    return MAGIC_V3 + salt + nonce + ct


def decrypt_private_key(blob: bytes, passphrase: str) -> bytes:
    """Open a private-key file: current ``SKX3`` files, or ``SKX1`` files from StegoForge <= 1.1.5."""
    if blob.startswith(MAGIC_V3):
        profile, aad = "v3", MAGIC_V3
    elif blob.startswith(MAGIC):
        profile, aad = "legacy", None
    else:
        raise ValueError("Invalid keyx private key file format")
    salt = blob[4:4 + SALT_LEN]
    nonce = blob[4 + SALT_LEN:4 + SALT_LEN + NONCE_LEN]
    ct = blob[4 + SALT_LEN + NONCE_LEN:]
    if len(salt) != SALT_LEN or len(nonce) != NONCE_LEN or not ct:
        raise ValueError("Invalid keyx private key file format")
    try:
        key = derive_key(passphrase, salt, profile=profile)
        return AESGCM(key).decrypt(nonce, ct, aad)
    except Exception as exc:
        raise ValueError("Failed to decrypt local private key file") from exc


def public_from_private(private_key_raw: bytes) -> bytes:
    """The X25519 public key belonging to a raw private key."""
    return X25519PrivateKey.from_private_bytes(private_key_raw).public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )


def save_private_key_file(path: str, private_key_raw: bytes, passphrase: str) -> str:
    blob = encrypt_private_key(private_key_raw, passphrase)
    p = Path(path)
    # 0o600: private key material must never be world-readable.
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
    except Exception:
        with contextlib.suppress(OSError):
            os.close(fd)
        raise
    with contextlib.suppress(OSError):
        os.chmod(str(p), 0o600)
    return str(p)


def load_private_key_file(path: str, passphrase: str) -> bytes:
    return decrypt_private_key(Path(path).read_bytes(), passphrase)


def derive_shared_secret(private_key_raw: bytes, peer_public_raw: bytes) -> bytes:
    priv = X25519PrivateKey.from_private_bytes(private_key_raw)
    pub = X25519PublicKey.from_public_bytes(peer_public_raw)
    return priv.exchange(pub)


def derive_session_key_hex(shared_secret: bytes) -> str:
    # HKDF-SHA256 with domain separation: proper KDF for DH output.
    # Never reuse the password-KDF with a deterministic salt here.
    if len(shared_secret) < 16:
        raise ValueError("Invalid shared secret length")
    out = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"stegoforge-keyx-v1",
    ).derive(shared_secret)
    return out.hex()


def derive_session_key_hex_1_1_5(shared_secret: bytes) -> str:
    """The session key StegoForge <= 1.1.5 derived: Argon2id (legacy profile) over the shared secret.

    Kept only so a key exchange with a peer still running <= 1.1.5 yields the same key
    (``keyx complete --legacy-v1``). It is not bound to either public key.
    """
    return derive_key(shared_secret.hex(), shared_secret[:16], profile="legacy").hex()


def derive_session_key_hex_v2(shared_secret: bytes, local_pub: bytes, peer_pub: bytes) -> str:
    """v2 peer-bound session key: binds both identities into HKDF info."""
    if len(shared_secret) < 16:
        raise ValueError("Invalid shared secret length")
    if len(local_pub) != 32 or len(peer_pub) != 32:
        raise ValueError("Invalid public key length for v2 derivation")
    a, b = sorted([bytes(local_pub), bytes(peer_pub)])
    info = b"stegoforge-keyx-v2|" + a + b"|" + b
    out = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(shared_secret)
    return out.hex()


def generate_signing_keypair() -> tuple[bytes, bytes]:
    """Generate Ed25519 signing keypair for authenticated key exchange."""
    priv = Ed25519PrivateKey.generate()
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


def sign_exchange(private_sign_raw: bytes, payload: bytes) -> bytes:
    """Sign key-exchange payload; returns 64-byte signature."""
    priv = Ed25519PrivateKey.from_private_bytes(private_sign_raw)
    return priv.sign(payload)


def verify_exchange(public_sign_raw: bytes, signature: bytes, payload: bytes) -> None:
    """Verify key-exchange signature; raises ValueError on failure."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(public_sign_raw)
        pub.verify(signature, payload)
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("Key-exchange signature verification failed (possible MITM)") from exc
