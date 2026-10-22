"""tests/test_cli_output.py — what the command line prints to a person and to a script."""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent))

from stegoforge import app
from stegoforge_ops import ui

KEY = "correct-horse-battery-29!"
# real emoji only: the plain dingbats \u2713 \u2717 \u2192 \u25cf \u25b2 are the UI's own text glyphs
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u26A0\u26A1\u2B50\u2705\u274C\u2757]")


@pytest.fixture
def runner():
    return CliRunner(env={"COLUMNS": "200"})  # keep long temp paths on one line


@pytest.fixture
def files(tmp_path):
    Image.fromarray(np.random.default_rng(1).integers(0, 256, (96, 96, 3), dtype=np.uint8)).save(tmp_path / "c.png")
    (tmp_path / "p.txt").write_bytes(b"cli output test")
    return tmp_path


def _encode(runner, files, *extra):
    return runner.invoke(app, ["encode", "-c", str(files / "c.png"), "-p", str(files / "p.txt"), "-k", KEY, *extra])


def test_encode_and_decode_print_a_compact_aligned_summary(runner, files):
    out = _encode(runner, files).stdout
    assert "Payload embedded" in out and "c_stego.png" in out
    assert "→" in out and "capacity" in out
    assert len(out.strip().splitlines()) <= 8
    assert not EMOJI.search(out)

    dec = runner.invoke(app, ["decode", "-f", str(files / "c_stego.png"), "-k", KEY, "-o", str(files / "out.bin")]).stdout
    assert "Payload extracted" in dec and (files / "out.bin").read_bytes() == b"cli output test"


def test_errors_go_to_stderr_with_a_hint_and_leave_stdout_empty(runner, files):
    _encode(runner, files)
    result = runner.invoke(app, ["decode", "-f", str(files / "c_stego.png"), "-k", "wrong-wrong-wrong-1!", "-o", str(files / "x.bin")])
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "error" in result.stderr and "hint" in result.stderr and "passphrase" in result.stderr.lower()


def test_json_errors_carry_a_stable_code(runner, files):
    _encode(runner, files)
    result = runner.invoke(app, ["decode", "-f", str(files / "c_stego.png"), "-k", "wrong-wrong-wrong-1!", "--json"])
    payload = json.loads(result.stdout)
    assert payload["status"] == "error" and payload["code"] == "decryption-failed"

    plain = runner.invoke(app, ["encode", "-c", str(files / "c.png"), "-p", str(files / "p.txt"), "--json"])
    assert json.loads(plain.stdout)["code"] == "plaintext-refused"


def test_json_stdout_stays_pure_when_a_warning_is_printed(runner, files, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["stegoforge", "encode", "-k", KEY])  # the real argv, as in a shell
    result = _encode(runner, files, "--json")
    assert json.loads(result.stdout)["status"] == "success"
    assert "visible in process list" in result.stderr


def test_exception_text_is_never_read_as_markup(runner, files, tmp_path):
    result = runner.invoke(app, ["decode", "-f", str(tmp_path / "[bold red]missing.png")])
    assert result.exit_code == 1
    assert "[bold red]missing.png" in result.stderr  # printed literally, not swallowed as a style tag


def test_file_names_with_markup_are_printed_literally(runner, files):
    name = files / "[red]odd.png"
    (files / "c.png").rename(name)
    out = runner.invoke(app, ["encode", "-c", str(name), "-p", str(files / "p.txt"), "-k", KEY]).stdout
    assert "[red]odd.png" in out


def _report(results):
    return {"file": "f.png", "detectors_run": len(results), "results": results}


def test_an_unsure_detector_is_never_shown_as_clean():
    results = [
        {"method": "chi2", "detected": False, "confidence": 0.0, "details": {"reliable": False, "interpretation": "cannot tell"}},
        {"method": "rs", "detected": False, "confidence": 0.0, "details": {"interpretation": "nothing"}},
        {"method": "blind", "detected": True, "confidence": 1.0, "details": {}},
        {"method": "ml", "detected": False, "confidence": 0.0, "details": {"skipped": True}},
    ]
    assert [ui.detector_state(r) for r in results] == ["inconclusive", "clean", "detected", "skipped"]
    from io import StringIO

    from rich.console import Console

    buf = StringIO()
    Console(file=buf, width=100, color_system=None).print(ui.detector_table(results))
    rows = {line.split()[0]: line for line in buf.getvalue().splitlines() if line.strip() and not line.startswith(("─", "Detector"))}
    assert "INCONCLUSIVE" in rows["Chi-square"] and "CLEAN" not in rows["Chi-square"]
    assert "DETECTED" in rows["Blind"] and "SKIPPED" in rows["ML"]
    summary = ui.detector_summary(results).plain
    assert "1 detected" in summary and "1 inconclusive" in summary and "1 clean" in summary


def test_detect_output_is_compact_and_emoji_free(runner, files):
    _encode(runner, files)
    out = runner.invoke(app, ["detect", "-f", str(files / "c_stego.png"), "--all"]).stdout
    assert "Detection report" in out and "Detector" in out and "Result" in out
    assert len(out.strip().splitlines()) < 30  # was one bordered panel per detector (~50 lines)
    assert not EMOJI.search(out)
    assert "indicators, not proof" in out


def test_ctf_calls_the_number_a_detector_signal_not_a_confidence_in_the_verdict(runner, files):
    out = runner.invoke(app, ["ctf", "-f", str(files / "c.png")]).stdout
    assert "strongest detector signal" in out and "% confidence" not in out


def test_capacity_output(runner, files):
    out = runner.invoke(app, ["capacity", "-c", str(files / "c.png")]).stdout
    assert "Capacity" in out and "bytes" in out and "Stealth" in out


def test_meter_direction_depends_on_what_high_means():
    low, high = ui.meter(0.1), ui.meter(0.9)
    assert low.plain.count("█") == 1 and high.plain.count("█") == 13
    assert ui.meter(0.9).spans[0].style == ui.BAD  # a high detector signal is bad
    assert ui.meter(0.9, higher_is_better=True).spans[0].style == ui.OK  # a high stealth score is good


def test_error_hints_exist_for_every_user_facing_error_code():
    from core import errors

    for cls in (errors.DecryptionError, errors.PlaintextRefusedError, errors.WeakPassphraseError,
                errors.EmptyPayloadError, errors.CorruptedCarrierError, errors.DepthError):
        assert cls.code in ui.ERROR_HINTS, cls.__name__


def test_schema_command_reads_bundled_data_not_the_docs_folder(runner):
    result = runner.invoke(app, ["schema", "--json", "encode"])
    assert result.exit_code == 0 and json.loads(result.stdout)["type"] == "object"
    assert "encode" in runner.invoke(app, ["schema", "encode"]).stdout.lower()
    bad = runner.invoke(app, ["schema", "nonsense"])
    assert bad.exit_code == 1 and "Unknown schema" in bad.stderr
    assert runner.invoke(app, ["schema", "--json", "nonsense"]).exit_code == 1
