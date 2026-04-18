"""Regression tests for runtime versioning and updater file replacement."""
import errno
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import stegoforge
from core.version import __version__


def test_current_version_prefers_core_version(monkeypatch):
    monkeypatch.delenv("STEGOFORGE_VERSION", raising=False)
    assert stegoforge._current_version() == __version__


def test_current_version_honors_env_override(monkeypatch):
    monkeypatch.setenv("STEGOFORGE_VERSION", "9.9.9")
    assert stegoforge._current_version() == "9.9.9"


def test_safe_replace_handles_cross_device(monkeypatch, tmp_path):
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"new-data")
    dst.write_bytes(b"old-data")

    real_replace = os.replace
    calls = {"count": 0}

    def fake_replace(a, b):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real_replace(a, b)

    monkeypatch.setattr(stegoforge.os, "replace", fake_replace)

    stegoforge._safe_replace(src, dst)

    assert dst.read_bytes() == b"new-data"
    assert not (tmp_path / f".{dst.name}.new").exists()


def test_safe_replace_reraises_non_exdev(monkeypatch, tmp_path):
    src = tmp_path / "src.bin"
    dst = tmp_path / "dst.bin"
    src.write_bytes(b"new-data")
    dst.write_bytes(b"old-data")

    def fake_replace(a, b):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(stegoforge.os, "replace", fake_replace)

    with pytest.raises(OSError):
        stegoforge._safe_replace(src, dst)
