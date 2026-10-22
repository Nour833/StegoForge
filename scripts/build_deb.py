#!/usr/bin/env python3
"""scripts/build_deb.py — build the Debian package from the working tree (stdlib only).

    python3 scripts/build_deb.py [--out DIR] [--stage-only DIR]

The package is architecture-independent and uses the distribution's own Python
libraries (``python3-numpy`` and friends), which suits Debian, Ubuntu and Kali.

The set of directories that ship is **derived from the project's package
discovery**, not hand-listed: the previous inline recipe copied a fixed list that
forgot ``stegoforge_ops``, so the installed command could not even be imported.
``tests/test_packaging_deb.py`` stages the tree and runs the CLI from it.
"""
from __future__ import annotations

import argparse
import gzip
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL_DIR = "usr/share/stegoforge"
DOC_DIR = "usr/share/doc/stegoforge"
DEFAULT_MAINTAINER = "StegoForge <nourelislem84@outlook.fr>"

# pip requirement -> Debian package. ``None`` means "no Debian package; not needed there".
# tests/test_packaging_deb.py fails when requirements.txt gains an entry that is not listed here.
PIP_TO_DEB: dict[str, str | None] = {
    "pillow": "python3-pil",
    "numpy": "python3-numpy",
    "scipy": "python3-scipy",
    "cryptography": "python3-cryptography",
    "argon2-cffi": "python3-argon2",
    "typer": "python3-typer",
    "rich": "python3-rich",
    "certifi": "python3-certifi",
    "reedsolo": "python3-reedsolo",
    "pypdf": "python3-pypdf",
    "lxml": "python3-lxml",
    "piexif": "python3-piexif",
    "av": "python3-av",
    "flask": "python3-flask",
    "flask-cors": "python3-flask-cors",
    "onnxruntime": "python3-onnxruntime",
    "scapy": "python3-scapy",
    "imageio-ffmpeg": None,  # the `ffmpeg` package is recommended instead
}
DEPENDS = ["python3 (>= 3.10)", "python3-numpy", "python3-scipy", "python3-pil", "python3-cryptography",
           "python3-argon2", "python3-typer", "python3-rich", "python3-certifi", "python3-reedsolo"]
RECOMMENDS = ["python3-pypdf", "python3-lxml", "python3-piexif", "python3-flask", "python3-flask-cors",
              "python3-av", "ffmpeg"]
SUGGESTS = ["python3-scapy", "python3-onnxruntime"]

DESCRIPTION = """The most complete open-source steganography toolkit.
 Hide, extract and detect data in images, audio, video, documents and
 executables. Payloads are sealed with AES-256-GCM under an Argon2id key.
 .
 This is the native distribution: it uses the system Python libraries instead
 of bundling its own, which suits Debian, Ubuntu and Kali. Optional features
 (PDF, web UI, video, ML steganalysis) are enabled by the recommended packages."""

LAUNCHER = """#!/bin/sh
exec /usr/bin/python3 /usr/share/stegoforge/stegoforge.py "$@"
"""
POSTINST = """#!/bin/sh
set -e
if [ "$1" = "configure" ] && command -v py3compile >/dev/null 2>&1; then
    py3compile -p stegoforge /usr/share/stegoforge || true
fi
exit 0
"""
PRERM = """#!/bin/sh
set -e
if command -v py3clean >/dev/null 2>&1; then
    py3clean -p stegoforge /usr/share/stegoforge || true
fi
exit 0
"""


def read_version() -> str:
    namespace: dict[str, str] = {}
    exec((ROOT / "core" / "version.py").read_text(encoding="utf-8"), namespace)  # noqa: S102 - our own file
    return str(namespace["__version__"])


def deb_version(version: str) -> str:
    """PEP 440 -> Debian: ``1.5.0rc1`` sorts before ``1.5.0`` only as ``1.5.0~rc1``."""
    return re.sub(r"[-.]?(a|b|rc|dev)(\d*)", lambda m: f"~{m.group(1)}{m.group(2)}", version)


def package_dirs() -> list[str]:
    """Top-level import packages of the project plus the model directory.

    Same rule as ``setup.py``'s ``find_packages(exclude=["tests*"])`` for top-level names (a directory
    with an ``__init__.py``), without importing setuptools, which Python 3.12 environments lack.
    ``tests/test_packaging_deb.py`` checks the two agree.
    """
    tops = {
        d.name for d in ROOT.iterdir()
        if d.is_dir() and (d / "__init__.py").is_file() and not d.name.startswith(("tests", "."))
    }
    return sorted(tops | {"models"})  # `models` is a package now; the union keeps this correct either way


