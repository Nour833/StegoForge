"""tests/test_packaging_deb.py — the Debian package must contain a working program.

The previous inline recipe forgot ``stegoforge_ops``; the installed CLI could not
be imported. These tests stage the package and run it from the staged copy.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build_deb  # noqa: E402


@pytest.fixture(scope="module")
def staged(tmp_path_factory) -> Path:
    return build_deb.stage(tmp_path_factory.mktemp("deb") / "pkg")


def _run(staged: Path, *args: str, cwd: Path) -> subprocess.CompletedProcess:
    # -E: ignore PYTHONPATH; cwd is outside the repo, so nothing can resolve from the source tree.
    return subprocess.run(
        [sys.executable, "-E", str(staged / build_deb.INSTALL_DIR / "stegoforge.py"), *args],
        capture_output=True, text=True, cwd=cwd, timeout=120,
    )


def test_every_project_package_is_shipped(staged):
    find_packages = pytest.importorskip("setuptools").find_packages

    install = staged / build_deb.INSTALL_DIR
    for package in find_packages(str(ROOT), exclude=["tests*"]):
        assert (install / package.replace(".", "/") / "__init__.py").is_file(), package
    assert (install / "stegoforge_ops" / "encode_ops.py").is_file()
    assert (install / "web" / "templates" / "index.html").is_file()
    assert (install / "web" / "static" / "app.js").is_file()
    assert (install / "models" / "model_quantized.onnx").is_file()
    assert (install / "assets.sha256").is_file()


def test_no_bytecode_or_caches_are_shipped(staged):
    junk = [p for p in staged.rglob("*") if p.name == "__pycache__" or p.suffix in (".pyc", ".pyo") or p.name == ".cache"]
    assert junk == []


def test_staged_program_runs_from_outside_the_source_tree(staged, tmp_path):
    result = _run(staged, "doctor", "--json", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"] is True


def test_staged_program_prints_its_schemas(staged, tmp_path):
    """`schema` used to read docs/ next to the script, which a pip install does not have."""
    result = _run(staged, "schema", "--json", "capacity", cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["type"] == "object"
    human = _run(staged, "schema", "encode", cwd=tmp_path)
    assert human.returncode == 0 and "encode" in human.stdout.lower()


def test_staged_program_encodes_and_decodes(staged, tmp_path):
    import numpy as np
    from PIL import Image

    Image.fromarray(np.random.default_rng(0).integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(tmp_path / "c.png")
    (tmp_path / "p.txt").write_bytes(b"from the staged package")
    enc = _run(staged, "encode", "-c", "c.png", "-p", "p.txt", "-k", "correct-horse-battery-29!", "--json", cwd=tmp_path)
    assert enc.returncode == 0, enc.stderr
    dec = _run(staged, "decode", "-f", "c_stego.png", "-k", "correct-horse-battery-29!", "-o", "out.bin", "--json", cwd=tmp_path)
    assert dec.returncode == 0, dec.stderr
    assert (tmp_path / "out.bin").read_bytes() == b"from the staged package"


def test_every_module_resolves_from_the_staged_tree(staged, tmp_path):
    """Proves isolation: a module missing from the package would silently load from the source tree
    (the dev environment has an editable install), so check where each one really came from."""
    find_packages = pytest.importorskip("setuptools").find_packages

    names = ["stegoforge", *find_packages(str(ROOT), exclude=["tests*"])]
    code = (
        "import importlib, json, sys\n"
        "staged = sys.argv[1]\n"
        "sys.path.insert(0, staged)\n"
        "bad = []\n"
        "for name in sys.argv[2:]:\n"
        "    mod = importlib.import_module(name)\n"
        "    if not str(mod.__file__).startswith(staged):\n"
        "        bad.append([name, str(mod.__file__)])\n"
        "print(json.dumps(bad))\n"
    )
    root = str(staged / build_deb.INSTALL_DIR)
    result = subprocess.run([sys.executable, "-E", "-c", code, root, *names], capture_output=True, text=True,
                            cwd=tmp_path, timeout=120)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


def test_staged_web_app_serves_the_index(staged, tmp_path):
    root = str(staged / build_deb.INSTALL_DIR)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1])\n"
        "from web.app import create_app\n"
        "r = create_app().test_client().get('/')\n"
        "print(r.status_code, b'StegoForge' in r.data)\n"
    )
    result = subprocess.run([sys.executable, "-E", "-c", code, root], capture_output=True, text=True, cwd=tmp_path, timeout=120)
    assert result.stdout.split() == ["200", "True"], result.stderr


def test_control_file_is_consistent(staged):
    fields = dict(line.split(": ", 1) for line in (staged / "DEBIAN" / "control").read_text().splitlines()
                  if line and not line.startswith(" ") and ": " in line)
    assert fields["Package"] == "stegoforge" and fields["Architecture"] == "all"
    assert fields["Version"] == build_deb.deb_version(build_deb.read_version())
    assert int(fields["Installed-Size"]) > 0
    for dep in ("python3-numpy", "python3-pil", "python3-argon2", "python3-cryptography"):
        assert dep in fields["Depends"]
    assert "ffmpeg" in fields["Recommends"] and "python3-scapy" in fields["Suggests"]
    assert "@" in fields["Maintainer"]


def test_launcher_uses_the_system_python_not_env_lookup(staged):
    launcher = (staged / "usr" / "bin" / "stegoforge").read_text()
    assert launcher.startswith("#!/bin/sh") and "/usr/bin/python3" in launcher
    assert "env python" not in launcher  # a pyenv/conda python on PATH would not see dist-packages


def test_every_requirement_has_a_debian_mapping():
    import re

    names = {re.split(r"[<>=!~\[ ]", ln.strip(), maxsplit=1)[0].lower().replace("_", "-")
             for ln in (ROOT / "requirements.txt").read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    names |= {re.split(r"[<>=!~\[ ]", ln.strip(), maxsplit=1)[0].lower().replace("_", "-")
              for ln in (ROOT / "requirements-web.txt").read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    missing = sorted(n for n in names if n not in build_deb.PIP_TO_DEB)
    assert not missing, f"add these to PIP_TO_DEB in scripts/build_deb.py: {missing}"
    listed = set(build_deb.DEPENDS + build_deb.RECOMMENDS + build_deb.SUGGESTS)
    for pip_name, deb_name in build_deb.PIP_TO_DEB.items():
        if deb_name is not None:
            assert deb_name in listed, f"{pip_name} -> {deb_name} is mapped but never declared"


def test_deb_version_translates_prereleases():
    assert build_deb.deb_version("1.5.0") == "1.5.0"
    assert build_deb.deb_version("1.5.0rc1") == "1.5.0~rc1"
    assert build_deb.deb_version("2.0.0.dev3") == "2.0.0~dev3"


@pytest.mark.skipif(shutil.which("dpkg-deb") is None, reason="dpkg-deb not installed")
def test_built_deb_is_owned_by_root_and_lists_the_ops_package(tmp_path):
    deb = build_deb.build(tmp_path)
    listing = subprocess.run(["dpkg-deb", "--contents", str(deb)], capture_output=True, text=True, check=True).stdout
    assert "usr/share/stegoforge/stegoforge_ops/encode_ops.py" in listing
    assert "usr/share/man/man1/stegoforge.1.gz" in listing
    owners = {line.split()[1] for line in listing.splitlines()}
    assert owners == {"root/root"}
