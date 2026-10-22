"""tests/test_cli_protocol.py — dead-drop and key-exchange commands, as a user runs them."""
import json
import stat
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent))

from stegoforge import app

KEY = "correct-horse-battery-29!"


@pytest.fixture
def runner():
    return CliRunner(env={"COLUMNS": "200"})


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # A private temp dir, so leftovers are only ever this test's (other processes also write to /tmp).
    scratch = tmp_path / ".scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    for name, seed in (("a.png", 1), ("b.png", 2)):
        Image.fromarray(np.random.default_rng(seed).integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(tmp_path / name)
    (tmp_path / "p.txt").write_bytes(b"dead drop payload")
    return tmp_path


def _leftovers() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob("stegoforge_deadrop_*")}


def _stego(runner, work) -> bytes:
    result = runner.invoke(app, ["encode", "-c", "a.png", "-p", "p.txt", "-k", KEY, "-o", "drop.png", "--json"])
    assert result.exit_code == 0, result.stderr
    return (work / "drop.png").read_bytes()


def test_check_decodes_into_the_current_directory_and_leaves_no_temp_files(runner, work, monkeypatch):
    blob = _stego(runner, work)
    monkeypatch.setattr("protocol.deadrop.fetch_url_bytes", lambda url, **kw: blob)
    before = _leftovers()
    result = runner.invoke(app, ["deadrop", "check", "--url", "https://drops.example/x.png?v=3", "-k", KEY])
    assert result.exit_code == 0, result.stderr
    assert "Payload extracted" in result.stdout
    produced = sorted(work.glob("*_decoded*"))
    assert len(produced) == 1 and produced[0].read_bytes() == b"dead drop payload"
    assert _leftovers() == before


def test_a_second_check_does_not_overwrite_the_first_result(runner, work, monkeypatch):
    blob = _stego(runner, work)
    monkeypatch.setattr("protocol.deadrop.fetch_url_bytes", lambda url, **kw: blob)
    for _ in range(2):
        assert runner.invoke(app, ["deadrop", "check", "--url", "https://d.example/x.png", "-k", KEY]).exit_code == 0
    assert len(list(work.glob("*_decoded*"))) == 2


def test_check_with_the_wrong_key_is_a_clean_error_and_leaves_nothing_behind(runner, work, monkeypatch):
    blob = _stego(runner, work)
    monkeypatch.setattr("protocol.deadrop.fetch_url_bytes", lambda url, **kw: blob)
    before = _leftovers()
    result = runner.invoke(app, ["deadrop", "check", "--url", "https://d.example/x.png", "-k", "wrong-wrong-wrong-1!"])
    assert result.exit_code == 1 and "error" in result.stderr and "Traceback" not in result.stderr
    assert _leftovers() == before and not list(work.glob("*_decoded*"))


def test_a_hostile_url_extension_is_not_trusted(runner, work, monkeypatch):
    blob = _stego(runner, work)
    monkeypatch.setattr("protocol.deadrop.fetch_url_bytes", lambda url, **kw: blob)
    result = runner.invoke(app, ["deadrop", "check", "--url", "https://d.example/x.p/../../ng", "-k", KEY])
    assert "Traceback" not in (result.stderr or "")


def test_post_reports_errors_instead_of_a_traceback(runner, work):
    result = runner.invoke(app, ["deadrop", "post", "-c", "missing.png", "-p", "p.txt", "-k", KEY])
    assert result.exit_code == 1 and "error" in result.stderr and "Traceback" not in result.stderr


# ── key exchange ──────────────────────────────────────────────────────────────

def _initiate(runner, carrier, out, privfile, passphrase_input="pass-one-1!\npass-one-1!\n"):
    return runner.invoke(app, ["deadrop", "keyx", "initiate", "-c", carrier, "-o", out, "--private-key-file", privfile, "--method", "lsb"],
                         input=passphrase_input)


