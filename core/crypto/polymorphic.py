"""
core/crypto/polymorphic.py — Key-seeded encoding parameter variation.

Polymorphic encoding derives encoding parameters from the key itself,
so two embeds of the same payload with different keys use different:
  - channel_order: e.g. [2, 0, 1] (B, R, G)
  - bit_position: 0–3 (which LSB layer to use)
  - row_direction: normal or reversed row traversal
  - shuffle_seed: seed for Fisher-Yates pixel order shuffle

This defeats signature-based steganalysis: tools looking for a fixed
pattern of modified bits will not find a consistent signature.
"""
import hashlib
import struct


def derive_encoding_params(key: str) -> dict:
    """
    Derive encoding parameters deterministically from a password/key.

    Args:
        key: The user's password string.

    Returns:
        dict with keys: channel_order, bit_position, row_reversed, shuffle_seed.
    """
    digest = hashlib.sha256(key.encode()).digest()

    # Channel order: sort [0,1,2] by bytes in digest → deterministic permutation
    channel_order = sorted([0, 1, 2], key=lambda i: digest[i])

    # Bit position: which LSB layer (0=LSB, 1=next, etc.)
    bit_position = digest[3] % 4

    # Row direction
    row_reversed = (digest[4] % 2 == 0)

    # Shuffle seed: 8-byte integer from digest bytes 5–12
    shuffle_seed = struct.unpack(">Q", digest[5:13])[0]

    return {
        "channel_order": channel_order,
        "bit_position": bit_position,
        "row_reversed": row_reversed,
        "shuffle_seed": shuffle_seed,
    }


def fisher_yates_indices(n: int, seed: int) -> list[int]:
    """
    Generate a Fisher-Yates shuffled index sequence [0..n-1] using the given seed.

    This allows reproducible pixel traversal order that varies by key.
    """
    indices = list(range(n))
    # Simple LCG-based shuffle for determinism (not security-critical here —
    # security comes from AES encryption, not obscure traversal order)
    state = seed
    for i in range(n - 1, 0, -1):
        state = (state * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFFFFFFFFFF
        j = state % (i + 1)
        indices[i], indices[j] = indices[j], indices[i]
    return indices
