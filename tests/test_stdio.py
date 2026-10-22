"""Redirected output on Windows is cp1252, which cannot encode the CLI's "✓": it must not crash."""
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.stdio import make_output_safe

ROOT = Path(__file__).resolve().parent.parent


def _cp1252_stream() -> tuple[io.BytesIO, io.TextIOWrapper]:
    raw = io.BytesIO()
    return raw, io.TextIOWrapper(raw, encoding="cp1252", write_through=True)


def test_the_unfixed_stream_really_fails():
    _, stream = _cp1252_stream()
    with pytest.raises(UnicodeEncodeError):
        stream.write("✓")


def test_elsewhere_the_encoding_is_kept_and_unencodable_characters_become_question_marks(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    raw, stream = _cp1252_stream()
    make_output_safe([stream])
    stream.write("ok ✓ é")
    assert raw.getvalue() == b"ok ? \xe9"


def test_on_windows_the_stream_becomes_utf8(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    raw, stream = _cp1252_stream()
    make_output_safe([stream])
    stream.write("✓")
    assert raw.getvalue() == "✓".encode()


def test_a_missing_or_closed_stream_is_ignored():
    make_output_safe([None, object()])
    _, stream = _cp1252_stream()
    stream.close()
    make_output_safe([stream])


@pytest.mark.parametrize("args", [["doctor"], ["capacity", "-c", "tests/fixtures/sample.png"], ["--help"]])
def test_the_real_cli_survives_a_cp1252_console(args):
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0", "STEGOFORGE_FAST_UI": "1"}
    done = subprocess.run([sys.executable, str(ROOT / "stegoforge.py"), *args], cwd=ROOT, env=env,
                          capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr.decode("cp1252", "replace")[-600:]
    assert b"Traceback" not in done.stderr and b"UnicodeEncodeError" not in done.stderr
