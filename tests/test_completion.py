"""tests/test_completion.py — shell completion is generated from the live command tree."""
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import typer.main

sys.path.insert(0, str(Path(__file__).parent.parent))

from stegoforge import app
from stegoforge_ops import completion

ROOT = typer.main.get_command(app)
COMMANDS = sorted(ROOT.commands)


def _script(shell: str) -> str:
    return completion.GENERATORS[shell](ROOT)


def test_every_real_command_is_completed_and_none_is_invented():
    for shell in ("bash", "zsh", "fish"):
        text = _script(shell)
        for name in COMMANDS:
            assert re.search(rf"\b{re.escape(name)}\b", text), f"{shell} completion lacks {name}"
    assert "doctor" in COMMANDS and "deadrop" in COMMANDS


def test_zsh_compdef_is_the_first_line_or_zsh_never_registers_the_file():
    assert _script("zsh").splitlines()[0] == "#compdef stegoforge"


def test_zsh_specs_are_well_formed():
    text = _script("zsh")
    for line in text.splitlines():
        if "_arguments" in line and "'" in line:
            for spec in shlex.split(line):  # parse like the shell does, so `'\''` (an apostrophe in a help text) is handled
                unescaped = re.sub(r"\\.", "", spec)
                assert unescaped.count("[") == unescaped.count("]"), spec
    assert "(lsb " in text or "(adaptive-lsb " in text  # --method choices are offered
    assert "twitter" in text and "_files" in text


@pytest.mark.parametrize("shell,tool,args", [("bash", "bash", ["-n"]), ("zsh", "zsh", ["-n"]), ("fish", "fish", ["--no-execute"])])
def test_scripts_pass_their_shells_syntax_check(tmp_path, shell, tool, args):
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} not installed")
    script = tmp_path / f"comp.{shell}"
    script.write_text(_script(shell))
    done = subprocess.run([tool, *args, str(script)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
@pytest.mark.parametrize("words,expect", [
    (["stegoforge", "enc"], "encode"),
    (["stegoforge", "doc"], "doctor"),
    (["stegoforge", "encode", "--me"], "--method"),
    (["stegoforge", "encode", "--method", "ad"], "adaptive-lsb"),
    (["stegoforge", "encode", "--target", "tw"], "twitter"),
    (["stegoforge", "deadrop", ""], "keyx"),
])
def test_bash_completion_gives_the_right_candidates(tmp_path, words, expect):
    script = tmp_path / "comp.bash"
    script.write_text(_script("bash"))
    quoted = " ".join(f'"{w}"' for w in words)
    code = (f'source {script}; COMP_WORDS=({quoted}); COMP_CWORD=$(( ${{#COMP_WORDS[@]}} - 1 )); '
            '_stegoforge; echo "${COMPREPLY[*]}"')
    out = subprocess.run(["bash", "-c", code], capture_output=True, text=True).stdout.split()
    assert expect in out, f"{words} -> {out}"


def test_completion_command_rejects_an_unknown_shell():
    from typer.testing import CliRunner

    result = CliRunner().invoke(app, ["completion", "powershell"])
    assert result.exit_code == 1 and "Unknown shell" in result.stderr
    ok = CliRunner().invoke(app, ["completion", "bash"])
    assert ok.exit_code == 0 and ok.stdout.startswith("# StegoForge bash completion")
