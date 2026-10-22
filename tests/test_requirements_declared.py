"""tests/test_requirements_declared.py — every third-party import must be a declared requirement.

`lxml` was imported by the Office carriers but never declared; it only worked
because `python-docx` happened to pull it in. A clean install would have failed.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SHIPPED = ("core", "detect", "protocol", "web", "stegoforge_ops")
LOCAL = {"core", "detect", "protocol", "web", "stegoforge_ops", "stegoforge", "models", "scripts", "tests"}
IMPORT_TO_DIST = {"PIL": "pillow", "argon2": "argon2-cffi", "flask_cors": "flask-cors", "imageio_ffmpeg": "imageio-ffmpeg"}


def _declared() -> set[str]:
    names = set()
    for name in ("requirements.txt", "requirements-web.txt"):
        for line in (ROOT / name).read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                names.add(re.split(r"[<>=!~\[ ]", line.strip(), maxsplit=1)[0].lower().replace("_", "-"))
    return names


def _third_party_imports() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    files = [ROOT / "stegoforge.py"] + [p for pkg in SHIPPED for p in (ROOT / pkg).rglob("*.py")]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                mods = [node.module]
            else:
                continue
            for mod in mods:
                top = mod.split(".")[0]
                if top not in sys.stdlib_module_names and top not in LOCAL:
                    found.setdefault(top, set()).add(str(path.relative_to(ROOT)))
    return found


def test_every_third_party_import_is_declared():
    declared = _declared()
    undeclared = {
        mod: sorted(files)[:3]
        for mod, files in _third_party_imports().items()
        if IMPORT_TO_DIST.get(mod, mod.lower().replace("_", "-")) not in declared
    }
    assert not undeclared, f"imported but not in requirements*.txt: {undeclared}"


def test_no_declared_requirement_is_dead_weight():
    imported = {IMPORT_TO_DIST.get(m, m.lower().replace("_", "-")) for m in _third_party_imports()}
    unused = sorted(_declared() - imported)
    assert not unused, f"declared in requirements*.txt but never imported: {unused}"
