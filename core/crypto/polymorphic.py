"""
core/crypto/polymorphic.py — key-seeded embedding order.

A keyed embed visits carrier samples in an order derived from the passphrase,
so the payload is not stored contiguously from the first pixel. This is
traversal obfuscation, NOT encryption: confidentiality always comes from
AES-256-GCM (``core/crypto/aes.py``), and the order is derived with a single
SHA-256, so it must not be relied upon against an attacker who can try
passphrases offline.

Two orders exist:

* ``keyed_permutation``  — the order used by every new keyed embed. It uses
  NumPy's *legacy* ``RandomState`` (MT19937), whose output stream NumPy
  freezes and guarantees across releases. ``numpy.random.Generator`` makes no
  such promise, and a stego tool must still be able to read a carrier years
  later.
* ``fisher_yates_indices`` — the LCG shuffle of StegoForge <= 1.1.5, kept only
  so that carriers written by those releases remain readable.
"""
from __future__ import annotations

import hashlib
import struct

import numpy as np


def derive_encoding_params(key: str) -> dict:
    """Derive traversal parameters deterministically from a passphrase.

    Returns a dict with ``row_reversed`` and ``shuffle_seed`` (used by the LSB
    encoder) plus ``channel_order`` / ``bit_position`` (reserved; the shipped
    encoders do not consume them).
    """
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return {
        "channel_order": sorted([0, 1, 2], key=lambda i: digest[i]),
        "bit_position": digest[3] % 4,
        "row_reversed": digest[4] % 2 == 0,
        "shuffle_seed": struct.unpack(">Q", digest[5:13])[0],
    }


def keyed_permutation(n: int, seed: int) -> np.ndarray:
    """Return a deterministic permutation of ``range(n)`` as an int64 array.

    Frozen across NumPy versions (legacy ``RandomState`` + ``init_by_array``).
    """
    if n <= 0:
        return np.empty(0, dtype=np.int64)
    seed = int(seed) & 0xFFFFFFFFFFFFFFFF
    state = np.random.RandomState(np.array([seed & 0xFFFFFFFF, seed >> 32], dtype=np.uint32))
    return state.permutation(n)


def fisher_yates_indices(n: int, seed: int) -> list[int]:
    """Legacy (<= 1.1.5) LCG Fisher-Yates order. Read-compatibility only."""
    if n <= 0:
        return []
    indices = list(range(n))
    state = seed & 0xFFFFFFFFFFFFFFFF
    for i in range(n - 1, 0, -1):
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        j = state % (i + 1)
        indices[i], indices[j] = indices[j], indices[i]
    return indices
