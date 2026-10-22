"""tests/test_protocol_keyexchange.py - Tests for key exchange primitives."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from protocol.keyexchange import (
    generate_ephemeral_keypair,
    encrypt_private_key,
    decrypt_private_key,
    derive_shared_secret,
    derive_session_key_hex,
)


def test_keyx_shared_secret_match():
    a_priv, a_pub = generate_ephemeral_keypair()
    b_priv, b_pub = generate_ephemeral_keypair()

    s1 = derive_shared_secret(a_priv, b_pub)
    s2 = derive_shared_secret(b_priv, a_pub)
    assert s1 == s2


def test_private_key_encrypt_decrypt():
    priv, _ = generate_ephemeral_keypair()
    blob = encrypt_private_key(priv, "local-pass")
    out = decrypt_private_key(blob, "local-pass")
    assert out == priv


def test_session_key_hex_length():
    priv, pub = generate_ephemeral_keypair()
    sec = derive_shared_secret(priv, pub)
    k = derive_session_key_hex(sec)
    assert isinstance(k, str)
    assert len(k) == 64


def test_new_private_key_files_use_the_v3_format_and_reject_tampering():
    import pytest

    priv, _ = generate_ephemeral_keypair()
    blob = encrypt_private_key(priv, "local-pass")
    assert blob.startswith(b"SKX3")
    with pytest.raises(ValueError, match="Failed to decrypt"):
        decrypt_private_key(blob, "wrong-pass")
    flipped = bytearray(blob)
    flipped[-1] ^= 1
    with pytest.raises(ValueError, match="Failed to decrypt"):
        decrypt_private_key(bytes(flipped), "local-pass")
    # a v3 file cannot be passed off as a legacy one by swapping the magic
    with pytest.raises(ValueError, match="Failed to decrypt"):
        decrypt_private_key(b"SKX1" + blob[4:], "local-pass")


def test_private_key_files_written_by_1_1_5_still_open():
    """1.1.5 wrote b"SKX1" + salt + nonce + AES-GCM(key=Argon2id t=2, no AAD)."""
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from core.crypto.kdf import derive_key

    priv, _ = generate_ephemeral_keypair()
    salt, nonce = os.urandom(16), os.urandom(12)
    key = derive_key("local-pass", salt, profile="legacy")  # exactly what 1.1.5's derive_key(passphrase, salt) computed
    legacy = b"SKX1" + salt + nonce + AESGCM(key).encrypt(nonce, priv, None)
    assert decrypt_private_key(legacy, "local-pass") == priv


def test_garbage_private_key_files_are_a_clean_error():
    import pytest

    for blob in (b"", b"SKX3", b"SKX3" + b"\x00" * 20, b"nonsense" * 10):
        with pytest.raises(ValueError):
            decrypt_private_key(blob, "x")


def test_session_key_matches_what_the_published_1_1_5_release_derives():
    """The vector was produced by running 1.1.5's own derive_session_key_hex."""
    import json

    from protocol.keyexchange import derive_session_key_hex_1_1_5

    vec = json.loads((Path(__file__).parent / "fixtures" / "legacy_v1_vectors.json").read_text())["keyx_session_v1"]
    assert derive_session_key_hex_1_1_5(bytes.fromhex(vec["shared_secret_hex"])) == vec["session_key_hex"]


def test_public_from_private_matches_generation():
    from protocol.keyexchange import public_from_private

    priv, pub = generate_ephemeral_keypair()
    assert public_from_private(priv) == pub
