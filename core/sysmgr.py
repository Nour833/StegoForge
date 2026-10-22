"""core/sysmgr.py — local asset locations and environment diagnostics.

StegoForge never downloads executables or models. FFmpeg (needed only to convert
MP3/FLAC/OGG audio) comes from ``STEGOFORGE_FFMPEG``, the ``PATH`` or the
``imageio-ffmpeg`` dependency — see ``core/audio/_convert.py`` — and the ML
steganalysis model ships inside the package. Fetching a binary over the network,
unverified, and then executing it is exactly what a security tool must not do.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import logging
import os
import shutil
import sys
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

STEGOFORGE_DIR = Path.home() / ".stegoforge"
MODELS_DIR = STEGOFORGE_DIR / "models"


def ffmpeg_available() -> bool:
    """True when an ffmpeg binary can be located (needed for MP3/FLAC/OGG only)."""
    from core.audio._convert import ffmpeg_path

    return ffmpeg_path() is not None


def model_available() -> bool:
    """True when the bundled ML steganalysis model (or a local copy of it) is present."""
    from detect.ml_steganalysis import MODEL_NAME, bundled_model_paths

    if (MODELS_DIR / MODEL_NAME).exists():
        return True
    return any(p.exists() and p.stat().st_size > 0 for p in bundled_model_paths())


def sha256_file(path: Path) -> str:
    """Stream SHA256 of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_asset_hash(path: Path, kind: str) -> bool:
    """Verify an optional SHA256 pin from the environment (``STEGOFORGE_MODEL_SHA256``).

    Returns True if no pin is set or the hash matches; False on a mismatch.
    """
    env_key = {"model": "STEGOFORGE_MODEL_SHA256"}.get(kind)
    expected = os.getenv(env_key, "") if env_key else ""
    if not expected:
        return True
    try:
        actual = sha256_file(Path(path))
    except OSError:
        return False
    return actual.lower() == expected.strip().lower()


def install_bundled_model() -> tuple[bool, str]:
    """Copy the packaged model into ``~/.stegoforge/models`` (offline). Returns ``(ok, message)``."""
    from detect.ml_steganalysis import MODEL_NAME, bundled_model_paths

    for bundled in bundled_model_paths():
        if not (bundled.exists() and bundled.stat().st_size > 0):
            continue
        if not verify_asset_hash(bundled, "model"):
            return False, "bundled model does not match STEGOFORGE_MODEL_SHA256; refusing to install it"
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundled, MODELS_DIR / MODEL_NAME)
        return True, f"installed {MODEL_NAME} from the bundled copy"
    return False, "this installation does not include the ML model (the other detectors are unaffected)"


# ── diagnostics (`stegoforge doctor`) ─────────────────────────────────────────

@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    required: bool = True


_REQUIRED_PACKAGES = ("numpy", "scipy", "Pillow", "cryptography", "argon2-cffi", "typer", "rich", "reedsolo")
_OPTIONAL_PACKAGES = (
    ("av", "video methods (video-dct, video-motion)"),
    ("pypdf", "PDF carriers"),
    ("flask", "web UI: pip install 'stegoforge[web]'"),
    ("onnxruntime", "ML steganalysis"),
)


# distribution name -> import name, for the cases where they differ
_IMPORT_NAME = {"Pillow": "PIL", "argon2-cffi": "argon2"}


def _version(dist: str) -> str | None:
    """Installed version of ``dist``; falls back to importing it (frozen builds carry no metadata)."""
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        pass
    try:
        module = importlib.import_module(_IMPORT_NAME.get(dist, dist))
    except ImportError:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)  # argon2/flask deprecate __version__
            return str(module.__version__)
    except Exception:  # noqa: BLE001 - e.g. Flask resolves __version__ via importlib.metadata, which a frozen build lacks
        return "installed"


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path):
            return True
    except OSError:
        return False


def diagnose() -> list[Check]:
    """Inspect the local environment. Never touches the network."""
    from core.config import get_config
    from core.version import __version__

    checks = [Check("StegoForge", True, __version__)]
    py = sys.version_info
    checks.append(Check("Python", py >= (3, 10), f"{py.major}.{py.minor}.{py.micro}" + ("" if py >= (3, 10) else " (3.10+ required)")))

    for dist in _REQUIRED_PACKAGES:
        v = _version(dist)
        checks.append(Check(dist, v is not None, v or "not installed (pip install -r requirements.txt)"))
    for dist, purpose in _OPTIONAL_PACKAGES:
        v = _version(dist)
        checks.append(Check(dist, v is not None, v or f"not installed — needed for {purpose}", required=False))

    if _version("av") is not None:
        try:
            av = importlib.import_module("av")
            has_x264 = "libx264" in av.codecs_available
        except Exception as exc:  # noqa: BLE001 - a broken native install is exactly what doctor reports
            checks.append(Check("libx264", False, f"PyAV failed to load: {exc}", required=False))
        else:
            checks.append(Check("libx264", has_x264, "lossless video encoder available" if has_x264
                                else "missing from this PyAV build; video methods unavailable", required=False))

    from core.audio._convert import ffmpeg_path

    ffmpeg = ffmpeg_path()
    checks.append(Check("ffmpeg", ffmpeg is not None, ffmpeg or "not found — only MP3/FLAC/OGG conversion needs it "
                        "(sudo apt install ffmpeg, or set STEGOFORGE_FFMPEG)", required=False))
    checks.append(Check("ML model", model_available(), "bundled model present" if model_available()
                        else "not packaged in this install; ML detector disabled", required=False))
    checks.append(Check("Temp dir writable", _writable(Path(tempfile.gettempdir())), tempfile.gettempdir()))
    checks.append(Check("Offline mode", True, "on — network features disabled" if get_config().offline else "off", required=False))
    return checks


def bootstrap_if_needed(require: list[str] | None = None, force: bool = False) -> None:
    """Compatibility shim: nothing is fetched. ``force`` re-installs the bundled model quietly."""
    if force:
        ok, message = install_bundled_model()
        log.info("bundled model: %s", message)
        if not ok:
            log.debug("bundled model not installed: %s", message)
