"""
core/crypto/decoy.py — dual-payload plausible deniability.

Container (all new embeds)::

    blob(decoy) | blob(real)

Both blobs are header-less obfuscated AES-GCM blobs (see ``aes.py``) whose
plaintexts were padded to the *same* length, so the two halves are exactly
the same size. There is no magic, no length prefix and no separator: the
container is a run of uniformly random-looking bytes, and nothing in it tells
an examiner which half (if any) is the "real" one or whether a second slot
exists at all. A key opens whichever half it authenticates; the other half is
indistinguishable from random data.

Deniability here is exactly as strong as the examiner's inability to prove
that the second half is not random padding. It holds against someone who has
only the carrier; it is not a defence against an adversary who can compel
*both* keys, or who has an unmodified copy of the carrier to diff against.

Legacy v1 containers (StegoForge <= 1.1.5)::

    SFRG-blob(decoy) | b'DCOY' | SFRG-blob(real)

are still read, but never written.
"""
from __future__ import annotations

from core.errors import DecryptionError

from . import aes

SEPARATOR = b"DCOY"          # legacy v1 only
_MAX_LEGACY_SPLITS = 8        # 'DCOY' can occur inside random ciphertext by chance
_MIN_BLOB = aes.OBF_HEADER_LEN + aes.TAG_LEN + 1


def encode_dual(
    decoy_payload: bytes,
    decoy_key: str,
    real_payload: bytes,
    real_key: str,
    method: str | None = None,
    pad_block: int = aes.OBF_PAD_BLOCK,
) -> bytes:
    """Combine a decoy and a real payload into one container to embed."""
    if not decoy_payload or not real_payload:
        raise ValueError("Decoy and real payloads must both be non-empty")
    if not decoy_key or not real_key:
        raise ValueError("Decoy mode needs both a decoy key and a real key")
    if decoy_key == real_key:
        raise ValueError("Decoy key and real key must differ")
    block = int(pad_block or aes.OBF_PAD_BLOCK)
    total = -(-(max(len(decoy_payload), len(real_payload)) + 1) // block) * block
    slot_a = aes.seal_obfuscated_padded(aes.iso_pad_to(decoy_payload, total), decoy_key, method)
    slot_b = aes.seal_obfuscated_padded(aes.iso_pad_to(real_payload, total), real_key, method)
    return slot_a + slot_b


def _split_even(data: bytes) -> tuple[bytes, bytes] | None:
    if len(data) % 2 or len(data) // 2 < _MIN_BLOB:
        return None
    half = len(data) // 2
    return data[:half], data[half:]


def _legacy_splits(data: bytes) -> list[tuple[bytes, bytes]]:
    out: list[tuple[bytes, bytes]] = []
    start = 0
    while len(out) < _MAX_LEGACY_SPLITS:
        idx = data.find(SEPARATOR, start)
        if idx < 0:
            break
        out.append((data[:idx], data[idx + len(SEPARATOR):]))
        start = idx + 1
    return out


def decode_dual(data: bytes, key: str, method: str | None = None) -> bytes:
    """Decrypt whichever slot ``key`` unlocks.

    Raises:
        DecryptionError: if ``key`` unlocks neither slot.
    """
    data = bytes(data)
    halves = _split_even(data)
    if halves is not None:
        for part in halves:
            try:
                return aes.decrypt_obfuscated(part, key, method)
            except DecryptionError:
                continue
    if data.startswith(aes.MAGIC):
        for first, second in _legacy_splits(data):
            for part in (first, second):
                try:
                    return aes.decrypt(part, key)
                except DecryptionError:
                    continue
    raise DecryptionError("Decryption failed — key does not match any payload slot")


def decrypt_container(data: bytes, key: str, method: str | None = None, *, require_v3: bool = False) -> bytes:
    """Open any StegoForge embed with ``key``: v3/v1 envelope, decoy container, or header-less blob.

    ``require_v3`` refuses everything written by StegoForge <= 1.1.5.

    Raises:
        DecryptionError: one generic message, whichever shape the data has.
    """
    data = bytes(data)
    if data.startswith(aes.MAGIC):
        try:
            return aes.decrypt_envelope(data, key, method, require_v3=require_v3)
        except DecryptionError:
            pass  # a decoy half or an obfuscated blob may begin with 'SFRG' by chance
    if not (require_v3 and data.startswith(aes.MAGIC)):
        try:
            return decode_dual(data, key, method)
        except DecryptionError:
            pass
    return aes.decrypt_obfuscated(data, key, method)
