"""Regression tests for key handling, payload typing, and diff compatibility."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.document.unicode_ws import UnicodeWSEncoder
from stegoforge import _guess_payload_ext, op_decode, op_diff, op_encode
from web.app import _detect_payload_type


def _carrier_text() -> str:
    # Dense spacing ensures enough Unicode insertion points for encrypted payloads.
    return ("lorem ipsum dolor sit amet " * 500).strip() + "\n"


def test_encode_uses_env_key_fallback(monkeypatch, tmp_path):
    carrier_path = tmp_path / "carrier.txt"
    payload_path = tmp_path / "payload.bin"

    carrier_path.write_text(_carrier_text(), encoding="utf-8")
    payload_path.write_bytes(b"HELLO-ENV-FALLBACK")

    monkeypatch.setenv("STEGOFORGE_KEY", "env-secret")

    result = op_encode(
        str(carrier_path),
        str(payload_path),
        None,
        None,
        "unicode",
        1,
        None,
        None,
        False,
        None,
        False,
        False,
        None,
        None,
        None,
        False,
    )

    stego_bytes = Path(result["output"]).read_bytes()
    raw = UnicodeWSEncoder().decode(stego_bytes)

    assert raw.startswith(b"SFRG")
    assert raw != payload_path.read_bytes()


def test_decode_without_key_returns_plain_payload(monkeypatch, tmp_path):
    carrier_path = tmp_path / "carrier.txt"
    stego_path = tmp_path / "carrier_stego.txt"
    payload = b"plain-payload-no-key"

    carrier_path.write_text(_carrier_text(), encoding="utf-8")
    monkeypatch.delenv("STEGOFORGE_KEY", raising=False)

    carrier_bytes = carrier_path.read_bytes()
    stego_bytes = UnicodeWSEncoder().encode(carrier_bytes, payload)
    stego_path.write_bytes(stego_bytes)

    result = op_decode(str(stego_path), None, None, "unicode", False, False)
    decoded = Path(result["output"]).read_bytes()

    assert decoded == payload


def test_diff_binary_returns_changed_alias_keys(tmp_path):
    cover = tmp_path / "cover.bin"
    stego = tmp_path / "stego.bin"

    cover.write_bytes(b"\x00\x01\x02\x03\x04\x05")
    stego.write_bytes(b"\x00\x01\xFF\x03\x05\x05")

    result = op_diff(str(cover), str(stego))

    assert result["type"] == "binary"
    assert result["changed_bytes"] == result["differing_bytes"]
    assert result["changed_percent"] == result["differing_percent"]


def test_unknown_payload_defaults_to_bin_extension():
    unknown = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A" * 5
    assert _guess_payload_ext(unknown) == ".bin"



def test_web_payload_type_unknown_defaults_to_bin():
    unknown = b"\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A" * 5
    mime, ext = _detect_payload_type(unknown)
    assert mime == "application/octet-stream"
    assert ext == ".bin"
