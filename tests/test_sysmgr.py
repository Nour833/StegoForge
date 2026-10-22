"""tests/test_sysmgr.py — StegoForge must never fetch or execute a downloaded binary."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core import sysmgr


def test_sysmgr_contains_no_download_or_exec_machinery():
    source = Path(sysmgr.__file__).read_text()
    for forbidden in ("urllib", "urlretrieve", "urlopen", "subprocess", "chmod", "tarfile", "zipfile", "xattr"):
        assert forbidden not in source, f"sysmgr must not use {forbidden}"
    for gone in ("_install_ffmpeg_linux", "_install_ffmpeg_windows", "_install_ffmpeg_macos", "_download_with_progress"):
        assert not hasattr(sysmgr, gone)


def test_bootstrap_is_silent_and_touches_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sysmgr, "STEGOFORGE_DIR", tmp_path / "home")
    monkeypatch.setattr(sysmgr, "MODELS_DIR", tmp_path / "home" / "models")
    sysmgr.bootstrap_if_needed()
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""
    assert not (tmp_path / "home").exists()


def test_install_bundled_model_copies_and_honours_a_pin(tmp_path, monkeypatch):
    import detect.ml_steganalysis as ml

    fake = tmp_path / "bundled.onnx"
    fake.write_bytes(b"onnx-bytes")
    monkeypatch.setattr(ml, "bundled_model_paths", lambda: [fake])
    monkeypatch.setattr(sysmgr, "MODELS_DIR", tmp_path / "models")

    ok, message = sysmgr.install_bundled_model()
    assert ok and (tmp_path / "models" / ml.MODEL_NAME).read_bytes() == b"onnx-bytes"

    monkeypatch.setenv("STEGOFORGE_MODEL_SHA256", "0" * 64)
    (tmp_path / "models" / ml.MODEL_NAME).unlink()
    ok, message = sysmgr.install_bundled_model()
    assert not ok and "SHA256" in message
    assert not (tmp_path / "models" / ml.MODEL_NAME).exists()


def test_missing_model_is_a_message_not_an_error(tmp_path, monkeypatch):
    import detect.ml_steganalysis as ml

    monkeypatch.setattr(ml, "bundled_model_paths", lambda: [tmp_path / "absent.onnx"])
    ok, message = sysmgr.install_bundled_model()
    assert not ok and "does not include" in message


def test_verify_asset_hash(tmp_path, monkeypatch):
    f = tmp_path / "a.bin"
    f.write_bytes(b"abc")
    monkeypatch.delenv("STEGOFORGE_MODEL_SHA256", raising=False)
    assert sysmgr.verify_asset_hash(f, "model")  # no pin: nothing to enforce
    monkeypatch.setenv("STEGOFORGE_MODEL_SHA256", sysmgr.sha256_file(f).upper())
    assert sysmgr.verify_asset_hash(f, "model")
    monkeypatch.setenv("STEGOFORGE_MODEL_SHA256", "1" * 64)
    assert not sysmgr.verify_asset_hash(f, "model")


def test_diagnose_reports_the_core_components():
    checks = {c.name: c for c in sysmgr.diagnose()}
    for name in ("Python", "numpy", "Pillow", "cryptography", "ffmpeg", "ML model", "Temp dir writable"):
        assert name in checks
    assert checks["Python"].ok and checks["numpy"].ok
    assert checks["ffmpeg"].required is False  # only MP3/FLAC/OGG conversion needs it


# ── CLI surface ───────────────────────────────────────────────────────────────

@pytest.fixture
def runner():
    from typer.testing import CliRunner

    return CliRunner()


def test_cli_commands_do_not_bootstrap_or_complain(runner):
    from stegoforge import app

    result = runner.invoke(app, ["doctor", "--json"])
    assert "Failed to install" not in result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True and any(c["name"] == "ffmpeg" for c in payload["checks"])


def test_doctor_exit_code_reflects_missing_required_components(runner, monkeypatch):
    from stegoforge import app

    broken = [sysmgr.Check("numpy", False, "not installed", required=True), sysmgr.Check("av", False, "x", required=False)]
    monkeypatch.setattr(sysmgr, "diagnose", lambda: broken)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1 and "required component" in result.output


def test_offline_flag_blocks_network_access(runner, monkeypatch):
    from core.http import UnsafeURLError, fetch

    monkeypatch.setenv("STEGOFORGE_OFFLINE", "1")
    with pytest.raises(UnsafeURLError, match="offline"):
        fetch("http://example.com/")
    from stegoforge import _urlopen_with_ca_fallback
    import urllib.request

    with pytest.raises(ValueError, match="offline"):
        _urlopen_with_ca_fallback(urllib.request.Request("http://example.com/"), timeout=1)


def test_doctor_still_sees_packages_when_metadata_is_unavailable(monkeypatch):
    """A PyInstaller build ships modules but no dist-info; doctor must not call everything missing."""
    import importlib.metadata

    def no_metadata(_name):
        raise importlib.metadata.PackageNotFoundError(_name)

    monkeypatch.setattr(importlib.metadata, "version", no_metadata)
    checks = {c.name: c for c in sysmgr.diagnose()}
    for name in ("numpy", "Pillow", "argon2-cffi", "cryptography", "typer", "rich"):
        assert checks[name].ok, f"{name}: {checks[name].detail}"
    assert sysmgr._version("definitely-not-a-package-xyz") is None
