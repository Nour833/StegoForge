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