def _ignore(_dir: str, names: list[str]) -> set[str]:
    return {n for n in names if n in ("__pycache__", ".cache") or n.endswith((".pyc", ".pyo"))}


def _chmod_tree(base: Path) -> None:
    for path in [base, *base.rglob("*")]:
        if path.is_symlink():
            continue
        if path.is_dir() or path.suffix in ("", ".sh", ".py") and os.access(path, os.X_OK):
            path.chmod(0o755)
        else:
            path.chmod(0o644)


def render_control(version: str, installed_kib: int, maintainer: str) -> str:
    return "\n".join([
        "Package: stegoforge",
        f"Version: {deb_version(version)}",
        "Section: utils",
        "Priority: optional",
        "Architecture: all",
        f"Installed-Size: {installed_kib}",
        f"Maintainer: {maintainer}",
        "Homepage: https://github.com/nour833/StegoForge",
        f"Depends: {', '.join(DEPENDS)}",
        f"Recommends: {', '.join(RECOMMENDS)}",
        f"Suggests: {', '.join(SUGGESTS)}",
        f"Description: {DESCRIPTION}",
        "",
    ])


def _dir_size_kib(base: Path) -> int:
    return -(-sum(p.stat().st_size for p in base.rglob("*") if p.is_file()) // 1024)


def stage(dest: Path, maintainer: str | None = None) -> Path:
    """Lay the package out under ``dest`` (a fresh directory). Returns ``dest``."""
    if dest.exists():
        shutil.rmtree(dest)
    install = dest / INSTALL_DIR
    install.mkdir(parents=True)

    for name in package_dirs():
        shutil.copytree(ROOT / name, install / name, ignore=_ignore)
    for name in ("stegoforge.py", "assets.sha256"):
        shutil.copy2(ROOT / name, install / name)

    bin_dir = dest / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "stegoforge").write_text(LAUNCHER)
    (bin_dir / "stegoforge").chmod(0o755)

    doc = dest / DOC_DIR
    doc.mkdir(parents=True)
    shutil.copy2(ROOT / "LICENSE", doc / "copyright")
    shutil.copy2(ROOT / "README.md", doc / "README.md")
    for name in ("THREAT-MODEL.md", "METHODS.md", "OFFLINE.md", "PROTOCOL.md"):
        if (ROOT / "docs" / name).exists():
            shutil.copy2(ROOT / "docs" / name, doc / name)
    with gzip.GzipFile(doc / "changelog.gz", "wb", mtime=0) as gz:
        gz.write((ROOT / "CHANGELOG.md").read_bytes())

    man = ROOT / "docs" / "stegoforge.1"
    if man.exists():
        man_dir = dest / "usr" / "share" / "man" / "man1"
        man_dir.mkdir(parents=True)
        with gzip.GzipFile(man_dir / "stegoforge.1.gz", "wb", mtime=0) as gz:
            gz.write(man.read_bytes())

    debian = dest / "DEBIAN"
    debian.mkdir()
    for name, body in (("postinst", POSTINST), ("prerm", PRERM)):
        (debian / name).write_text(body)
        (debian / name).chmod(0o755)

    _chmod_tree(dest / "usr")
    (bin_dir / "stegoforge").chmod(0o755)
    (debian / "control").write_text(
        render_control(read_version(), _dir_size_kib(dest / "usr"), maintainer or os.getenv("DEB_MAINTAINER", DEFAULT_MAINTAINER)),
        encoding="utf-8",
    )
    return dest


def build(out_dir: Path, work_dir: Path | None = None) -> Path:
    """Stage and run ``dpkg-deb``; returns the path of the resulting ``.deb``."""
    if shutil.which("dpkg-deb") is None:
        raise SystemExit("dpkg-deb not found: install dpkg (apt install dpkg-dev) to build the package")
    import tempfile

    with tempfile.TemporaryDirectory(prefix="stegoforge_deb_") as tmp:
        staged = stage(Path(work_dir or tmp) / f"stegoforge_{deb_version(read_version())}_all")
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"stegoforge_{deb_version(read_version())}_all.deb"
        subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(staged), str(target)], check=True)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path("."), help="directory for the .deb (default: .)")
    parser.add_argument("--stage-only", type=Path, metavar="DIR", help="only lay the package out under DIR")
    args = parser.parse_args(argv)
    if args.stage_only:
        print(stage(args.stage_only))
        return 0
    deb = build(args.out)
    print(deb)
    return 0


if __name__ == "__main__":
    sys.exit(main())
