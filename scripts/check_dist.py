#!/usr/bin/env python3
"""scripts/check_dist.py — verify built distributions actually contain the program.

    python scripts/check_dist.py dist/*

A wheel that imports fine in the source tree can still ship without a package,
the ML model or the web assets (an earlier release did: 186 KB, no models). Run
this on every build before publishing.
"""
from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

WHEEL_REQUIRED = [
    "stegoforge.py",
    "stegoforge_ops/__init__.py",
    "stegoforge_ops/encode_ops.py",
    "stegoforge_ops/decode_ops.py",
    "stegoforge_ops/schemas/json-schema.json",
    "stegoforge_ops/schemas/JSON-SCHEMA.md",
    "core/version.py",
    "core/crypto/aes.py",
    "core/video/_luma.py",
    "detect/chi2.py",
    "protocol/deadrop.py",
    "web/app.py",
    "web/blueprints/forms.py",
    "web/templates/index.html",
    "web/static/app.js",
    "web/static/style.css",
    "models/model_quantized.onnx",
    "models/model_quantized.onnx.sha256",
]
SDIST_REQUIRED = WHEEL_REQUIRED + [
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "requirements.lock",
    "requirements.hash.lock",
    "assets.sha256",
    "scripts/build_deb.py",
    "docs/THREAT-MODEL.md",
]
FORBIDDEN_PREFIXES = ("tests/", "venv/", ".git/", "build/", "dist/")


def _names(path: Path) -> list[str]:
    if path.suffix == ".whl":
        return zipfile.ZipFile(path).namelist()
    if path.name.endswith(".tar.gz"):
        # sdist members are prefixed with "<name>-<version>/"
        return [n.split("/", 1)[1] for n in tarfile.open(path).getnames() if "/" in n]
    raise SystemExit(f"{path}: not a .whl or .tar.gz")


def check(path: Path) -> list[str]:
    names = set(_names(path))
    required = WHEEL_REQUIRED if path.suffix == ".whl" else SDIST_REQUIRED
    problems = [f"missing {need}" for need in required if need not in names]
    if path.suffix == ".whl":
        problems += [f"unexpected {n}" for n in sorted(names) if n.startswith(FORBIDDEN_PREFIXES)]
        if path.stat().st_size < 1_000_000:
            problems.append(f"only {path.stat().st_size:,} bytes: the bundled model is probably missing")
    return problems


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv if not Path(a).name.startswith(".")]
    paths = [p for p in paths if p.suffix == ".whl" or p.name.endswith(".tar.gz")]
    if not paths:
        print("no .whl / .tar.gz given", file=sys.stderr)
        return 2
    failed = False
    for path in paths:
        problems = check(path)
        status = "ok" if not problems else "FAILED"
        print(f"{path.name}: {status}")
        for problem in problems:
            print(f"  - {problem}")
        failed |= bool(problems)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
