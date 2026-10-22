"""
core/crypto/kdf.py — Argon2id key derivation and passphrase hygiene.

Argon2 parameters are NOT stored in StegoForge wire formats, so they must
never change silently: doing so makes every previously written payload
undecryptable. Each parameter set is therefore a named *profile* that is
selected by the wire-format version, never by a global constant:

    legacy  Argon2id t=2, m=64 MiB, p=2     StegoForge <= 1.1.5 ("SFRG" v1)
    v3      Argon2id t=3, m=64 MiB, p=2     envelope v3 and obfuscated blobs

The v3 profile also normalises the passphrase to Unicode NFC so that the
same typed passphrase derives the same key on every platform / input method.
The legacy profile deliberately does not normalise: that would change keys
for existing data.
"""
from __future__ import annotations

import unicodedata

from argon2.low_level import Type, hash_secret_raw

SALT_LEN = 16

# profile -> (time_cost, memory_cost_kib, parallelism, normalise_nfc)
_PROFILES: dict[str, tuple[int, int, int, bool]] = {
    "legacy": (2, 65536, 2, False),
    "v3": (3, 65536, 2, True),
}

DEFAULT_PROFILE = "v3"


def derive_key(password: str, salt: bytes, key_len: int = 32, *, profile: str = DEFAULT_PROFILE) -> bytes:
    """Derive a ``key_len``-byte key from ``password`` with Argon2id.

    Args:
        password: The user's passphrase (must not be empty).
        salt: Exactly 16 random bytes, stored next to the ciphertext.
        key_len: Output length in bytes (32 for AES-256).
        profile: ``"v3"`` (default, all new data) or ``"legacy"`` (read
            payloads written by StegoForge <= 1.1.5).
    """
    try:
        time_cost, memory_cost, parallelism, normalise = _PROFILES[profile]
    except KeyError:
        raise ValueError(f"Unknown KDF profile: {profile!r}") from None
    if len(salt) != SALT_LEN:
        raise ValueError(f"Salt must be {SALT_LEN} bytes, got {len(salt)}")
    if not password:
        raise ValueError("Password must not be empty")
    if normalise:
        password = unicodedata.normalize("NFC", password)
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=key_len,
        type=Type.ID,
    )


def password_strength(password: str) -> tuple[int, str]:
    """Score passphrase strength 0-4 with a human-readable rating.

    Heuristic: length + character-class diversity. Not a full zxcvbn
    replacement, but sufficient to warn against trivial brute-force targets.
    Returns ``(score, label)`` where label is one of weak/fair/good/strong.
    """
    if not password:
        return 0, "weak"
    score = 0
    length = len(password)
    if length >= 8:
        score += 1
    if length >= 12:
        score += 1
    classes = sum([
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ])
    if classes >= 3:
        score += 1
    if length >= 16 and classes >= 3:
        score += 1
    score = max(0, min(4, score))
    label = "weak" if score <= 1 else ("fair" if score == 2 else ("good" if score == 3 else "strong"))
    return score, label


def is_weak_password(password: str) -> bool:
    """Return True if the passphrase scores weak (0-1)."""
    score, _ = password_strength(password)
    return score <= 1
