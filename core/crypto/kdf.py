"""
core/crypto/kdf.py — Argon2id key derivation function.
"""
from argon2.low_level import hash_secret_raw, Type


def derive_key(password: str, salt: bytes, key_len: int = 32) -> bytes:
    """
    Derive a cryptographic key from a password using Argon2id.

    Parameters are deliberately modest for speed on low-end machines,
    while still providing strong protection against brute-force attacks.
    Salt must be exactly 16 bytes.

    Args:
        password: The user's passphrase.
        salt: 16 random bytes (stored in the encrypted payload header).
        key_len: Output key length in bytes (default: 32 for AES-256).

    Returns:
        Derived key bytes of length key_len.
    """
    if len(salt) != 16:
        raise ValueError(f"Salt must be 16 bytes, got {len(salt)}")
    return hash_secret_raw(
        secret=password.encode(),
        salt=salt,
        time_cost=2,
        memory_cost=65536,
        parallelism=2,
        hash_len=key_len,
        type=Type.ID,
    )
