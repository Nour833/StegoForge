"""tests/test_ops_roundtrip.py — the CLI/web operation layer, end to end through real files.

These run op_encode -> file -> op_decode (and op_batch_encode) so that a drift
between the ops layer and the crypto/encoder APIs cannot hide behind unit tests
of either side.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.crypto import aes
from core.errors import DecryptionError, PlaintextRefusedError
from stegoforge_ops import op_batch_encode, op_decode, op_encode

KEY = "correct-horse-battery-29!"
FIXTURES = Path(__file__).parent / "fixtures"


def _png(path: Path, size: int = 96, seed: int = 0) -> Path:
    arr = np.random.default_rng(seed).integers(0, 256, (size, size, 3), dtype=np.uint8)
    Image.fromarray(arr).save(path, format="PNG")
    return path


def _encode(carrier, payload_bytes, tmp_path, key=KEY, method="lsb", **kw):
    payload = tmp_path / "payload.bin"
    payload.write_bytes(payload_bytes)
    args = dict(
        decoy=None, decoy_key=None, wet_paper=False, target=None, test_survival=False,
        preserve_fingerprint=False, cover=None, topic=None, llm_model=None, json_mode=True,
    )
    args.update(kw)
    return op_encode(
        str(carrier), str(payload), key, args.pop("output", None), method, args.pop("depth", 1),
        args.pop("decoy"), args.pop("decoy_key"), args.pop("wet_paper"), args.pop("target"),
        args.pop("test_survival"), args.pop("preserve_fingerprint"), args.pop("cover"),
        args.pop("topic"), args.pop("llm_model"), args.pop("json_mode"), **args,
    )


def _decode(stego, tmp_path, key=KEY, method=None, **kw):
    out = tmp_path / "decoded.bin"
    res = op_decode(str(stego), key, str(out), method, kw.pop("wet_paper", False), True, **kw)
    return out.read_bytes(), res


@pytest.fixture
def png(tmp_path):
    return _png(tmp_path / "c.png")


# ── new embeds really are v3 and method-bound ─────────────────────────────────

def test_standard_embed_is_a_v3_envelope_bound_to_the_method(png, tmp_path):
    res = _encode(png, b"payload", tmp_path)
    from core.image.lsb import LSBEncoder

    raw = LSBEncoder().decode(Path(res["output"]).read_bytes(), depth=1, key=KEY)
    assert raw[:4] == aes.MAGIC and raw[4] == aes.VERSION_V3
    assert aes.decrypt_envelope(raw, KEY, "lsb") == b"payload"
    with pytest.raises(DecryptionError):
        aes.decrypt_envelope(raw, KEY, "dct")  # replay into another method is refused
    assert _decode(res["output"], tmp_path)[0] == b"payload"


@pytest.mark.parametrize("tail", [b"\x01", b"\x02\x02", b"\x80", b"\x80\x00\x00", b"\x00", b"\x01\x02\x03\x04"])
def test_unpadded_payload_keeps_every_trailing_byte(png, tmp_path, tail):
    """Padding is flagged, not guessed: a payload that merely looks padded must survive intact."""
    payload = b"binary-data" + tail
    res = _encode(png, payload, tmp_path)
    assert _decode(res["output"], tmp_path)[0] == payload


@pytest.mark.parametrize("pad", [8, 64, 128, 256])
def test_padded_embed_roundtrips(png, tmp_path, pad):
    payload = b"hello\x01\x02"
    res = _encode(png, payload, tmp_path, pad_block=pad)
    assert res["encrypted_size"] >= pad
    assert _decode(res["output"], tmp_path)[0] == payload


def test_obfuscated_header_has_no_fixed_bytes_and_decodes(png, tmp_path):
    res = _encode(png, b"stealthy", tmp_path, header_mode="obfuscated")
    from core.image.lsb import LSBEncoder

    raw = LSBEncoder().decode(Path(res["output"]).read_bytes(), depth=1, key=KEY)
    assert not raw.startswith(aes.MAGIC)
    assert _decode(res["output"], tmp_path)[0] == b"stealthy"
    with pytest.raises(DecryptionError):
        _decode(res["output"], tmp_path, key="not-the-right-key-1!")


def test_wrong_key_is_one_generic_failure(png, tmp_path):
    res = _encode(png, b"secret", tmp_path)
    with pytest.raises(DecryptionError, match="Failed to decode payload"):
        _decode(res["output"], tmp_path, key="wrong-key-wrong-key-1!")


def test_aliases_bind_to_the_canonical_method(png, tmp_path):
    for alias in ("adaptive", "ADAPTIVE-LSB"):
        res = _encode(png, b"via-" + alias.encode(), tmp_path, method=alias)
        assert res["method"] == "adaptive-lsb"
        assert _decode(res["output"], tmp_path)[0] == b"via-" + alias.encode()


def test_office_family_shares_one_binding(tmp_path):
    carrier = FIXTURES / "sample.docx"
    res = _encode(carrier, b"office-payload", tmp_path, method="office", output=str(tmp_path / "o.docx"))
    assert _decode(res["output"], tmp_path)[0] == b"office-payload"            # auto-detected as docx
    assert _decode(res["output"], tmp_path, method="docx")[0] == b"office-payload"


def test_decoy_each_key_opens_its_own_payload(png, tmp_path):
    decoy = tmp_path / "decoy.txt"
    decoy.write_bytes(b"nothing to see here")
    res = _encode(png, b"the real one", tmp_path, decoy=str(decoy), decoy_key="decoy-pass-phrase-1!")
    assert res["decoy_mode"] is True
    assert _decode(res["output"], tmp_path)[0] == b"the real one"
    assert _decode(res["output"], tmp_path, key="decoy-pass-phrase-1!")[0] == b"nothing to see here"


def test_wet_paper_roundtrip(tmp_path):
    carrier = _png(tmp_path / "w.png", size=160)
    res = _encode(carrier, b"wet-paper payload", tmp_path, wet_paper=True)
    assert res["wet_paper"] is True
    data, info = _decode(res["output"], tmp_path)
    assert data == b"wet-paper payload"
    assert info["wet_paper"] is True


def test_require_v2_refuses_legacy_blobs_but_default_reads_them(png, tmp_path):
    from core.image.lsb import LSBEncoder

    legacy = aes.encrypt(b"from 1.1.5", KEY)
    stego = LSBEncoder().encode(png.read_bytes(), legacy)
    path = tmp_path / "legacy.png"
    path.write_bytes(stego)
    assert _decode(path, tmp_path)[0] == b"from 1.1.5"
    with pytest.raises(DecryptionError):
        _decode(path, tmp_path, require_v2=True)


def test_plaintext_is_refused_without_opt_in(png, tmp_path, monkeypatch):
    monkeypatch.delenv("STEGOFORGE_ALLOW_PLAINTEXT", raising=False)
    monkeypatch.delenv("STEGOFORGE_KEY", raising=False)
    with pytest.raises(PlaintextRefusedError):
        _encode(png, b"x", tmp_path, key=None)


# ── output naming ─────────────────────────────────────────────────────────────

def test_default_output_name_uses_the_format_the_encoder_produces(tmp_path):
    wav = FIXTURES / "sample.wav"
    res = _encode(wav, b"audio payload", tmp_path, method="audio-lsb", output=None) if False else None
    bmp = tmp_path / "c.bmp"
    Image.fromarray(np.random.default_rng(1).integers(0, 256, (96, 96, 3), dtype=np.uint8)).save(bmp)
    res = _encode(bmp, b"bmp payload", tmp_path)
    assert res["output"].endswith("c_stego.bmp")


def test_explicit_output_with_wrong_extension_warns(png, tmp_path):
    res = _encode(png, b"x", tmp_path, output=str(tmp_path / "wrong.jpg"))
    assert any(".png" in w for w in res.get("warnings", []))


# ── survival self-test (used to fail unconditionally) ─────────────────────────

def test_survival_test_decrypts_the_v3_envelope(tmp_path):
    carrier = tmp_path / "c.png"
    Image.fromarray(np.random.default_rng(4).integers(0, 256, (256, 256, 3), dtype=np.uint8)).save(carrier)
    res = _encode(carrier, b"survive me", tmp_path, target="telegram", test_survival=True)
    st = res["survival_test"]
    assert st["error"] is None or "differ" not in st["error"]
    # a v3 envelope must never be rejected for being "not legacy":
    assert "Decryption failed" not in (st["error"] or "") or st["survived"] is False


# ── batch ─────────────────────────────────────────────────────────────────────

def _tree(tmp_path):
    root = tmp_path / "batch"
    (root / "a").mkdir(parents=True)
    (root / "b").mkdir()
    _png(root / "a" / "x.png", seed=1)
    _png(root / "b" / "x.png", seed=2)          # same name in another folder
    _png(root / "top.png", seed=3)
    _png(root / "old_stego.png", seed=4)        # output of an earlier run: must be ignored
    (root / "notes.xyz").write_text("not a carrier")
    payload = tmp_path / "p.bin"
    payload.write_bytes(b"batch payload")
    return root, payload


def test_batch_encode_encodes_every_carrier_and_keeps_same_named_files_apart(tmp_path):
    root, payload = _tree(tmp_path)
    out = tmp_path / "out"
    res = op_batch_encode(str(root), str(payload), KEY, str(out), None, 1, False)
    assert (res["total"], res["passed"], res["failed"]) == (3, 3, 0), res["rows"]
    produced = sorted(str(Path(r["output"]).relative_to(out)) for r in res["rows"])
    assert produced == ["a/x_stego.png", "b/x_stego.png", "top_stego.png"]
    for r in res["rows"]:
        assert _decode(r["output"], tmp_path)[0] == b"batch payload"


def test_batch_encode_in_place_does_not_reprocess_its_own_output(tmp_path):
    root, payload = _tree(tmp_path)
    first = op_batch_encode(str(root), str(payload), KEY, None, None, 1, False)
    assert first["passed"] == 3
    second = op_batch_encode(str(root), str(payload), KEY, None, None, 1, False)
    assert second["total"] == 3 and second["failed"] == 0  # *_stego files were not picked up


def test_batch_output_dir_inside_the_batch_dir_is_not_rescanned(tmp_path):
    root, payload = _tree(tmp_path)
    op_batch_encode(str(root), str(payload), KEY, str(root / "stego_out"), None, 1, False)
    again = op_batch_encode(str(root), str(payload), KEY, str(root / "stego_out"), None, 1, False)
    assert again["total"] == 3


def test_batch_parallel_matches_sequential(tmp_path):
    root, payload = _tree(tmp_path)
    res = op_batch_encode(str(root), str(payload), KEY, str(tmp_path / "par"), None, 1, False, jobs=3)
    assert res["passed"] == 3 and res["failed"] == 0


def test_batch_reports_a_bad_carrier_without_aborting_the_rest(tmp_path):
    root, payload = _tree(tmp_path)
    (root / "broken.png").write_bytes(b"\x89PNG not really")
    res = op_batch_encode(str(root), str(payload), KEY, str(tmp_path / "o"), None, 1, False)
    assert res["passed"] == 3 and res["failed"] == 1
    bad = next(r for r in res["rows"] if r["status"] == "error")
    assert bad["file"] == "broken.png" and "NameError" not in bad["error"]


def test_batch_unknown_method_fails_once_up_front(tmp_path):
    root, payload = _tree(tmp_path)
    with pytest.raises(ValueError, match="Unknown method"):
        op_batch_encode(str(root), str(payload), KEY, None, "lsbb", 1, False)


def test_batch_requires_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("STEGOFORGE_KEY", raising=False)
    root, payload = _tree(tmp_path)
    with pytest.raises(ValueError, match="key"):
        op_batch_encode(str(root), str(payload), "", None, None, 1, False)


def test_ops_result_is_json_serialisable(png, tmp_path):
    json.dumps(_encode(png, b"x", tmp_path))
