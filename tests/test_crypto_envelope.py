"""tests/test_crypto_envelope.py — AES-GCM envelopes, KDF profiles, padding, decoy container.

The legacy vectors in fixtures/legacy_v1_vectors.json were produced by the
*published* StegoForge 1.1.5 code. They must keep decrypting forever: changing
a KDF parameter without a format version silently destroys user data.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.crypto import aes, decoy
from core.crypto.kdf import derive_key, is_weak_password, password_strength
from core.errors import DecryptionError

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "legacy_v1_vectors.json").read_text())
PW = "Str0ng!Passphrase#99"


# ── legacy compatibility (the regression that motivated profiles) ─────────────

@pytest.mark.parametrize("vec", VECTORS["aes_v1"], ids=lambda v: v["blob_hex"][:12])
def test_legacy_v1_blobs_from_published_release_still_decrypt(vec):
    blob = bytes.fromhex(vec["blob_hex"])
    expected = bytes.fromhex(vec["plaintext_hex"])
    assert aes.decrypt(blob, vec["password"]) == expected
    assert aes.decrypt_envelope(blob, vec["password"]) == expected
    assert aes.decrypt_any(blob, vec["password"], "lsb") == expected


@pytest.mark.parametrize("vec", VECTORS["decoy_v1"], ids=lambda v: v["blob_hex"][:12])
def test_legacy_v1_decoy_containers_still_open(vec):
    blob = bytes.fromhex(vec["blob_hex"])
    assert decoy.decode_dual(blob, vec["decoy_key"]) == bytes.fromhex(vec["decoy_hex"])
    assert decoy.decode_dual(blob, vec["real_key"]) == bytes.fromhex(vec["real_hex"])


def test_require_v3_refuses_legacy_blob():
    vec = VECTORS["aes_v1"][0]
    with pytest.raises(DecryptionError):
        aes.decrypt_any(bytes.fromhex(vec["blob_hex"]), vec["password"], require_v3=True)


def test_kdf_profiles_are_distinct_and_unknown_profile_rejected():
    salt = bytes(range(16))
    assert derive_key("pw", salt, profile="legacy") != derive_key("pw", salt, profile="v3")
    with pytest.raises(ValueError):
        derive_key("pw", salt, profile="nope")


def test_v3_kdf_normalises_unicode_but_legacy_does_not():
    salt = bytes(range(16))
    composed, decomposed = "café", "café"
    assert derive_key(composed, salt, profile="v3") == derive_key(decomposed, salt, profile="v3")
    assert derive_key(composed, salt, profile="legacy") != derive_key(decomposed, salt, profile="legacy")


def test_kdf_rejects_bad_salt_and_empty_password():
    with pytest.raises(ValueError):
        derive_key("pw", b"short")
    with pytest.raises(ValueError):
        derive_key("", bytes(16))


# ── v3 envelope ───────────────────────────────────────────────────────────────

def test_v3_roundtrip_and_header_layout():
    blob = aes.encrypt_envelope(b"hello", PW, "lsb")
    assert blob[:4] == aes.MAGIC and blob[4] == aes.VERSION_V3 and blob[5] == 0
    assert aes.decrypt_envelope(blob, PW, "lsb") == b"hello"


def test_v3_is_bound_to_the_carrier_method():
    blob = aes.encrypt_envelope(b"top", PW, "lsb")
    with pytest.raises(DecryptionError):
        aes.decrypt_envelope(blob, PW, "dct")


def test_v3_wrong_key_truncation_and_garbage_share_one_message():
    blob = aes.encrypt_envelope(b"top", PW, "lsb")
    msgs = set()
    for bad in (lambda: aes.decrypt_envelope(blob, "wrong-pass", "lsb"),
                lambda: aes.decrypt_envelope(blob[:20], PW, "lsb"),
                lambda: aes.decrypt_envelope(b"BADMAGIC" * 10, PW, "lsb"),
                lambda: aes.decrypt(b"BADMAGICBYTES" * 10, PW)):
        with pytest.raises(ValueError) as exc:
            bad()
        msgs.add(str(exc.value))
    assert len(msgs) == 1 and "Decryption failed" in msgs.pop()


def test_v3_flags_are_authenticated():
    blob = bytearray(aes.encrypt_envelope(b"abc", PW, "lsb"))
    blob[5] ^= aes.FLAG_PADDED
    with pytest.raises(DecryptionError):
        aes.decrypt_envelope(bytes(blob), PW, "lsb")


def test_tampered_ciphertext_is_rejected():
    blob = bytearray(aes.encrypt_envelope(b"abcdef", PW, "lsb"))
    blob[-1] ^= 1
    with pytest.raises(DecryptionError):
        aes.decrypt_envelope(bytes(blob), PW, "lsb")


def test_same_plaintext_never_encrypts_identically():
    assert aes.encrypt_envelope(b"same", PW, "lsb") != aes.encrypt_envelope(b"same", PW, "lsb")


# ── padding: the "ends in 0x01" truncation regression ─────────────────────────

@pytest.mark.parametrize("tail", [b"\x01", b"\x02\x02", b"\x03\x03\x03", b"\x80", b"\x00\x00", b"\x80\x00"])
def test_unpadded_payload_with_padding_like_tail_survives_unchanged(tail):
    payload = b"important binary data " + tail
    assert aes.decrypt_any(aes.encrypt_envelope(payload, PW, "lsb"), PW, "lsb") == payload
    assert aes.decrypt_any(aes.encrypt_obfuscated(payload, PW, "lsb"), PW, "lsb") == payload


@pytest.mark.parametrize("block", [1, 7, 16, 128, 256, 1000])
@pytest.mark.parametrize("size", [0, 1, 15, 16, 17, 255, 256, 257])
def test_padding_roundtrip_for_every_block_and_length(block, size):
    payload = bytes((i * 31) % 256 for i in range(size))
    padded = aes.iso_pad(payload, block)
    assert len(padded) % block == 0 and len(padded) > size
    assert aes.iso_unpad(padded) == payload
    blob = aes.encrypt_envelope(payload, PW, "lsb", pad_block=block)
    assert blob[5] == aes.FLAG_PADDED
    assert aes.decrypt_envelope(blob, PW, "lsb") == payload
    assert (len(blob) - aes.HEADER_LEN_V3 - aes.TAG_LEN) % block == 0


def test_padding_hides_the_exact_length():
    sizes = {len(aes.encrypt_envelope(b"x" * n, PW, "lsb", pad_block=128)) for n in (1, 50, 100)}
    assert len(sizes) == 1


def test_iso_unpad_rejects_malformed_padding_and_bad_blocks():
    with pytest.raises(ValueError):
        aes.iso_unpad(b"abc")
    with pytest.raises(ValueError):
        aes.iso_unpad(b"\x00\x00")
    with pytest.raises(ValueError):
        aes.iso_pad(b"x", 0)
    with pytest.raises(ValueError):
        aes.iso_pad(b"x", aes.MAX_PAD_BLOCK + 1)


# ── obfuscated (--no-magic) ───────────────────────────────────────────────────

def test_obfuscated_blob_has_no_fixed_bytes_and_no_password_derived_marker():
    a = aes.encrypt_obfuscated(b"payload", PW, "lsb")
    b = aes.encrypt_obfuscated(b"payload", PW, "lsb")
    assert not a.startswith(aes.MAGIC)
    # Same key, method and plaintext must NOT share any prefix: a stable
    # key-derived marker would be a fast offline password oracle.
    assert a[:4] != b[:4]
    assert a != b


def test_obfuscated_roundtrip_wrong_key_and_method_binding():
    blob = aes.encrypt_obfuscated(b"payload", PW, "lsb")
    assert aes.decrypt_obfuscated(blob, PW, "lsb") == b"payload"
    with pytest.raises(DecryptionError):
        aes.decrypt_obfuscated(blob, "other-pass", "lsb")
    with pytest.raises(DecryptionError):
        aes.decrypt_obfuscated(blob, PW, "dct")


def test_decrypt_any_dispatches_all_formats():
    for blob in (aes.encrypt_envelope(b"p", PW, "lsb"),
                 aes.encrypt_envelope(b"p", PW, "lsb", pad_block=64),
                 aes.encrypt_obfuscated(b"p", PW, "lsb"),
                 aes.encrypt(b"p", PW)):
        assert aes.decrypt_any(blob, PW, "lsb") == b"p"


def test_legacy_blob_whose_salt_starts_with_version_byte_still_decrypts(monkeypatch):
    # ~1/256 legacy blobs begin their salt with 0x03 and look like v3.
    monkeypatch.setattr(os, "urandom", lambda n: b"\x03" + b"\x00" * (n - 1) if n == 16 else b"\x07" * n)
    blob = aes.encrypt(b"edge case", PW)
    assert blob[4] == aes.VERSION_V3
    assert aes.decrypt_any(blob, PW, "lsb") == b"edge case"


def test_is_encrypted():
    assert aes.is_encrypted(aes.encrypt_envelope(b"t", PW)) is True
    assert aes.is_encrypted(b"random bytes") is False


# ── decoy container ───────────────────────────────────────────────────────────

REAL, DECOY = b"the real secret", b"grocery list"


def test_decoy_each_key_opens_only_its_own_slot():
    blob = decoy.encode_dual(DECOY, "decoy-key", REAL, "real-key", "lsb")
    assert decoy.decode_dual(blob, "real-key", "lsb") == REAL
    assert decoy.decode_dual(blob, "decoy-key", "lsb") == DECOY
    with pytest.raises(DecryptionError):
        decoy.decode_dual(blob, "third-key", "lsb")


def test_decoy_container_has_no_structure_to_find():
    blob = decoy.encode_dual(DECOY, "decoy-key", REAL * 20, "real-key", "lsb")
    assert not blob.startswith(aes.MAGIC) and decoy.SEPARATOR not in blob
    half = len(blob) // 2
    assert len(blob) % 2 == 0
    # Equal slots: the sizes reveal nothing about which payload is larger.
    assert len(blob[:half]) == len(blob[half:])
    # Swapping which payload is longer must not change the container length.
    swapped = decoy.encode_dual(REAL * 20, "real-key", DECOY, "decoy-key", "lsb")
    assert len(swapped) == len(blob)


def test_decoy_rejects_identical_keys_and_empty_payloads():
    with pytest.raises(ValueError):
        decoy.encode_dual(DECOY, "same", REAL, "same")
    with pytest.raises(ValueError):
        decoy.encode_dual(b"", "a", REAL, "b")
    with pytest.raises(ValueError):
        decoy.encode_dual(DECOY, "", REAL, "b")


def test_decoy_does_not_misparse_ciphertext_that_contains_the_legacy_separator():
    # A random v3 blob can contain b"DCOY" by chance; it must never be split on it.
    payload = b"A" * 40
    blob = aes.encrypt_obfuscated(payload, PW, "lsb")
    forged = blob[:10] + decoy.SEPARATOR + blob[10:]
    with pytest.raises(DecryptionError):
        decoy.decode_dual(forged, PW, "lsb")
    assert aes.decrypt_any(blob, PW, "lsb") == payload


# ── passphrase hygiene ────────────────────────────────────────────────────────

def test_password_strength():
    assert is_weak_password("abc")
    score, label = password_strength("Correct-Horse-29!x")
    assert score >= 3 and label in ("good", "strong")
    assert password_strength("") == (0, "weak")
