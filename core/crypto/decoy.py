"""
core/crypto/decoy.py — Dual-payload deniability system.

Decoy mode stores two separately encrypted payloads in the same carrier.

Wire format embedded in carrier:
  [decoy_payload_encrypted | 4-byte separator: b'DCOY' | real_payload_encrypted]

- The decoy payload is placed FIRST (found by naive extractors).
- The real payload follows after the DCOY separator.

On decode:
  - If key decrypts the decoy slot → returns decoy payload.
  - If key decrypts the real slot  → returns real payload.
  - The separator is only meaningful to someone who knows to look past the decoy.
  - Neither key reveals the other slot exists.

This gives plausible deniability: under duress, reveal the decoy key.
The real payload is invisible to anyone without the real key.
"""
from . import aes

SEPARATOR = b'DCOY'
SEP_LEN = 4


def encode_dual(
    decoy_payload: bytes,
    decoy_key: str,
    real_payload: bytes,
    real_key: str,
) -> bytes:
    """
    Combine decoy and real payloads into a single byte string for embedding.

    Returns: bytes to embed in carrier.
    """
    decoy_enc = aes.encrypt(decoy_payload, decoy_key)
    real_enc = aes.encrypt(real_payload, real_key)
    return decoy_enc + SEPARATOR + real_enc


def decode_dual(data: bytes, key: str) -> bytes:
    """
    Extract and decrypt the appropriate payload given a key.

    Tries the decoy slot first, then the real slot.
    Returns the decrypted payload for whichever slot the key unlocks.

    Raises:
        ValueError: If the key does not unlock either slot.
    """
    if SEPARATOR not in data:
        # Single payload — not dual mode, try straight decrypt
        return aes.decrypt(data, key)

    sep_idx = data.find(SEPARATOR)
    decoy_enc = data[:sep_idx]
    real_enc = data[sep_idx + SEP_LEN:]

    # Try decoy slot first
    try:
        return aes.decrypt(decoy_enc, key)
    except ValueError:
        pass

    # Try real slot
    try:
        return aes.decrypt(real_enc, key)
    except ValueError:
        pass

    raise ValueError("Decryption failed — key does not match any payload slot")


def split_slots(data: bytes) -> tuple[bytes, bytes] | None:
    """
    Split dual-payload data into (decoy_enc, real_enc) byte strings.
    Returns None if data is not in dual-payload format.
    """
    if SEPARATOR not in data:
        return None
    sep_idx = data.find(SEPARATOR)
    return data[:sep_idx], data[sep_idx + SEP_LEN:]