def test_keyx_both_sides_derive_the_same_session_key_with_prompted_passphrases(runner, work):
    assert _initiate(runner, "a.png", "a_out.png", "a.priv", "pass-a-1!\npass-a-1!\n").exit_code == 0
    assert _initiate(runner, "b.png", "b_out.png", "b.priv", "pass-b-1!\npass-b-1!\n").exit_code == 0
    assert stat.S_IMODE((work / "a.priv").stat().st_mode) == 0o600
    assert (work / "a.priv").read_bytes()[:4] == b"SKX3"

    def complete(received, priv, pw, *extra):
        out = work / f"key_{priv}.txt"
        res = runner.invoke(app, ["deadrop", "keyx", "complete", "-f", received, "--private-key-file", priv,
                                  "--output-key-file", str(out), "--method", "lsb", *extra], input=pw + "\n")
        assert res.exit_code == 0, res.stderr
        return out.read_text()

    key_a = complete("b_out.png", "a.priv", "pass-a-1!")
    key_b = complete("a_out.png", "b.priv", "pass-b-1!")
    assert key_a == key_b and len(key_a) == 64


def test_keyx_does_not_silently_fall_back_to_the_unbound_v1_key(runner, work):
    _initiate(runner, "a.png", "a_out.png", "a.priv", "pass-a-1!\npass-a-1!\n")
    _initiate(runner, "b.png", "b_out.png", "b.priv", "pass-b-1!\npass-b-1!\n")

    def derive(*extra):
        out = work / "k.txt"
        res = runner.invoke(app, ["deadrop", "keyx", "complete", "-f", "b_out.png", "--private-key-file", "a.priv",
                                  "--output-key-file", str(out), "--method", "lsb", *extra], input="pass-a-1!\n")
        assert res.exit_code == 0, res.stderr
        return out.read_text(), res.stderr

    v2, _ = derive()
    v1, warning = derive("--legacy-v1")
    assert v1 != v2
    assert "not bound to both public keys" in warning

    # --legacy-v1 must equal the 1.1.5 derivation of the same shared secret
    from protocol.keyexchange import derive_session_key_hex_1_1_5, derive_shared_secret, load_private_key_file

    priv = load_private_key_file(str(work / "a.priv"), "pass-a-1!")
    from core.image.lsb import LSBEncoder

    peer = LSBEncoder().decode((work / "b_out.png").read_bytes(), depth=1)[:32]
    assert v1 == derive_session_key_hex_1_1_5(derive_shared_secret(priv, peer))


def test_keyx_wrong_local_passphrase_is_a_clean_error(runner, work):
    _initiate(runner, "a.png", "a_out.png", "a.priv", "pass-a-1!\npass-a-1!\n")
    _initiate(runner, "b.png", "b_out.png", "b.priv", "pass-b-1!\npass-b-1!\n")
    res = runner.invoke(app, ["deadrop", "keyx", "complete", "-f", "b_out.png", "--private-key-file", "a.priv", "--method", "lsb"],
                        input="not-the-passphrase\n")
    assert res.exit_code == 1 and "Failed to decrypt local private key file" in res.stderr and "Traceback" not in res.stderr


def test_passing_the_local_passphrase_on_argv_warns(runner, work):
    res = runner.invoke(app, ["deadrop", "keyx", "initiate", "-c", "a.png", "-o", "o.png", "--private-key-file", "p.priv",
                              "--local-passphrase", "pass-argv-1!", "--method", "lsb"])
    assert res.exit_code == 0
    assert "visible in the process list" in res.stderr


def test_json_is_not_involved_in_keyx_output(runner, work):
    # the commands are interactive-first; make sure nothing prints a secret to stdout by default
    _initiate(runner, "a.png", "a_out.png", "a.priv", "pass-a-1!\npass-a-1!\n")
    _initiate(runner, "b.png", "b_out.png", "b.priv", "pass-b-1!\npass-b-1!\n")
    res = runner.invoke(app, ["deadrop", "keyx", "complete", "-f", "b_out.png", "--private-key-file", "a.priv", "--method", "lsb"],
                        input="pass-a-1!\n")
    assert "prefer --output-key-file" in res.stdout  # an explicit warning accompanies printing the key
    assert not json.dumps(res.stdout).count("pass-a-1!")
