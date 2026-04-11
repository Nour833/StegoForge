"""tests/test_protocol_deadrop.py - Dead-drop protocol helper tests."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from protocol.deadrop import hash_bytes, save_local_output, upload_bytes


def test_hash_bytes_stable():
    a = hash_bytes(b"abc")
    b = hash_bytes(b"abc")
    assert a == b
    assert len(a) == 64


def test_save_local_output(tmp_path):
    out = save_local_output(b"payload", str(tmp_path / "out.bin"), "ignored.bin")
    p = Path(out)
    assert p.exists()
    assert p.read_bytes() == b"payload"


def test_upload_method_validation():
    with pytest.raises(ValueError):
        upload_bytes("https://example.com/upload", b"x", method="DELETE")
