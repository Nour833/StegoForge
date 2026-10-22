"""tests/test_upgrades_14.py — coverage for v1.4 upgrade tracks."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.crypto import aes
from core.crypto.kdf import is_weak_password, password_strength


def test_aes_v3_bind_and_legacy():
    c = aes.encrypt_envelope(b"top", "strong-pass-1!", "lsb")
    assert aes.decrypt_envelope(c, "strong-pass-1!", "lsb") == b"top"
    try:
        aes.decrypt_envelope(c, "strong-pass-1!", "dct")
        raise AssertionError("AAD bind should reject wrong method")
    except ValueError:
        pass
    legacy = aes.encrypt(b"old", "strong-pass-1!")
    assert aes.decrypt(legacy, "strong-pass-1!") == b"old"


def test_pad_roundtrip():
    p = aes.iso_pad(b"AB", 8)
    assert len(p) == 8
    assert aes.iso_unpad(p) == b"AB"


def test_password_strength():
    assert is_weak_password("abc")
    score, label = password_strength("Correct-Horse-29!x")
    assert score >= 3 and label in ("good", "strong")


def test_keyx_v2_and_sign():
    from protocol.keyexchange import (
        derive_session_key_hex_v2,
        derive_shared_secret,
        generate_ephemeral_keypair,
        generate_signing_keypair,
        sign_exchange,
        verify_exchange,
    )

    priv, pub = generate_ephemeral_keypair()
    priv2, pub2 = generate_ephemeral_keypair()
    ss = derive_shared_secret(priv, pub2)
    k1 = derive_session_key_hex_v2(ss, pub, pub2)
    k2 = derive_session_key_hex_v2(ss, pub2, pub)
    assert k1 == k2
    spriv, spub = generate_signing_keypair()
    sig = sign_exchange(spriv, pub)
    verify_exchange(spub, sig, pub)


def test_fail_closed_and_enforce(tmp_path):
    from PIL import Image
    import io
    from stegoforge import op_encode

    img = Image.new("RGB", (64, 64), (1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    c = tmp_path / "c.png"
    c.write_bytes(buf.getvalue())
    p = tmp_path / "p.bin"
    p.write_bytes(b"data")
    try:
        op_encode(str(c), str(p), None, None, "lsb", 1, None, None,
                  False, None, False, False, None, None, None, False)
        raise AssertionError("should refuse plaintext")
    except ValueError:
        pass
    try:
        op_encode(str(c), str(p), "abc", None, "lsb", 1, None, None,
                  False, None, False, False, None, None, None, False,
                  enforce_strong=True)
        raise AssertionError("should refuse weak pass")
    except ValueError:
        pass


def test_case_id_and_report_version(tmp_path):
    from PIL import Image
    import io
    from stegoforge import op_detect, op_ctf

    img = Image.new("RGB", (32, 32), (4, 5, 6))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    f = tmp_path / "x.png"
    f.write_bytes(buf.getvalue())
    r = op_detect(str(f), False, False, True, True, False, False, False, False, False, case_id="C1")
    assert r["case_id"] == "C1" and r["report_version"] == 1 and r["file_sha256"]
    c = op_ctf(str(f), False, save_payloads=False, case_id="C2")
    assert c["case_id"] == "C2" and c["report_version"] == 1


def test_web_artifact_id_only():
    from web.app import create_app

    app = create_app()
    client = app.test_client()
    r = client.get("/artifact")
    assert r.status_code == 400
    assert b"artifact id" in r.data
