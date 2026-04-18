#!/usr/bin/env python3
"""
stegoforge.py — StegoForge CLI

Animated ASCII banner, interactive menu, and direct bypass arguments.
All features accessible both interactively and via direct args.
"""
import json
import errno
import os
import sys
import time
import io
import platform
import re
import shutil
import ssl
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from core import sysmgr
from core.version import __version__ as APP_VERSION
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.live import Live
from rich.spinner import Spinner
from rich.prompt import Prompt, Confirm
from rich.columns import Columns
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

# ── App setup ─────────────────────────────────────────────────────────────────
app = typer.Typer(
    name="stegoforge",
    help="StegoForge — The most complete steganography toolkit",
    invoke_without_command=True,
    no_args_is_help=False,
    rich_markup_mode="rich",
    add_completion=False,
)
deadrop_app = typer.Typer(help="Dead drop protocol operations")
deadrop_keyx_app = typer.Typer(help="Steganographic X25519 key exchange operations")
deadrop_app.add_typer(deadrop_keyx_app, name="keyx")
app.add_typer(deadrop_app, name="deadrop")
console = Console()

# ── Color palette ─────────────────────────────────────────────────────────────
C_TITLE   = "bold bright_cyan"
C_ACCENT  = "bright_magenta"
C_SUCCESS = "bold bright_green"
C_WARN    = "bold yellow"
C_ERROR   = "bold bright_red"
C_DIM     = "dim white"
C_INFO    = "bright_blue"
C_GOLD    = "bold yellow"
C_PURPLE  = "bold magenta"

# ── ASCII Banner ──────────────────────────────────────────────────────────────
BANNER = r"""
 ███████╗████████╗███████╗ ██████╗  ██████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
 ██╔════╝╚══██╔══╝██╔════╝██╔════╝ ██╔═══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
 ███████╗   ██║   █████╗  ██║  ███╗██║   ██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
 ╚════██║   ██║   ██╔══╝  ██║   ██║██║   ██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
 ███████║   ██║   ███████╗╚██████╔╝╚██████╔╝██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
 ╚══════╝   ╚═╝   ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
"""

TAGLINES = [
    "Advanced Heuristics  ·  Argon2id Key Derivation  ·  Polymorphic LSB",
    "Zero-Day Survivability  ·  Wet-Paper Error Correction  ·  Audio Phase Codes",
    "Forensic Invisibility  ·  Network Covert Channels  ·  Denial Mechanics",
    "Secure Dead Drops  ·  Curve25519 Key Exchange  ·  AES-256-GCM",
]
PRIMARY_TAGLINE = "Infiltrate Digital Carriers  ·  Evade Cryptanalysis"

UI_ANIMATION_ENABLED = os.getenv("STEGOFORGE_FAST_UI", "0") not in ("1", "true", "TRUE", "yes", "YES")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
        return value if value >= 0 else default
    except ValueError:
        return default


UI_STAGE_DELAY = _env_float("STEGOFORGE_UI_STAGE_DELAY", 0.45)
UI_TRANSITION_DELAY = _env_float("STEGOFORGE_UI_TRANSITION_DELAY", 0.55)
GITHUB_REPO = os.getenv("STEGOFORGE_GITHUB_REPO", "Nour833/StegoForge").strip()
GITHUB_RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


def _ui_sleep(seconds: float):
    """Sleep helper that can be disabled for automation or fast startup."""
    if UI_ANIMATION_ENABLED and sys.stdout.isatty():
        time.sleep(seconds)


def _startup_loading_sequence():
    """Render a short startup loading animation for the interactive UI."""
    if not (UI_ANIMATION_ENABLED and sys.stdout.isatty()):
        return

    stages = [
        ("VFS", "Mounting virtual encoding registry...", "cyan"),
        ("SEC", "Bypassing entropy constraints...", "magenta"),
        ("ML",  "Loading ONNX steganalysis models...", "blue"),
        ("CRY", "Priming cryptographic keyspace...", "green"),
    ]

    console.clear()
    console.print()

    for prefix, msg, color in stages:
        console.print(f"  [{color}][{prefix}][/{color}] {msg}", end="")
        sys.stdout.flush()
        _ui_sleep(UI_STAGE_DELAY * 0.8)
        console.print(f" [{C_SUCCESS}]OK[/{C_SUCCESS}]")
        _ui_sleep(UI_STAGE_DELAY * 0.2)

    console.print()
    console.print(Align.center(f"[{C_SUCCESS}]System Sequence Initialized. Directives unlocked.[/{C_SUCCESS}]"))
    console.print()
    _ui_sleep(0.5)


def _menu_transition(action: str):
    """Small transition spinner before opening a menu action."""
    if not (UI_ANIMATION_ENABLED and sys.stdout.isatty()):
        return
    with console.status(f"[{C_INFO}]Opening {action}...[/{C_INFO}]", spinner="dots"):
        _ui_sleep(UI_TRANSITION_DELAY)


def print_banner():
    """Print the animated StegoForge banner."""
    banner_text = Text()
    lines = BANNER.strip('\n').split('\n')
    colors = ["#00ffff", "#00dfff", "#00bfff", "#009fff", "#007fff", "#005fff"]
    
    if UI_ANIMATION_ENABLED and sys.stdout.isatty():
        from rich.live import Live
        with Live(Align.center(banner_text), console=console, refresh_per_second=25, transient=False) as live:
            for i, line in enumerate(lines):
                color = colors[i % len(colors)]
                banner_text.append(line + "\n", style=f"bold {color}")
                live.update(Align.center(banner_text))
                time.sleep(0.08)
    else:
        for i, line in enumerate(lines):
            color = colors[i % len(colors)]
            banner_text.append(line + "\n", style=f"bold {color}")
        console.print(Align.center(banner_text))

    if UI_ANIMATION_ENABLED and sys.stdout.isatty():
        _ui_sleep(0.3)
        # Cinematic typing effect
        padding_width = max(0, (console.width - len(PRIMARY_TAGLINE)) // 2)
        sys.stdout.write(" " * padding_width)
        for char in PRIMARY_TAGLINE:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(0.015)
        print("\n")
        
        highlight = TAGLINES[int(time.time()) % len(TAGLINES)]
        console.print(Align.center(f"[dim]{highlight}[/dim]"))
        _ui_sleep(0.3)
    else:
        console.print(Align.center(f"[bold white]{PRIMARY_TAGLINE}[/bold white]"))
    
    console.print()

    # CLI Panel
    info_text = Text()
    info_text.append("Framework Version: ", style="dim")
    info_text.append(f"{_current_version()}-CORE", style="bold white")
    info_text.append("   ·   ", style="dim")
    info_text.append("Payload Modules: ", style="dim")
    info_text.append("20", style="bold white")
    info_text.append("   ·   ", style="dim")
    info_text.append("Forensic Engines: ", style="dim")
    info_text.append("11\n", style="bold white")
    info_text.append("Encryption: ", style="bold bright_red")
    info_text.append("AES-256-GCM", style="bold white")
    info_text.append("   ·   ", style="dim")
    info_text.append("Mode: ", style="bold bright_magenta")
    info_text.append("STEALTH", style="bold white")

    panel = Panel(
        Align.center(info_text),
        title="[bold white]StegoForge[/bold white]",
        subtitle="[bold bright_yellow]Made by nour833[/bold bright_yellow]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 4),
        expand=False
    )
    console.print(Align.center(panel))
    console.print()


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", value or "")
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts[:4])


def _current_version() -> str:
    env_version = str(os.getenv("STEGOFORGE_VERSION", "")).strip()
    if env_version:
        return env_version

    if APP_VERSION:
        return APP_VERSION

    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version("stegoforge")
        except PackageNotFoundError:
            return "0.0.0"
    except Exception:
        return "0.0.0"


def _display_version(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "unknown"
    if re.match(r"^[vV]\d", text):
        return text[1:]
    return text


def _detect_install_kind() -> str:
    if bool(getattr(sys, "frozen", False)):
        return "release-binary"

    repo_root = Path(__file__).resolve().parent
    if (repo_root / ".git").exists():
        return "source-checkout"

    return "python-package"


def _manual_update_command(install_kind: str) -> str:
    if install_kind == "source-checkout":
        repo_root = Path(__file__).resolve().parent
        return f'git -C "{repo_root}" pull --ff-only'

    if install_kind == "python-package":
        py_exec = Path(sys.executable).resolve()
        return f'"{py_exec}" -m pip install --upgrade stegoforge'

    return ""


def _print_update_versions(probe: dict):
    current = _display_version(str(probe.get("current", "unknown")))
    latest = _display_version(str(probe.get("latest", "unknown")))
    console.print(f"[{C_INFO}]Current version: {current}[/{C_INFO}]")
    console.print(f"[{C_INFO}]Latest release: {latest}[/{C_INFO}]")


def _is_archive_asset(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".zip") or lower.endswith(".tar.gz") or lower.endswith(".tgz")


def _select_release_asset(assets: list[dict]) -> Optional[dict]:
    system = platform.system().lower()
    arch = platform.machine().lower()
    os_aliases = {
        "linux": ("linux", "gnu-linux", "manylinux"),
        "windows": ("windows", "win32", "win64", "mingw", ".exe"),
        "darwin": ("darwin", "macos", "osx", "universal2", "mac"),
    }
    arch_aliases = {
        "x86_64": ("x86_64", "amd64", "x64"),
        "amd64": ("x86_64", "amd64", "x64"),
        "aarch64": ("aarch64", "arm64"),
        "arm64": ("aarch64", "arm64"),
        "armv7l": ("armv7", "armv7l"),
        "i386": ("i386", "x86"),
        "i686": ("i686", "x86"),
    }

    def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
        return any(n in haystack for n in needles)

    def _token_set(haystack: str) -> set[str]:
        normalized = haystack.replace("-", "_")
        return set(re.findall(r"[a-z0-9_]+", normalized))

    def _contains_any_token(tokens: set[str], needles: tuple[str, ...]) -> bool:
        return any(n in tokens for n in needles)

    all_arch_markers = (
        "x86_64", "amd64", "x64", "aarch64", "arm64", "armv7", "armv7l", "i386", "i686", "x86"
    )

    expected_os = os_aliases.get(system, ())
    expected_arch = arch_aliases.get(arch, ())
    best = None
    best_score = -1
    candidates: list[dict] = []

    for asset in assets:
        name = str(asset.get("name", "")).strip()
        if not name:
            continue
        lower = name.lower()
        tokens = _token_set(lower)

        if any(lower.endswith(ext) for ext in (".sha256", ".sha512", ".sig", ".txt", ".json")):
            continue
        candidates.append(asset)

        score = 0
        if expected_os and not _contains_any(lower, expected_os):
            continue
        score += 8

        mentions_any_arch = _contains_any_token(tokens, all_arch_markers)
        if expected_arch and _contains_any_token(tokens, expected_arch):
            score += 4
        elif mentions_any_arch and expected_arch:
            # Asset explicitly targets a different architecture.
            continue
        else:
            # OS match but architecture not stated; keep as lower-priority fallback.
            score += 1

        if lower.startswith("stegoforge"):
            score += 1

        if _is_archive_asset(name):
            score -= 1

        if score > best_score:
            best_score = score
            best = asset

    # If only one meaningful asset exists, accept it as a universal fallback.
    if best is None and len(candidates) == 1:
        return candidates[0]

    return best


def _is_cert_verification_error(exc: BaseException) -> bool:
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True

    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, ssl.SSLCertVerificationError):
            return True
        if isinstance(reason, ssl.SSLError):
            reason_text = str(reason).lower()
            return (
                "certificate_verify_failed" in reason_text
                or "unable to get local issuer certificate" in reason_text
            )

    message = str(exc).lower()
    return (
        "certificate_verify_failed" in message
        or "unable to get local issuer certificate" in message
    )


def _certifi_ssl_context() -> Optional[ssl.SSLContext]:
    try:
        import certifi
    except Exception:
        return None

    cafile = certifi.where()
    if not cafile:
        return None
    return ssl.create_default_context(cafile=cafile)


def _urlopen_with_ca_fallback(req: urllib.request.Request, timeout: int):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except (urllib.error.URLError, ssl.SSLError) as exc:
        if not _is_cert_verification_error(exc):
            raise

        fallback_context = _certifi_ssl_context()
        if fallback_context is None:
            raise urllib.error.URLError(
                "TLS certificate verification failed while contacting GitHub. "
                "Install/update system CA certificates or install the 'certifi' package."
            ) from exc

        try:
            return urllib.request.urlopen(req, timeout=timeout, context=fallback_context)
        except (urllib.error.URLError, ssl.SSLError) as fallback_exc:
            if _is_cert_verification_error(fallback_exc):
                raise urllib.error.URLError(
                    "TLS certificate verification failed while contacting GitHub even with "
                    "the certifi CA bundle. Check proxy/TLS interception settings and trust "
                    "store configuration."
                ) from fallback_exc
            raise


def _download_release_asset(url: str, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "StegoForge-Updater",
            "Accept": "application/octet-stream",
        },
    )

    with _urlopen_with_ca_fallback(req, timeout=120) as resp, target.open("wb") as out:
        total = int(resp.headers.get("Content-Length", "0") or "0")
        chunk = 256 * 1024

        if total > 0:
            with Progress(
                SpinnerColumn(),
                TextColumn("[cyan]Downloading update...[/cyan]"),
                BarColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                console=console,
            ) as progress:
                task = progress.add_task("download", total=total)
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    out.write(data)
                    progress.update(task, advance=len(data))
        else:
            with console.status(f"[{C_INFO}]Downloading update...[/{C_INFO}]", spinner="dots"):
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    out.write(data)


def _safe_replace(src: Path, dst: Path):
    """Replace dst with src, handling cross-filesystem moves (EXDEV)."""
    try:
        os.replace(src, dst)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise

    staged = dst.parent / f".{dst.name}.new"
    if staged.exists():
        staged.unlink()

    try:
        shutil.copy2(src, staged)
        os.replace(staged, dst)
    finally:
        staged.unlink(missing_ok=True)


def op_update(check_only: bool = False, auto_apply: bool = False) -> dict:
    current = _current_version()
    install_kind = _detect_install_kind()
    req = urllib.request.Request(
        GITHUB_RELEASES_LATEST_URL,
        headers={
            "User-Agent": "StegoForge-Updater",
            "Accept": "application/vnd.github+json",
        },
    )

    with _urlopen_with_ca_fallback(req, timeout=25) as resp:
        release = json.loads(resp.read().decode("utf-8"))

    latest_tag = str(release.get("tag_name") or release.get("name") or "").strip()
    release_url = str(release.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases").strip()
    assets = release.get("assets") or []
    selected = _select_release_asset(assets)

    update_available = _version_tuple(latest_tag) > _version_tuple(current)
    result = {
        "current": current,
        "latest": latest_tag,
        "update_available": update_available,
        "release_url": release_url,
        "install_kind": install_kind,
        "asset_name": str(selected.get("name")) if selected else "",
        "asset_url": str(selected.get("browser_download_url")) if selected else "",
        "downloaded_path": "",
        "applied": False,
        "can_auto_apply": False,
        "manual_update_command": _manual_update_command(install_kind),
    }

    if not update_available or check_only:
        return result

    if install_kind != "release-binary":
        # Source checkouts and pip installs should be updated via their native installers.
        return result

    if not selected:
        return result

    asset_name = str(selected.get("name", "")).strip()
    asset_url = str(selected.get("browser_download_url", "")).strip()
    if not asset_name or not asset_url:
        return result

    frozen = bool(getattr(sys, "frozen", False))
    exe_path = Path(sys.argv[0]).resolve()
    can_auto_apply = (
        auto_apply
        and frozen
        and platform.system() != "Windows"
        and exe_path.exists()
        and os.access(exe_path.parent, os.W_OK)
        and not _is_archive_asset(asset_name)
    )
    result["can_auto_apply"] = can_auto_apply

    tmp_dir = Path(tempfile.mkdtemp(prefix="stegoforge_update_"))
    tmp_target = tmp_dir / asset_name
    try:
        _download_release_asset(asset_url, tmp_target)

        if platform.system() != "Windows" and not _is_archive_asset(asset_name):
            try:
                tmp_target.chmod(tmp_target.stat().st_mode | 0o111)
            except OSError:
                pass

        if can_auto_apply:
            backup = Path(f"{exe_path}.old")
            if backup.exists():
                backup.unlink()
            shutil.copy2(exe_path, backup)
            _safe_replace(tmp_target, exe_path)
            result["applied"] = True
            result["downloaded_path"] = str(exe_path)
            result["backup_path"] = str(backup)
            return result

        out_dir = exe_path.parent if frozen and exe_path.parent.exists() else Path.cwd()
        out_path = out_dir / asset_name
        if out_path.exists():
            out_path = out_dir / f"{asset_name}.new"
        shutil.move(str(tmp_target), str(out_path))
        result["downloaded_path"] = str(out_path)
        return result
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Stealth score registry (0-100, higher = harder to detect) ────────────────
# Each score weights: chi-square resistance, RS resistance, ML evasion,
# perceptual invisibility, and social-media survivability.
STEALTH_SCORES: dict[str, int] = {
    "adaptive-lsb":    88,
    "fingerprint-lsb": 85,
    "video-motion":    82,
    "linguistic":      95,
    "dct":             72,
    "alpha":           70,
    "palette":         78,
    "lsb":             45,
    "video-dct":       65,
    "audio-lsb":       60,
    "phase":           68,
    "spectrogram":     55,
    "unicode":         80,
    "pdf":             75,
    "docx":            74,
    "xlsx":            74,
    "elf":             50,
    "pe":              50,
    "tcp-covert":      40,
    "timing-covert":   38,
}


def _stealth_bar(score: int) -> str:
    """Return a compact colored stealth bar string for CLI output."""
    filled = score // 5
    empty  = 20 - filled
    if score >= 80:
        color = "bright_green"
    elif score >= 60:
        color = "yellow"
    else:
        color = "bright_red"
    return f"[{color}]{'█' * filled}{'░' * empty}[/{color}] {score}/100"


# ── Method registry ───────────────────────────────────────────────────────────
ENCODE_METHODS = {
    "lsb":          ("Image",    "LSB — Least Significant Bit in image pixels (PNG/BMP)"),
    "adaptive-lsb": ("Image",    "Adaptive LSB — content-aware embedding, recommended for forensic resistance"),
    "dct":          ("Image",    "DCT — Frequency domain injection (JPEG)"),
    "video-dct":    ("Video",    "Video DCT — keyframe-focused embedding (MP4/WebM)"),
    "video-motion": ("Video",    "Video Motion — P-frame motion-style embedding (MP4)"),
    "alpha":        ("Image",    "Alpha — Hide in transparency channel (PNG/WebP)"),
    "palette":      ("Image",    "Palette — GIF/indexed PNG color reordering"),
    "fingerprint-lsb": ("Image", "PRNU-aware LSB embedding for fingerprint preservation"),
    "audio-lsb":    ("Audio",    "Audio LSB — PCM sample bit manipulation (WAV/FLAC)"),
    "phase":        ("Audio",    "Phase — Segment phase coding, MP3-tolerant"),
    "spectrogram":  ("Audio",    "Spectrogram — Embed visible image/text in audio spectrum"),
    "unicode":      ("Document", "Unicode — Zero-width character encoding (TXT)"),
    "linguistic":   ("Document", "Linguistic — synonym-based natural text steganography"),
    "pdf":          ("Document", "PDF — Stream/metadata injection (PDF)"),
    "docx":         ("Document", "DOCX — Custom XML stream injection (DOCX)"),
    "xlsx":         ("Document", "XLSX — Custom XML stream injection (XLSX)"),
    "elf":          ("Binary",   "ELF — section slack and notes embedding (CLI only)"),
    "pe":           ("Binary",   "PE — section slack and overlay embedding (CLI only)"),
    "tcp-covert":   ("Network",  "TCP covert channel (CLI only, authorized use only)"),
    "timing-covert":("Network",  "Timing covert channel (CLI only, authorized use only)"),
}

HYBRID_METHODS = {
    "adaptive-lsb",
    "fingerprint-lsb",
    "video-motion",
    "linguistic",
}

METHOD_CATEGORY_ORDER = ["Hybrid", "Image", "Video", "Audio", "Document", "Binary", "Network"]


def _group_encode_methods() -> list[tuple[str, list[tuple[str, str, str]]]]:
    grouped: dict[str, list[tuple[str, str, str]]] = {cat: [] for cat in METHOD_CATEGORY_ORDER}
    for method, (category, desc) in ENCODE_METHODS.items():
        if method in HYBRID_METHODS:
            grouped["Hybrid"].append((method, category, desc))
        else:
            grouped.setdefault(category, []).append((method, category, desc))
    return [(cat, grouped[cat]) for cat in METHOD_CATEGORY_ORDER if grouped.get(cat)]

DECODE_METHODS = {k: v for k, v in ENCODE_METHODS.items()}

EXT_TO_METHOD = {
    ".png":  "lsb", ".bmp": "lsb", ".tiff": "lsb",
    ".jpg":  "dct", ".jpeg": "dct",
    ".gif":  "palette",
    ".mp4":  "video-dct", ".webm": "video-dct",
    ".wav":  "audio-lsb", ".flac": "audio-lsb",
    ".mp3":  "audio-lsb", ".ogg": "audio-lsb",
    ".txt":  "unicode",
    ".pdf":  "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".webp": "alpha",
    ".elf":  "elf", ".exe": "pe", ".dll": "pe",
    ".sfrg": "sfrg"
}


def auto_detect_method(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    return EXT_TO_METHOD.get(ext, "lsb")


def get_encoder(method: str):
    """Return encoder instance for given method name."""
    if method == "lsb":
        from core.image.lsb import LSBEncoder
        return LSBEncoder()
    elif method == "adaptive-lsb":
        from core.image.adaptive import AdaptiveLSBEncoder
        return AdaptiveLSBEncoder()
    elif method == "dct":
        from core.image.dct import DCTEncoder
        return DCTEncoder()
    elif method == "video-dct":
        from core.video.dct import VideoDCTEncoder
        return VideoDCTEncoder()
    elif method == "video-motion":
        from core.video.motion import VideoMotionEncoder
        return VideoMotionEncoder()
    elif method == "alpha":
        from core.image.alpha import AlphaEncoder
        return AlphaEncoder()
    elif method == "palette":
        from core.image.palette import PaletteEncoder
        return PaletteEncoder()
    elif method == "fingerprint-lsb":
        from core.image.fingerprint import FingerprintEncoder
        return FingerprintEncoder()
    elif method == "audio-lsb":
        from core.audio.lsb import AudioLSBEncoder
        return AudioLSBEncoder()
    elif method == "phase":
        from core.audio.phase import PhaseEncoder
        return PhaseEncoder()
    elif method == "spectrogram":
        from core.audio.spectrogram import SpectrogramEncoder
        return SpectrogramEncoder()
    elif method == "unicode":
        from core.document.unicode_ws import UnicodeWSEncoder
        return UnicodeWSEncoder()
    elif method == "linguistic":
        from core.document.linguistic import LinguisticEncoder
        return LinguisticEncoder()
    elif method == "pdf":
        from core.document.pdf import PDFEncoder
        return PDFEncoder()
    elif method in ("docx", "xlsx", "office"):
        from core.document.office import OfficeEncoder
        return OfficeEncoder()
    elif method == "elf":
        from core.binary.elf import ELFEncoder
        return ELFEncoder()
    elif method == "pe":
        from core.binary.pe import PEEncoder
        return PEEncoder()
    elif method == "tcp-covert":
        from core.network.tcp import TCPCovertEncoder
        return TCPCovertEncoder()
    elif method == "timing-covert":
        from core.network.timing import TimingCovertEncoder
        return TimingCovertEncoder()
    else:
        raise ValueError(f"Unknown method: {method}")


def get_output_path(carrier_path: str, output: str | None, suffix: str = "_stego") -> Path:
    p = Path(carrier_path)
    if output:
        return Path(output)
    return p.with_stem(p.stem + suffix)


def _is_image_ext(ext: str) -> bool:
    return ext.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"}


def _is_audio_ext(ext: str) -> bool:
    return ext.lower() in {".wav", ".flac", ".mp3", ".ogg"}


def _is_video_ext(ext: str) -> bool:
    return ext.lower() in {".mp4", ".webm"}


def _is_document_ext(ext: str) -> bool:
    return ext.lower() in {".txt", ".pdf", ".docx", ".xlsx"}


def _is_binary_ext(ext: str) -> bool:
    return ext.lower() in {".elf", ".exe", ".dll", ".bin"}


def _resize_carrier_if_needed(carrier_bytes: bytes, ext: str, max_dim: int) -> tuple[bytes, tuple[int, int] | None, tuple[int, int] | None]:
    if not _is_image_ext(ext) or max_dim <= 0:
        return carrier_bytes, None, None

    from PIL import Image
    import io

    img = Image.open(io.BytesIO(carrier_bytes))
    if max(img.size) <= max_dim:
        return carrier_bytes, img.size, img.size

    ratio = max_dim / float(max(img.size))
    resized = (max(1, int(img.size[0] * ratio)), max(1, int(img.size[1] * ratio)))
    out = img.convert("RGB").resize(resized, Image.LANCZOS)

    buf = io.BytesIO()
    if ext.lower() in (".jpg", ".jpeg"):
        out.save(buf, format="JPEG", quality=95, subsampling=0)
    elif ext.lower() == ".webp":
        out.save(buf, format="WEBP", lossless=True)
    elif ext.lower() == ".bmp":
        out.save(buf, format="BMP")
    else:
        out.save(buf, format="PNG")
    return buf.getvalue(), img.size, resized


# ── Core operation helpers ────────────────────────────────────────────────────

def op_encode(
    carrier: str,
    payload: str,
    key: str | None,
    output: str | None,
    method: str | None,
    depth: int,
    decoy: str | None,
    decoy_key: str | None,
    wet_paper: bool,
    target: str | None,
    test_survival: bool,
    preserve_fingerprint: bool,
    cover: str | None,
    topic: str | None,
    llm_model: str | None,
    json_mode: bool,
    target_ip: str | None = None,
    target_port: int | None = None,
    listen_ip: str | None = None,
    listen_port: int | None = None,
    channel: str | None = None,
    timing_delta: int = 50,
) -> dict:
    carrier_path = Path(cover) if cover else Path(carrier)
    payload_path = Path(payload)

    if not carrier_path.exists():
        raise IOError(f"Carrier file not found: {carrier}")
    if not payload_path.exists():
        raise IOError(f"Payload file not found: {payload}")

    carrier_bytes = carrier_path.read_bytes()
    payload_bytes = payload_path.read_bytes()

    method = method or auto_detect_method(str(carrier_path))

    # Resolve key from env var fallback before any encryption/placement logic.
    key = key or os.getenv("STEGOFORGE_KEY", "")

    profile = None
    if target:
        from detect.survival import suggest_encode_profile
        profile = suggest_encode_profile(target)
        if method is None or method == auto_detect_method(str(carrier_path)):
            method = profile.preferred_method
        wet_paper = wet_paper or profile.requires_wet_paper

    if preserve_fingerprint and method in ("lsb", "adaptive-lsb"):
        method = "fingerprint-lsb"

    encoder = get_encoder(method)

    # Encrypt payload if key provided
    from core.crypto import aes
    if decoy and decoy_key:
        if not key:
            raise ValueError("Decoy mode requires a real payload key. Pass -k / --key or set STEGOFORGE_KEY.")
        from core.crypto import decoy as decoy_mod
        decoy_payload = Path(decoy).read_bytes()
        embed_bytes = decoy_mod.encode_dual(decoy_payload, decoy_key, payload_bytes, key)
    elif key:
        embed_bytes = aes.encrypt(payload_bytes, key)
    else:
        embed_bytes = payload_bytes

    if wet_paper:
        from core.image.wetpaper import encode_wet_paper
        embed_bytes = encode_wet_paper(embed_bytes)

    ext = carrier_path.suffix.lower()
    resized_from = resized_to = None
    if profile and _is_image_ext(ext):
        carrier_bytes, resized_from, resized_to = _resize_carrier_if_needed(
            carrier_bytes,
            ext,
            profile.max_dimension,
        )

    # Build kwargs before capacity check so audio ext is included
    kwargs = {"depth": depth, "key": key}
    if method in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
        kwargs["ext"] = ext
    if method in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(carrier_path)
    if method == "linguistic":
        kwargs["topic"] = topic
        kwargs["llm_model"] = llm_model
    if method in ("tcp-covert", "timing-covert"):
        kwargs["target_ip"] = target_ip
        kwargs["target_port"] = target_port
        kwargs["listen_ip"] = listen_ip
        kwargs["listen_port"] = listen_port
        kwargs["channel"] = channel or ("timing" if method == "timing-covert" else "ip_id")
        kwargs["timing_delta"] = timing_delta
        console.print(
            f"[{C_WARN}]Legal notice:[/{C_WARN}] covert network channels must only be used on systems you own or are explicitly authorized to test."
        )
    if method == "fingerprint-lsb" and not json_mode:
        last_progress = {"pct": -1}

        def _progress(done: int, total: int):
            pct = int((done / max(1, total)) * 100)
            if pct >= last_progress["pct"] + 10 or pct == 100:
                last_progress["pct"] = pct
                console.print(f"[{C_INFO}]Fingerprint-preserving embed progress: {pct}%[/{C_INFO}]")

        kwargs["progress_callback"] = _progress

    cap_kwargs = {k: v for k, v in kwargs.items() if k != "key"}  # capacity doesn't need key
    cap = encoder.capacity(carrier_bytes, **cap_kwargs)
    if len(embed_bytes) > cap:
        # Build smart suggestions
        suggestions = []
        if depth < 4 and _is_image_ext(ext) or _is_audio_ext(ext):
            needed_depth = 1
            for d in range(depth + 1, 5):
                test_cap = encoder.capacity(carrier_bytes, depth=d, **{k: v for k, v in cap_kwargs.items() if k != "depth"})
                if test_cap >= len(embed_bytes):
                    needed_depth = d
                    break
            if needed_depth > depth:
                suggestions.append(f"--depth {needed_depth} (gives ~{encoder.capacity(carrier_bytes, depth=needed_depth, **{k: v for k, v in cap_kwargs.items() if k != 'depth'}):,} bytes)")
        if method not in ("adaptive-lsb",) and _is_image_ext(ext):
            suggestions.append("--method adaptive-lsb (higher effective capacity + better stealth)")
        budget_needed = len(embed_bytes) - cap
        suggestions.append(f"use a larger carrier (need at least {budget_needed:,} more bytes of capacity)")
        raw_payload_size = len(payload_bytes)
        if len(embed_bytes) > 0:
            overhead_ratio = len(embed_bytes) / raw_payload_size if raw_payload_size else 1
            if raw_payload_size > 256:
                compressed_est = int(raw_payload_size * 0.6)
                suggestions.append(f"compress your payload first (e.g. zip — was {raw_payload_size:,} bytes, ~{compressed_est:,} compressed)")
        raise ValueError(
            f"Encrypted payload too large: {len(embed_bytes):,} bytes, "
            f"method '{method}' capacity at depth={depth}: {cap:,} bytes.\n"
            f"  Needed: {len(embed_bytes):,} B  |  Available: {cap:,} B  |  Gap: {len(embed_bytes)-cap:,} B\n"
            f"  Suggestions:\n" + "\n".join(f"    • {s}" for s in suggestions)
        )

    stego_bytes = encoder.encode(carrier_bytes, embed_bytes, **kwargs)

    # Save output
    out_path = get_output_path(carrier, output)
    out_path.write_bytes(stego_bytes)

    result = {
        "status": "success",
        "method": method,
        "carrier": str(carrier_path),
        "payload_size": len(payload_bytes),
        "encrypted_size": len(embed_bytes),
        "capacity": cap,
        "output": str(out_path),
        "depth": depth,
        "decoy_mode": bool(decoy and decoy_key),
        "wet_paper": wet_paper,
        "preserve_fingerprint": preserve_fingerprint,
    }

    if profile:
        result["target_profile"] = {
            "platform": profile.name,
            "notes": profile.notes,
            "requires_wet_paper": profile.requires_wet_paper,
        }
    if resized_from and resized_to and resized_from != resized_to:
        result["resized"] = {"from": resized_from, "to": resized_to}

    if test_survival and profile:
        from detect.survival import simulate_platform_pipeline
        from core.crypto import aes as aes_mod
        from core.crypto import decoy as decoy_mod
        from core.image.wetpaper import decode_wet_paper, is_wet_paper_blob

        sim_bytes, sim_meta = simulate_platform_pipeline(stego_bytes, out_path.name, profile)
        survived = False
        corrected = 0
        sim_error = None
        try:
            sim_raw = encoder.decode(sim_bytes, **kwargs)
            if wet_paper or is_wet_paper_blob(sim_raw):
                sim_raw, corrected, _ = decode_wet_paper(sim_raw)
            if decoy and decoy_key:
                try:
                    decoy_mod.decode_dual(sim_raw, key)
                except ValueError:
                    aes_mod.decrypt(sim_raw, key)
            else:
                aes_mod.decrypt(sim_raw, key)
            survived = True
        except Exception as exc:
            sim_error = str(exc)

        result["survival_test"] = {
            "target": profile.name,
            "survived": survived,
            "corrected_bits": corrected,
            "simulation": sim_meta,
            "error": sim_error,
        }

    return result


def _guess_payload_ext(data: bytes) -> str:
    if len(data) >= 12 and data[4:8] == b"ftyp": return ".mp4"
    if data[:4] == b"PK\x03\x04": return ".zip"
    if data[:4] == b"SFRG": return ".sfrg"
    magics = [
        (b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"GIF8", ".gif"),
        (b"BM", ".bmp"), (b"II*\x00", ".tiff"), (b"MM\x00*", ".tiff"),
        (b"RIFF", ".wav"), (b"ID3", ".mp3"), (b"\xff\xfb", ".mp3"),
        (b"fLaC", ".flac"), (b"OggS", ".ogg"), (b"%PDF", ".pdf"),
        (b"\x7fELF", ".elf"), (b"MZ", ".exe"), (b"{\n", ".json")
    ]
    for magic, ext in magics:
        if data.startswith(magic): return ext
    try:
        text = data[:512].decode("utf-8")
        if text and sum(1 for c in text if c.isprintable() or c in "\n\r\t") / len(text) > 0.85:
            return ".txt"
    except UnicodeDecodeError: pass
    return ".bin"


def op_decode(
    file: str,
    key: str | None,
    output: str | None,
    method: str | None,
    wet_paper: bool,
    json_mode: bool,
    target_ip: str | None = None,
    target_port: int | None = None,
    listen_ip: str | None = None,
    listen_port: int | None = None,
    channel: str | None = None,
    timing_delta: int = 50,
) -> dict:
    file_path = Path(file)
    if not file_path.exists():
        raise IOError(f"File not found: {file}")

    stego_bytes = file_path.read_bytes()
    # Resolve key from env var fallback
    key = key or os.getenv("STEGOFORGE_KEY", "")
    ext = file_path.suffix.lower()
    methods_to_try = [method] if method else []
    if not methods_to_try:
        suggested = auto_detect_method(file)
        if suggested in ("audio-lsb", "phase", "spectrogram"):
            methods_to_try = ["audio-lsb", "phase", "spectrogram"]
        elif suggested in ("video-dct", "video-motion"):
            methods_to_try = ["video-dct", "video-motion"]
        elif suggested in ("lsb", "adaptive-lsb", "dct", "alpha", "palette", "fingerprint-lsb"):
            methods_to_try = ["adaptive-lsb", "lsb", "fingerprint-lsb", "dct", "alpha", "palette"]
        elif suggested in ("elf", "pe"):
            methods_to_try = ["elf", "pe"]
        else:
            methods_to_try = [suggested]

    from core.crypto import aes, decoy as decoy_mod
    from core.image.wetpaper import decode_wet_paper, is_wet_paper_blob

    payload = None
    last_error = None

    for try_method in methods_to_try:
        if try_method == "sfrg":
            if not key:
                # Keyless decode for .sfrg means "extract as-is".
                payload = stego_bytes
                method = "sfrg"
                wet_paper = False
                wet_corrected_bits = 0
                break
            try:
                payload = decoy_mod.decode_dual(stego_bytes, key)
                method = "sfrg"
                wet_paper = False
                wet_corrected_bits = 0
                break
            except ValueError:
                try:
                    payload = aes.decrypt(stego_bytes, key)
                    method = "sfrg"
                    wet_paper = False
                    wet_corrected_bits = 0
                    break
                except ValueError as e:
                    last_error = str(e)
            continue

        encoder = get_encoder(try_method)
        kwargs = {"key": key}
        if try_method in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
            kwargs["ext"] = ext
        if try_method in ("docx", "xlsx", "office"):
            kwargs["filename"] = str(file_path)
        if try_method in ("tcp-covert", "timing-covert"):
            kwargs["target_ip"] = target_ip
            kwargs["target_port"] = target_port
            kwargs["listen_ip"] = listen_ip
            kwargs["listen_port"] = listen_port
            kwargs["channel"] = channel
            kwargs["timing_delta"] = timing_delta
            console.print(
                f"[{C_WARN}]Legal notice:[/{C_WARN}] covert network channels must only be used on systems you own or are explicitly authorized to test."
            )

        depth_methods = {"lsb", "adaptive-lsb", "fingerprint-lsb", "audio-lsb"}
        depths = [1, 2, 3, 4] if try_method in depth_methods else [1]

        for depth in depths:
            try:
                kwargs["depth"] = depth
                raw_bytes = encoder.decode(stego_bytes, **kwargs)

                corrected_bits = 0
                wet_used = False
                if wet_paper or is_wet_paper_blob(raw_bytes):
                    raw_bytes, corrected_bits, wet_used = decode_wet_paper(raw_bytes)

                if not key:
                    # For keyless decode, return extracted bytes directly (encrypted or plaintext).
                    method = try_method
                    payload = raw_bytes
                    wet_paper = wet_used
                    wet_corrected_bits = corrected_bits
                    break

                try:
                    payload = decoy_mod.decode_dual(raw_bytes, key)
                    method = try_method
                    wet_paper = wet_used
                    wet_corrected_bits = corrected_bits
                    break
                except ValueError:
                    try:
                        payload = aes.decrypt(raw_bytes, key)
                        method = try_method
                        wet_paper = wet_used
                        wet_corrected_bits = corrected_bits
                        break
                    except ValueError:
                        pass
            except ValueError as e:
                last_error = str(e)
                payload = None

        if payload is not None:
            break

    if payload is None:
        raise ValueError(f"Failed to decode payload: wrong key, wrong method, or corrupted file. Last error: {last_error}")

    # Save output
    if output:
        out_path = Path(output)
    else:
        stem = file_path.stem.replace("_stego", "")
        detected_ext = _guess_payload_ext(payload)
        out_path = file_path.with_name(f"{stem}_decoded{detected_ext}")

    out_path.write_bytes(payload)

    result = {
        "status": "success",
        "method": method,
        "file": str(file_path),
        "payload_size": len(payload),
        "output": str(out_path),
        "wet_paper": bool(wet_paper),
        "wet_corrected_bits": int(locals().get("wet_corrected_bits", 0)),
    }
    return result


def op_detect(
    file: str,
    chi2: bool,
    rs: bool,
    exif: bool,
    blind: bool,
    ml: bool,
    fingerprint: bool,
    binary: bool,
    all_detectors: bool,
    json_mode: bool,
) -> dict:
    file_path = Path(file)
    if not file_path.exists():
        raise IOError(f"File not found: {file}")

    file_bytes = file_path.read_bytes()
    filename = file_path.name
    ext = file_path.suffix.lower()
    results = []

    is_image = _is_image_ext(ext)
    is_audio = _is_audio_ext(ext)
    is_video = _is_video_ext(ext)
    is_document = _is_document_ext(ext)
    is_pdf = ext == ".pdf"
    is_binary = _is_binary_ext(ext) or file_bytes.startswith(b"\x7fELF") or file_bytes.startswith(b"MZ")
    any_requested = any([chi2, rs, exif, blind, ml, fingerprint, binary, all_detectors])

    if (chi2 or all_detectors) and is_image:
        from detect.chi2 import Chi2Detector
        results.append(Chi2Detector().analyze(file_bytes, filename))
    if (rs or all_detectors) and is_image:
        from detect.rs import RSDetector
        results.append(RSDetector().analyze(file_bytes, filename))
    if exif or all_detectors:
        from detect.exif import EXIFDetector
        results.append(EXIFDetector().analyze(file_bytes, filename))
    if blind or all_detectors:
        if is_video:
            results.append(_VideoAudioBlindDetector().analyze(file_bytes, filename))
        else:
            from detect.blind import BlindExtractor
            results.append(BlindExtractor().analyze(file_bytes, filename))
    if (fingerprint or all_detectors) and is_image:
        from detect.fingerprint import FingerprintDetector
        results.append(FingerprintDetector().analyze(file_bytes, filename))
    if (binary or all_detectors) and is_binary:
        from detect.binary import BinaryDetector
        results.append(BinaryDetector().analyze(file_bytes, filename))
    if (ml or all_detectors) and is_image:
        from detect.ml_steganalysis import MLSteganalysisDetector
        classical = {
            "chi2": next((r.confidence for r in results if r.method == "chi2"), 0.0),
            "rs": next((r.confidence for r in results if r.method == "rs"), 0.0),
        }
        results.append(MLSteganalysisDetector().analyze(file_bytes, filename, classical=classical))
    if (all_detectors or any_requested) and is_audio:
        from detect.audio_anomaly import AudioAnomalyDetector
        results.append(AudioAnomalyDetector().analyze(file_bytes, filename))
    if (all_detectors or any_requested) and is_pdf:
        from detect.pdf_anomaly import PDFAnomalyDetector
        results.append(PDFAnomalyDetector().analyze(file_bytes, filename))
    if (all_detectors or any_requested) and is_document and not is_pdf:
        from detect.document_anomaly import DocumentAnomalyDetector
        results.append(DocumentAnomalyDetector().analyze(file_bytes, filename))
    if (all_detectors or any_requested) and is_video:
        from detect.video_anomaly import VideoAnomalyDetector
        results.append(VideoAnomalyDetector().analyze(file_bytes, filename))

    if not results:
        # Default: run all applicable detectors for the file type
        from detect.exif import EXIFDetector
        from detect.blind import BlindExtractor
        results = [EXIFDetector().analyze(file_bytes, filename)]
        if is_video:
            results.append(_VideoAudioBlindDetector().analyze(file_bytes, filename))
        else:
            results.append(BlindExtractor().analyze(file_bytes, filename))
        if is_image:
            from detect.chi2 import Chi2Detector
            from detect.rs import RSDetector
            from detect.fingerprint import FingerprintDetector
            from detect.ml_steganalysis import MLSteganalysisDetector

            chi2_r = Chi2Detector().analyze(file_bytes, filename)
            rs_r = RSDetector().analyze(file_bytes, filename)
            results.extend([chi2_r, rs_r, FingerprintDetector().analyze(file_bytes, filename)])
            results.append(MLSteganalysisDetector().analyze(
                file_bytes,
                filename,
                classical={"chi2": chi2_r.confidence, "rs": rs_r.confidence},
            ))
        if is_binary:
            from detect.binary import BinaryDetector
            results.append(BinaryDetector().analyze(file_bytes, filename))
        if is_audio:
            from detect.audio_anomaly import AudioAnomalyDetector
            results.append(AudioAnomalyDetector().analyze(file_bytes, filename))
        if is_pdf:
            from detect.pdf_anomaly import PDFAnomalyDetector
            results.append(PDFAnomalyDetector().analyze(file_bytes, filename))
        if is_document and not is_pdf:
            from detect.document_anomaly import DocumentAnomalyDetector
            results.append(DocumentAnomalyDetector().analyze(file_bytes, filename))
        if is_video:
            from detect.video_anomaly import VideoAnomalyDetector
            results.append(VideoAnomalyDetector().analyze(file_bytes, filename))

    return {
        "status": "success",
        "file": str(file_path),
        "detectors_run": len(results),
        "results": [_result_to_dict(r) for r in results],
    }


def op_ctf(file: str, json_mode: bool) -> dict:
    """Run all detectors and provide a comprehensive CTF-style report."""
    file_path = Path(file)
    if not file_path.exists():
        raise IOError(f"File not found: {file}")

    file_bytes = file_path.read_bytes()
    filename = file_path.name
    file_size = len(file_bytes)
    ext = file_path.suffix.lower()

    from detect.exif import EXIFDetector
    from detect.blind import BlindExtractor

    is_image = _is_image_ext(ext)
    is_audio = _is_audio_ext(ext)
    is_video = _is_video_ext(ext)
    is_binary = _is_binary_ext(ext) or file_bytes.startswith(b"\x7fELF") or file_bytes.startswith(b"MZ")

    detectors = []
    if is_image:
        from detect.chi2 import Chi2Detector
        from detect.rs import RSDetector
        from detect.fingerprint import FingerprintDetector

        detectors.extend([Chi2Detector(), RSDetector(), FingerprintDetector()])
    else:
        detectors.extend([
            _SkippedDetector("chi2", "Image-only chi-square detector skipped for this file type"),
            _SkippedDetector("rs", "Image-only RS detector skipped for this file type"),
        ])

    if is_video:
        detectors.extend([EXIFDetector(), _VideoAudioBlindDetector()])
    else:
        detectors.extend([EXIFDetector(), BlindExtractor()])

    if is_audio:
        from detect.audio_anomaly import AudioAnomalyDetector
        detectors.append(AudioAnomalyDetector())
    if ext == ".pdf":
        from detect.pdf_anomaly import PDFAnomalyDetector
        detectors.append(PDFAnomalyDetector())
    if _is_document_ext(ext) and ext != ".pdf":
        from detect.document_anomaly import DocumentAnomalyDetector
        detectors.append(DocumentAnomalyDetector())

    if is_image:
        from detect.ml_steganalysis import MLSteganalysisDetector
        detectors.append(MLSteganalysisDetector())
    if is_binary:
        from detect.binary import BinaryDetector
        detectors.append(BinaryDetector())
    if is_video:
        from detect.video_anomaly import VideoAnomalyDetector
        detectors.append(VideoAnomalyDetector())

    results = []
    for det in detectors:
        if getattr(det, "name", "") == "ml":
            chi2_conf = next((r.confidence for r in results if r.method == "chi2"), 0.0)
            rs_conf = next((r.confidence for r in results if r.method == "rs"), 0.0)
            results.append(det.analyze(file_bytes, filename, classical={"chi2": chi2_conf, "rs": rs_conf}))
        else:
            results.append(det.analyze(file_bytes, filename))

    # Save extracted payloads from any successful keyless extraction
    saved_files = []
    for idx, r in enumerate(results, start=1):
        if r.extracted_payload:
            method_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", r.method or f"detector{idx}")
            save_path = file_path.parent / f"extracted_{file_path.stem}_{idx:02d}_{method_slug}.bin"
            save_path.write_bytes(r.extracted_payload)
            saved_files.append(str(save_path))

    overall_confidence = max((r.confidence for r in results), default=0.0)
    any_detected = any(r.detected for r in results)

    ctf_notes = []
    if is_image:
        chi2_r = next((r for r in results if r.method == "chi2"), None)
        rs_r = next((r for r in results if r.method == "rs"), None)
        if chi2_r and rs_r and chi2_r.confidence < 0.3 and rs_r.confidence < 0.3:
            ctf_notes.append(
                "Clean chi-square/RS scores do not rule out adaptive embedding; run ML analysis when available."
            )
    if is_audio:
        ctf_notes.append("Audio file detected: image-only detectors were labeled SKIPPED and audio anomaly scan was included.")
    if is_video:
        ctf_notes.append("Video file detected: chi-square/RS are skipped and video anomaly scan is included.")
    if is_binary:
        ctf_notes.append("Binary file detected: binary slack/entropy analysis included.")
    if ext == ".pdf":
        ctf_notes.append("PDF file detected: PDF structural anomaly scan included.")
    if _is_document_ext(ext) and ext != ".pdf":
        ctf_notes.append("Document file detected: Office/text anomaly scan included.")

    return {
        "status": "success",
        "file": str(file_path),
        "file_size": file_size,
        "overall_verdict": "STEGO DETECTED" if any_detected else "CLEAN",
        "overall_confidence": round(overall_confidence, 4),
        "results": [_result_to_dict(r) for r in results],
        "saved_payloads": saved_files,
        "notes": ctf_notes,
    }


def op_capacity(carrier: str, method: str | None, depth: int) -> dict:
    carrier_path = Path(carrier)
    if not carrier_path.exists():
        raise IOError(f"Carrier file not found: {carrier}")

    carrier_bytes = carrier_path.read_bytes()
    method = method or auto_detect_method(carrier)
    encoder = get_encoder(method)

    ext = carrier_path.suffix.lower()
    kwargs = {"depth": depth}
    if method in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
        kwargs["ext"] = ext
    if method in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(carrier_path)

    cap = encoder.capacity(carrier_bytes, **kwargs)

    result = {
        "status": "success",
        "carrier": str(carrier_path),
        "method": method,
        "depth": depth,
        "capacity_bytes": cap,
        "capacity_kb": round(cap / 1024, 2),
        "capacity_mb": round(cap / (1024 * 1024), 4),
        "stealth_score": STEALTH_SCORES.get(method, 0),
    }

    if method == "dct":
        try:
            jnd = encoder.jnd_safe_capacity(carrier_bytes)
            result["jnd_safe_dct_capacity"] = {
                "bytes": jnd,
                "kb": round(jnd / 1024, 2),
                "note": "JND-safe DCT capacity estimates perceptually conservative embedding budget",
            }
        except Exception:
            pass

    if method in ("video-dct", "video-motion"):
        try:
            import av  # type: ignore
            import tempfile
            from pathlib import Path as _P

            with tempfile.NamedTemporaryFile(suffix=ext or ".mp4", delete=False) as tmp:
                tmp.write(carrier_bytes)
                tmp.flush()
                path = tmp.name
            container = av.open(path)
            stream = container.streams.video[0]
            frame_count = 0
            keyframes = 0
            for frame in container.decode(video=0):
                frame_count += 1
                if getattr(frame, "key_frame", False):
                    keyframes += 1
            container.close()
            _P(path).unlink(missing_ok=True)
            duration_sec = float(stream.duration * float(stream.time_base)) if stream.duration else 0.0
            result["video_context"] = {
                "duration_seconds": round(duration_sec, 3),
                "frames": frame_count,
                "keyframes": keyframes,
                "capacity_note": f"up to {round(cap / 1024, 2)} KB across {keyframes} keyframes",
            }
        except Exception:
            pass

    return result


def op_diff(carrier: str, stego: str, save_heatmap: str | None = None) -> dict:
    """Compare an original carrier against its stego version byte/pixel-by-pixel."""
    carrier_path = Path(carrier)
    stego_path   = Path(stego)
    for p in (carrier_path, stego_path):
        if not p.exists():
            raise IOError(f"File not found: {p}")

    ext = carrier_path.suffix.lower()
    result: dict = {"carrier": str(carrier_path), "stego": str(stego_path)}

    if _is_image_ext(ext):
        from PIL import Image
        import numpy as np

        img_a = Image.open(carrier_path).convert("RGB")
        img_b = Image.open(stego_path).convert("RGB")
        if img_a.size != img_b.size:
            img_b = img_b.resize(img_a.size, Image.LANCZOS)

        arr_a = np.array(img_a, dtype=np.int16)
        arr_b = np.array(img_b, dtype=np.int16)
        diff  = np.abs(arr_a - arr_b)

        changed_pixels = int(np.any(diff > 0, axis=2).sum())
        total_pixels   = img_a.size[0] * img_a.size[1]
        max_delta      = int(diff.max())
        mean_delta     = float(diff.mean())

        result.update({
            "type": "image",
            "dimensions": list(img_a.size),
            "total_pixels": total_pixels,
            "changed_pixels": changed_pixels,
            "changed_percent": round(changed_pixels / total_pixels * 100, 4),
            "max_delta": max_delta,
            "mean_delta": round(mean_delta, 4),
            "heatmap": None,
        })

        # Build amplified heatmap (bright = changed pixel, dark = unchanged)
        amp = np.clip(diff.max(axis=2).astype(np.float32) * 20, 0, 255).astype(np.uint8)
        heat_img = Image.fromarray(amp, mode="L").convert("RGB")
        heat_w = min(img_a.width, 800)
        heat_h = min(img_a.height, 800)
        heat_img = heat_img.resize((heat_w, heat_h), Image.NEAREST)
        out_heat = save_heatmap or str(
            carrier_path.with_stem(carrier_path.stem + "_diff_heatmap").with_suffix(".png")
        )
        heat_img.save(out_heat)
        result["heatmap"] = out_heat

    elif _is_audio_ext(ext):
        data_a = carrier_path.read_bytes()
        data_b = stego_path.read_bytes()
        min_len = min(len(data_a), len(data_b))
        diff_bytes = sum(1 for x, y in zip(data_a[:min_len], data_b[:min_len]) if x != y)
        diff_percent = round(diff_bytes / max(min_len, 1) * 100, 4)
        result.update({
            "type": "audio",
            "size_original": len(data_a),
            "size_stego": len(data_b),
            "differing_bytes": diff_bytes,
            "differing_percent": diff_percent,
            # Compatibility aliases used by the web UI.
            "changed_bytes": diff_bytes,
            "changed_percent": diff_percent,
        })
    else:
        data_a = carrier_path.read_bytes()
        data_b = stego_path.read_bytes()
        min_len = min(len(data_a), len(data_b))
        diff_bytes = sum(1 for x, y in zip(data_a[:min_len], data_b[:min_len]) if x != y)
        diff_percent = round(diff_bytes / max(min_len, 1) * 100, 4)
        result.update({
            "type": "binary",
            "size_original": len(data_a),
            "size_stego": len(data_b),
            "differing_bytes": diff_bytes,
            "differing_percent": diff_percent,
            # Compatibility aliases used by the web UI.
            "changed_bytes": diff_bytes,
            "changed_percent": diff_percent,
        })

    return result


def op_batch_encode(
    batch_dir: str,
    payload: str,
    key: str,
    output_dir: str | None,
    method: str | None,
    depth: int,
    wet_paper: bool,
) -> dict:
    """Encode a payload into every compatible carrier file in a directory."""
    key = key or os.getenv("STEGOFORGE_KEY", "")
    if not key:
        raise ValueError("Encryption key required. Pass -k / --key or set STEGOFORGE_KEY.")

    bd = Path(batch_dir)
    if not bd.is_dir():
        raise IOError(f"Batch directory not found: {batch_dir}")
    if not Path(payload).exists():
        raise IOError(f"Payload file not found: {payload}")

    out_dir = Path(output_dir) if output_dir else bd
    out_dir.mkdir(parents=True, exist_ok=True)

    # Supported carrier extensions minus binary/network (require special args)
    skip = {".elf", ".exe", ".dll", ".bin"}
    carriers = sorted(
        f for f in bd.rglob("*")
        if f.is_file() and f.suffix.lower() in EXT_TO_METHOD and f.suffix.lower() not in skip
    )

    rows: list[dict] = []
    passed = 0
    failed = 0

    for cf in carriers:
        auto_out = out_dir / (cf.stem + "_stego" + cf.suffix)
        try:
            r = op_encode(
                str(cf), payload, key, str(auto_out),
                method, depth,
                None, None, wet_paper,
                None, False, False,
                None, None, None, False,
            )
            rows.append({
                "file": cf.name,
                "status": "success",
                "method": r["method"],
                "output": r["output"],
                "payload_size": r["payload_size"],
                "capacity": r["capacity"],
            })
            passed += 1
        except Exception as exc:
            rows.append({"file": cf.name, "status": "error", "error": str(exc)})
            failed += 1

    return {
        "batch_dir": str(bd),
        "payload": payload,
        "total": len(carriers),
        "passed": passed,
        "failed": failed,
        "rows": rows,
    }


class _SkippedDetector:
    def __init__(self, name: str, reason: str):
        self.name = name
        self._reason = reason

    def analyze(self, file_bytes: bytes, filename: str = ""):
        from detect.base import DetectionResult
        return DetectionResult(
            method=self.name,
            detected=False,
            confidence=0.0,
            details={"skipped": True, "interpretation": self._reason},
        )


class _VideoAudioBlindDetector:
    name = "blind-audio"

    def analyze(self, file_bytes: bytes, filename: str = ""):
        import subprocess
        import tempfile

        from detect.blind import BlindExtractor
        from detect.base import DetectionResult
        from core.audio._convert import _ffmpeg_cmd

        ffmpeg_cmd = _ffmpeg_cmd()
        if not ffmpeg_cmd:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={
                    "skipped": True,
                    "interpretation": "ffmpeg unavailable for video audio-track extraction",
                },
            )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as in_tmp:
            in_tmp.write(file_bytes)
            in_tmp.flush()
            in_path = in_tmp.name

        try:
            proc = subprocess.run(
                [
                    ffmpeg_cmd,
                    "-y",
                    "-i",
                    in_path,
                    "-vn",
                    "-f",
                    "wav",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0 or not proc.stdout:
                return DetectionResult(
                    method=self.name,
                    detected=False,
                    confidence=0.0,
                    details={
                        "skipped": True,
                        "interpretation": "Audio track extraction failed for video blind analysis",
                    },
                )

            r = BlindExtractor().analyze(proc.stdout, "video_audio.wav")
            r.method = self.name
            return r
        finally:
            Path(in_path).unlink(missing_ok=True)


def _result_to_dict(result) -> dict:
    return {
        "method": result.method,
        "detected": result.detected,
        "confidence": result.confidence,
        "details": result.details,
        "findings": getattr(result, "findings", []),
        "has_payload": result.extracted_payload is not None,
    }


# ── Rich output helpers ───────────────────────────────────────────────────────

def print_encode_result(result: dict):
    extra_lines = []
    if result.get("wet_paper"):
        extra_lines.append("  [dim]Wet Paper :[/dim]  Enabled (Reed-Solomon redundancy active)")
    if result.get("preserve_fingerprint"):
        extra_lines.append("  [dim]Fingerprint:[/dim]  Preservation mode active (slightly reduced effective capacity)")
    if result.get("target_profile"):
        t = result["target_profile"]
        extra_lines.append(f"  [dim]Target    :[/dim]  {t['platform']} ({t['notes']})")
    if result.get("resized"):
        r = result["resized"]
        extra_lines.append(f"  [dim]Resized   :[/dim]  {r['from']} -> {r['to']}")
    if result.get("survival_test"):
        st = result["survival_test"]
        status = "PASS" if st.get("survived") else "FAIL"
        extra_lines.append(
            f"  [dim]Survival  :[/dim]  {status} ({st.get('target')}, corrected bits={st.get('corrected_bits', 0)})"
        )

    panel_content = (
        f"[{C_SUCCESS}]✓ Payload successfully embedded[/{C_SUCCESS}]\n\n"
        f"  [dim]Method    :[/dim]  [{C_ACCENT}]{result['method'].upper()}[/{C_ACCENT}]\n"
        f"  [dim]Carrier   :[/dim]  {result['carrier']}\n"
        f"  [dim]Output    :[/dim]  [{C_SUCCESS}]{result['output']}[/{C_SUCCESS}]\n"
        f"  [dim]Payload   :[/dim]  {result['payload_size']:,} bytes → "
        f"{result['encrypted_size']:,} bytes encrypted\n"
        f"  [dim]Capacity  :[/dim]  {result['capacity']:,} bytes available\n"
        f"  [dim]Depth     :[/dim]  {result['depth']} bit(s)\n"
        f"  [dim]Decoy Mode:[/dim]  {'Enabled ✓' if result['decoy_mode'] else 'Disabled'}"
    )
    if extra_lines:
        panel_content += "\n" + "\n".join(extra_lines)
    console.print(Panel(panel_content, title=f"[{C_TITLE}]StegoForge — Encode Result[/{C_TITLE}]",
                        border_style="cyan", padding=(1, 2)))


def print_decode_result(result: dict):
    wet_line = ""
    if result.get("wet_paper"):
        wet_line = f"\n  [dim]Wet Paper :[/dim]  Enabled (corrected bits: {result.get('wet_corrected_bits', 0)})"

    panel_content = (
        f"[{C_SUCCESS}]✓ Payload successfully extracted & decrypted[/{C_SUCCESS}]\n\n"
        f"  [dim]Method    :[/dim]  [{C_ACCENT}]{result['method'].upper()}[/{C_ACCENT}]\n"
        f"  [dim]Input     :[/dim]  {result['file']}\n"
        f"  [dim]Output    :[/dim]  [{C_SUCCESS}]{result['output']}[/{C_SUCCESS}]\n"
        f"  [dim]Payload   :[/dim]  {result['payload_size']:,} bytes"
        f"{wet_line}"
    )
    console.print(Panel(panel_content, title=f"[{C_TITLE}]StegoForge — Decode Result[/{C_TITLE}]",
                        border_style="green", padding=(1, 2)))


def print_detect_results(report: dict):
    console.print(Panel(
        f"[{C_ACCENT}]File:[/{C_ACCENT}] {report['file']}\n"
        f"[{C_ACCENT}]Detectors run:[/{C_ACCENT}] {report['detectors_run']}",
        title=f"[{C_TITLE}]StegoForge — Detection Report[/{C_TITLE}]",
        border_style="blue",
    ))

    for r in report["results"]:
        _print_single_result(r)


def print_ctf_report(report: dict):
    verdict = report["overall_verdict"]
    verdict_color = C_ERROR if "DETECTED" in verdict else C_SUCCESS
    confidence_pct = int(report["overall_confidence"] * 100)

    header = (
        f"[dim]File   :[/dim] {report['file']}\n"
        f"[dim]Size   :[/dim] {report['file_size']:,} bytes\n"
        f"[{verdict_color}][dim]Verdict:[/dim] {verdict}  ({confidence_pct}% confidence)[/{verdict_color}]"
    )
    console.print(Panel(header, title=f"[{C_TITLE}]StegoForge — CTF Analysis Report[/{C_TITLE}]",
                        border_style="magenta", padding=(1, 2)))

    for r in report["results"]:
        _print_single_result(r)

    if report.get("notes"):
        console.print(f"\n[{C_WARN}]CTF Notes:[/{C_WARN}]")
        for note in report["notes"]:
            console.print(f"  - {note}")

    if report["saved_payloads"]:
        console.print(f"\n[{C_SUCCESS}]Extracted payloads saved:[/{C_SUCCESS}]")
        for path in report["saved_payloads"]:
            console.print(f"  [{C_ACCENT}]→[/{C_ACCENT}] {path}")


def print_capacity_result(result: dict):
    stealth = STEALTH_SCORES.get(result.get("method", ""), 0)
    panel_content = (
        f"  [dim]Carrier  :[/dim] {result['carrier']}\n"
        f"  [dim]Method   :[/dim] [{C_ACCENT}]{result['method'].upper()}[/{C_ACCENT}]\n"
        f"  [dim]Depth    :[/dim] {result['depth']} bit(s)\n"
        f"  [dim]Stealth  :[/dim]  {_stealth_bar(stealth)}\n\n"
        f"  [{C_SUCCESS}]Capacity:[/{C_SUCCESS}]\n"
        f"    [{C_GOLD}]{result['capacity_bytes']:>12,}[/{C_GOLD}] bytes\n"
        f"    [{C_GOLD}]{result['capacity_kb']:>12.2f}[/{C_GOLD}] KB\n"
        f"    [{C_GOLD}]{result['capacity_mb']:>12.4f}[/{C_GOLD}] MB"
    )
    if result.get("jnd_safe_dct_capacity"):
        j = result["jnd_safe_dct_capacity"]
        panel_content += (
            f"\n\n  [{C_INFO}]JND-safe DCT capacity:[/{C_INFO}]\n"
            f"    {j['bytes']:,} bytes ({j['kb']} KB)\n"
            f"    [dim]{j['note']}[/dim]"
        )
    if result.get("video_context"):
        v = result["video_context"]
        panel_content += (
            f"\n\n  [{C_INFO}]Video context:[/{C_INFO}]\n"
            f"    duration={v.get('duration_seconds')}s, frames={v.get('frames')}, keyframes={v.get('keyframes')}\n"
            f"    [dim]{v.get('capacity_note')}[/dim]"
        )

    console.print(Panel(panel_content, title=f"[{C_TITLE}]StegoForge — Capacity Check[/{C_TITLE}]",
                        border_style="yellow", padding=(1, 2)))


def print_diff_result(result: dict):
    """Pretty-print the result of op_diff."""
    kind = result.get("type", "binary")
    if kind == "image":
        chg = result["changed_pixels"]
        pct = result["changed_percent"]
        total = result["total_pixels"]
        stealth_ok = pct < 0.1
        color = C_SUCCESS if stealth_ok else (C_WARN if pct < 1.0 else C_ERROR)
        content = (
            f"  [dim]Original :[/dim] {result['carrier']}\n"
            f"  [dim]Stego    :[/dim] {result['stego']}\n"
            f"  [dim]Mode     :[/dim] {result['dimensions'][0]}×{result['dimensions'][1]} px\n\n"
            f"  [{color}]Changed pixels :[/{color}] {chg:,} / {total:,} ({pct}%)\n"
            f"  [dim]Max delta      :[/dim] {result['max_delta']} (per channel, 0-255)\n"
            f"  [dim]Mean delta     :[/dim] {result['mean_delta']:.4f}\n"
        )
        if result.get("heatmap"):
            content += f"\n  [{C_INFO}]Heatmap saved:[/{C_INFO}] {result['heatmap']}\n"
        console.print(Panel(content, title=f"[{C_TITLE}]StegoForge — Stego Diff (Image)[/{C_TITLE}]",
                            border_style="cyan", padding=(1, 2)))
    elif kind == "audio":
        content = (
            f"  [dim]Original :[/dim] {result['carrier']}\n"
            f"  [dim]Stego    :[/dim] {result['stego']}\n\n"
            f"  [dim]Differing bytes:[/dim] {result['differing_bytes']:,} "
            f"({result['differing_percent']}%)\n"
        )
        console.print(Panel(content, title=f"[{C_TITLE}]StegoForge — Stego Diff (Audio)[/{C_TITLE}]",
                            border_style="cyan", padding=(1, 2)))
    else:
        content = (
            f"  [dim]Original :[/dim] {result['carrier']}\n"
            f"  [dim]Stego    :[/dim] {result['stego']}\n\n"
            f"  [dim]Differing bytes:[/dim] {result.get('differing_bytes', 'N/A')}\n"
        )
        console.print(Panel(content, title=f"[{C_TITLE}]StegoForge — Stego Diff (Binary)[/{C_TITLE}]",
                            border_style="cyan", padding=(1, 2)))


def print_batch_result(result: dict):
    """Pretty-print the result of op_batch_encode."""
    total  = result["total"]
    passed = result["passed"]
    failed = result["failed"]

    table = Table(
        title=f"[{C_TITLE}]StegoForge — Batch Encode Results[/{C_TITLE}]",
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("File", style="dim", overflow="fold", max_width=40)
    table.add_column("Status", width=9)
    table.add_column("Method", style="cyan", width=16)
    table.add_column("Payload", width=10, justify="right")
    table.add_column("Capacity", width=10, justify="right")
    table.add_column("Output / Error", overflow="fold")

    for row in result["rows"]:
        if row["status"] == "success":
            pct = round(row["payload_size"] / max(row["capacity"], 1) * 100, 1)
            table.add_row(
                row["file"],
                f"[{C_SUCCESS}]✓ OK[/{C_SUCCESS}]",
                row["method"],
                f"{row['payload_size']:,} B",
                f"{row['capacity']:,} B",
                f"{Path(row['output']).name} ({pct}%)",
            )
        else:
            table.add_row(
                row["file"],
                f"[{C_ERROR}]✗ ERR[/{C_ERROR}]",
                "—", "—", "—",
                f"[{C_ERROR}]{row.get('error', '')[:80]}[/{C_ERROR}]",
            )

    console.print(table)
    color = C_SUCCESS if failed == 0 else C_WARN
    console.print(
        f"\n  [{color}]Batch complete:[/{color}] "
        f"{passed} encoded, {failed} failed, {total} total  "
        f"  [dim]Payload: {result['payload']}[/dim]"
    )




def _print_single_result(r: dict):
    detected = r["detected"]
    confidence_pct = int(r["confidence"] * 100)
    details = r.get("details", {})
    
    if details.get("skipped", False):
        status_icon = "[dim]⏭[/dim]"
        status_label = "[dim]SKIPPED[/dim]"
    else:
        status_icon = "[bold red]🔴[/bold red]" if detected else "[dim green]🟢[/dim green]"
        status_label = "[bold red]DETECTED[/bold red]" if detected else "[dim]CLEAN[/dim]"

    # Build confidence bar
    bar_filled = int(confidence_pct / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    bar_color = "red" if confidence_pct > 70 else "yellow" if confidence_pct > 30 else "green"

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    table.add_column("Field", style="dim", width=14)
    table.add_column("Value", width=60)

    table.add_row("Status", f"{status_icon} {status_label}")
    table.add_row("Confidence", f"[{bar_color}]{bar}[/{bar_color}] {confidence_pct}%")

    interp = details.get("interpretation", "")
    if interp:
        table.add_row("Analysis", interp)

    # Method-specific details
    if r["method"] == "chi2":
        if "p_value" in details:
            table.add_row("p-value", f"{details['p_value']:.4f}")
        if "chi2_statistic" in details:
            table.add_row("χ² stat", f"{details['chi2_statistic']:.2f}")
    elif r["method"] == "rs":
        if "estimated_payload_fraction" in details:
            pct = details["estimated_payload_fraction"] * 100
            table.add_row("Est. payload", f"~{pct:.1f}% of pixels")
    elif r["method"] == "exif":
        findings = r.get("findings", [])
        for f in findings[:5]:  # show first 5
            level = f.get("suspicion", "low")
            icon = "❗" if level == "high" else "⚠" if level == "medium" else "ℹ"
            table.add_row(f.get("field", ""), f"[dim]{icon}[/dim] {f.get('description', '')[:70]}")
    elif r["method"] in ("blind", "blind-audio"):
        if "candidates_found" in details:
            table.add_row("Candidates", str(details["candidates_found"]))
        for cand in details.get("candidates", [])[:3]:
            table.add_row(
                "→ Found",
                f"Ch={cand['channel']}, depth={cand['depth']}, "
                f"order={cand['row_order']}, {cand['payload_bytes']} bytes "
                f"[{cand.get('payload_type','?')}]"
            )

    if r.get("has_payload"):
        table.add_row("Payload", f"[{C_SUCCESS}]Extracted — check output file[/{C_SUCCESS}]")

    console.print(Panel(table, title=f"[{C_ACCENT}]{r['method'].upper()}[/{C_ACCENT}]",
                        border_style="dim", padding=(0, 1)))


# ── Interactive menu ──────────────────────────────────────────────────────────

def interactive_encode():
    """Interactive encode wizard."""
    console.print(f"\n[{C_TITLE}]── ENCODE ──────────────────────────────────────[/{C_TITLE}]")
    carrier = Prompt.ask(f"  [{C_ACCENT}]Carrier file[/{C_ACCENT}] (path)")
    payload = Prompt.ask(f"  [{C_ACCENT}]Payload file[/{C_ACCENT}] (path)")
    key = Prompt.ask(f"  [{C_ACCENT}]Encryption key[/{C_ACCENT}] (passphrase)", password=True)

    # Show method options
    console.print(f"\n  [dim]Available methods grouped by category (hybrid-first):[/dim]")
    auto_method = auto_detect_method(carrier)
    if Path(carrier).suffix.lower() in (".png", ".bmp", ".webp"):
        auto_method = "adaptive-lsb"

    method_names: list[str] = []
    index = 1
    for category, methods in _group_encode_methods():
        console.print(f"    [{C_INFO}]{category}[/{C_INFO}]")
        for m, source_category, desc in methods:
            marker = f"[{C_SUCCESS}] ✓ auto[/{C_SUCCESS}]" if m == auto_method else ""
            hybrid_note = f"[{C_GOLD}]hybrid[/{C_GOLD}] · " if category == "Hybrid" else ""
            console.print(
                f"      [{C_DIM}]{index:2}.[/{C_DIM}] "
                f"[{C_ACCENT}]{m:14}[/{C_ACCENT}] "
                f"{hybrid_note}{source_category}: {desc} {marker}"
            )
            method_names.append(m)
            index += 1

    method_input = Prompt.ask(
        f"\n  [{C_ACCENT}]Method[/{C_ACCENT}] (name or number, Enter for auto)",
        default=auto_method,
    )
    # Resolve numeric input
    if method_input.isdigit():
        idx = int(method_input) - 1
        method = method_names[idx] if 0 <= idx < len(method_names) else auto_method
    else:
        method = method_input or auto_method

    depth_str = Prompt.ask(f"  [{C_ACCENT}]Bit depth[/{C_ACCENT}] (1-4, default: 1)", default="1")
    depth = int(depth_str) if depth_str.isdigit() else 1
    output = Prompt.ask(f"  [{C_ACCENT}]Output path[/{C_ACCENT}] (Enter for auto)", default="")

    use_decoy = Confirm.ask(f"  [{C_ACCENT}]Enable decoy mode?[/{C_ACCENT}]", default=False)
    decoy = decoy_key = None
    if use_decoy:
        decoy = Prompt.ask(f"  [{C_ACCENT}]Decoy payload file[/{C_ACCENT}]")
        decoy_key = Prompt.ask(f"  [{C_ACCENT}]Decoy key[/{C_ACCENT}]", password=True)

    console.print()
    with console.status(f"[{C_INFO}]Encrypting and embedding payload...[/{C_INFO}]", spinner="dots"):
        result = op_encode(
            carrier,
            payload,
            key,
            output or None,
            method,
            depth,
            decoy,
            decoy_key,
            False,
            None,
            False,
            False,
            None,
            None,
            None,
            False,
        )
    print_encode_result(result)


def interactive_decode():
    """Interactive decode wizard."""
    console.print(f"\n[{C_TITLE}]── DECODE ──────────────────────────────────────[/{C_TITLE}]")
    file = Prompt.ask(f"  [{C_ACCENT}]Stego file[/{C_ACCENT}] (path)")
    key = Prompt.ask(f"  [{C_ACCENT}]Decryption key[/{C_ACCENT}]", password=True)
    auto_method = auto_detect_method(file)
    method_input = Prompt.ask(f"  [{C_ACCENT}]Method[/{C_ACCENT}] (Enter for auto: {auto_method})", default=auto_method)
    output = Prompt.ask(f"  [{C_ACCENT}]Output path[/{C_ACCENT}] (Enter for auto)", default="")

    console.print()
    with console.status(f"[{C_INFO}]Extracting and decrypting payload...[/{C_INFO}]", spinner="dots"):
        result = op_decode(file, key, output or None, method_input or None, False, False)
    print_decode_result(result)


def interactive_detect():
    """Interactive detect wizard."""
    console.print(f"\n[{C_TITLE}]── DETECT ──────────────────────────────────────[/{C_TITLE}]")
    file = Prompt.ask(f"  [{C_ACCENT}]File to analyze[/{C_ACCENT}] (path)")
    console.print(f"  [{C_DIM}]Detectors: chi2, rs, exif, blind, ml, fingerprint, binary, all[/{C_DIM}]")
    which = Prompt.ask(f"  [{C_ACCENT}]Detectors to run[/{C_ACCENT}]", default="all")

    chi2_flag = "chi2" in which or which == "all"
    rs_flag = "rs" in which or which == "all"
    exif_flag = "exif" in which or which == "all"
    blind_flag = "blind" in which or which == "all"
    ml_flag = "ml" in which or which == "all"
    fingerprint_flag = "fingerprint" in which or which == "all"
    binary_flag = "binary" in which or which == "all"

    console.print()
    with console.status(f"[{C_INFO}]Analyzing file...[/{C_INFO}]", spinner="dots"):
        result = op_detect(
            file,
            chi2_flag,
            rs_flag,
            exif_flag,
            blind_flag,
            ml_flag,
            fingerprint_flag,
            binary_flag,
            which == "all",
            False,
        )
    print_detect_results(result)


def interactive_ctf():
    """Interactive CTF mode."""
    console.print(f"\n[{C_TITLE}]── CTF MODE ─────────────────────────────────────[/{C_TITLE}]")
    file = Prompt.ask(f"  [{C_ACCENT}]Suspicious file[/{C_ACCENT}] (path)")
    console.print()
    with console.status(
        f"[{C_INFO}]Running all detectors on {Path(file).name}...[/{C_INFO}]", spinner="dots2"
    ):
        result = op_ctf(file, False)
    print_ctf_report(result)


def interactive_capacity():
    """Interactive capacity check."""
    console.print(f"\n[{C_TITLE}]── CAPACITY ─────────────────────────────────────[/{C_TITLE}]")
    carrier = Prompt.ask(f"  [{C_ACCENT}]Carrier file[/{C_ACCENT}]")
    method = Prompt.ask(f"  [{C_ACCENT}]Method[/{C_ACCENT}] (Enter for auto)", default="")
    depth_str = Prompt.ask(f"  [{C_ACCENT}]Bit depth[/{C_ACCENT}] (1-4)", default="1")

    depth = int(depth_str) if depth_str.isdigit() else 1
    result = op_capacity(carrier, method or None, depth)
    print_capacity_result(result)


def interactive_survive():
    """Interactive platform survivability wizard."""
    console.print(f"\n[{C_TITLE}]── PLATFORM SURVIVAL CHECK ─────────────────────[/{C_TITLE}]")
    carrier = Prompt.ask(f"  [{C_ACCENT}]Carrier file[/{C_ACCENT}]")
    payload = Prompt.ask(f"  [{C_ACCENT}]Payload file[/{C_ACCENT}]")
    key = Prompt.ask(f"  [{C_ACCENT}]Encryption key[/{C_ACCENT}]", password=True)
    target = Prompt.ask(
        f"  [{C_ACCENT}]Target platform[/{C_ACCENT}]",
        choices=["twitter", "instagram", "telegram", "discord", "whatsapp", "facebook", "tiktok", "linkedin", "reddit", "signal"],
        default="twitter",
    )
    output = Prompt.ask(f"  [{C_ACCENT}]Output path[/{C_ACCENT}] (Enter for auto)", default="")

    with console.status(f"[{C_INFO}]Encoding and simulating platform pipeline...[/{C_INFO}]", spinner="dots"):
        result = op_encode(
            carrier,
            payload,
            key,
            output or None,
            None,
            1,
            None,
            None,
            False,
            target,
            True,
            False,
            None,
            None,
            None,
            False,
        )
    print_encode_result(result)


def interactive_update():
    """Interactive update checker and downloader."""
    console.print(f"\n[{C_TITLE}]── UPDATE ──────────────────────────────────────[/{C_TITLE}]")
    try:
        with console.status(f"[{C_INFO}]Checking latest GitHub release...[/{C_INFO}]", spinner="dots"):
            probe = op_update(check_only=True, auto_apply=False)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] Update check failed: {e}")
        return

    _print_update_versions(probe)

    if not probe.get("update_available"):
        console.print(f"[{C_SUCCESS}]You are up to date.[/{C_SUCCESS}]")
        return

    console.print(f"[{C_WARN}]Update available.[/{C_WARN}] {probe.get('release_url', '')}")
    install_kind = str(probe.get("install_kind", ""))
    if install_kind != "release-binary":
        cmd = str(probe.get("manual_update_command") or "").strip()
        if install_kind == "source-checkout":
            console.print(f"[{C_INFO}]Source checkout detected. Update your clone with:[/{C_INFO}]")
        else:
            console.print(f"[{C_INFO}]Python package install detected. Update with:[/{C_INFO}]")
        if cmd:
            console.print(f"[{C_ACCENT}]{cmd}[/{C_ACCENT}]")
        return

    if not probe.get("asset_url"):
        console.print(f"[{C_WARN}]No matching asset for this platform. Open releases page above.[/{C_WARN}]")
        return

    auto_apply = bool(getattr(sys, "frozen", False)) and platform.system() != "Windows"
    action_label = "Download and apply update now" if auto_apply else "Download latest asset now"
    if not Confirm.ask(f"  [{C_ACCENT}]{action_label}?[/{C_ACCENT}]", default=True):
        return

    try:
        result = op_update(check_only=False, auto_apply=auto_apply)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] Update failed: {e}")
        return

    if result.get("applied"):
        console.print(f"[{C_SUCCESS}]Update applied successfully.[/{C_SUCCESS}]")
        console.print(f"[{C_DIM}]Restart StegoForge to run the new version.[/{C_DIM}]")
    elif result.get("downloaded_path"):
        console.print(f"[{C_SUCCESS}]Update downloaded:[/{C_SUCCESS}] {result['downloaded_path']}")
        if platform.system() == "Windows" and getattr(sys, "frozen", False):
            console.print(f"[{C_DIM}]Windows blocks replacing a running executable. Close app and replace manually.[/{C_DIM}]")
    else:
        console.print(f"[{C_WARN}]No update artifact was downloaded.[/{C_WARN}]")


def interactive_menu():
    """Main interactive menu."""
    _startup_loading_sequence()
    print_banner()

    menu_items = [
        ("[bold cyan]1[/bold cyan]", "Encode",    "Embed a secret payload in any carrier"),
        ("[bold cyan]2[/bold cyan]", "Decode",    "Extract & decrypt a hidden payload"),
        ("[bold cyan]3[/bold cyan]", "Detect",    "Analyze a file for hidden content"),
        ("[bold cyan]4[/bold cyan]", "CTF Mode",  "Run all detectors, get full forensic report"),
        ("[bold cyan]5[/bold cyan]", "Capacity",  "Check how much data a carrier can hold"),
        ("[bold cyan]6[/bold cyan]", "Web UI",    "Launch the local web interface"),
        ("[bold cyan]7[/bold cyan]", "Survival",  "Platform Survival Check"),
        ("[bold cyan]8[/bold cyan]", "Dead Drop", "Dead drop and key exchange commands"),
        ("[bold cyan]9[/bold cyan]", "Update",    "Check GitHub for newer releases and update"),
        ("[bold cyan]d[/bold cyan]", "Diff",      "Compare original vs stego — pixel heatmap"),
        ("[bold cyan]b[/bold cyan]", "Batch",     "Encode payload into every carrier in a folder"),
        ("[bold cyan]q[/bold cyan]", "Quit",      "Exit StegoForge"),
    ]

    table = Table(box=box.ROUNDED, show_header=False, border_style="cyan", padding=(0, 2))
    table.add_column("Key",  style="bold cyan",  width=4)
    table.add_column("Action", style="bold white", width=12)
    table.add_column("Description", style="dim")

    if UI_ANIMATION_ENABLED and sys.stdout.isatty():
        with Live(table, console=console, refresh_per_second=20, transient=False) as live:
            time.sleep(0.1)
            for key, action, desc in menu_items:
                table.add_row(key, action, desc)
                live.update(table)
                time.sleep(0.04)
    else:
        for key, action, desc in menu_items:
            table.add_row(key, action, desc)
        console.print(table)

    while True:
        choice = Prompt.ask(f"\n  [{C_TITLE}]Command[/{C_TITLE}]").strip().lower()

        try:
            if choice == "1" or choice == "encode":
                _menu_transition("Encode")
                interactive_encode()
            elif choice == "2" or choice == "decode":
                _menu_transition("Decode")
                interactive_decode()
            elif choice == "3" or choice == "detect":
                _menu_transition("Detect")
                interactive_detect()
            elif choice == "4" or choice == "ctf":
                _menu_transition("CTF Mode")
                interactive_ctf()
            elif choice == "5" or choice == "capacity":
                _menu_transition("Capacity")
                interactive_capacity()
            elif choice == "6" or choice == "web":
                _menu_transition("Web UI")
                console.print(f"[{C_INFO}]Starting web UI...[/{C_INFO}]")
                _launch_web()
                break
            elif choice == "7" or choice == "survival" or choice == "survive":
                _menu_transition("Survival")
                interactive_survive()
            elif choice == "8" or choice == "deadrop":
                _menu_transition("Dead Drop")
                console.print(
                    f"[{C_INFO}]Use CLI subcommands:[/{C_INFO}] "
                    "stegoforge deadrop post|check|monitor and stegoforge deadrop keyx initiate|complete"
                )
            elif choice == "9" or choice == "update":
                _menu_transition("Update")
                interactive_update()
            elif choice in ("d", "diff"):
                _menu_transition("Diff")
                carrier = Prompt.ask(f"  [{C_ACCENT}]Original (clean) carrier[/{C_ACCENT}]")
                stego   = Prompt.ask(f"  [{C_ACCENT}]Stego carrier to compare[/{C_ACCENT}]")
                with console.status(f"[{C_INFO}]Analyzing differences...[/{C_INFO}]", spinner="dots"):
                    res = op_diff(carrier, stego)
                print_diff_result(res)
            elif choice in ("b", "batch"):
                _menu_transition("Batch Encode")
                b_dir    = Prompt.ask(f"  [{C_ACCENT}]Directory of carriers[/{C_ACCENT}]")
                b_payload = Prompt.ask(f"  [{C_ACCENT}]Payload file[/{C_ACCENT}]")
                b_key    = Prompt.ask(f"  [{C_ACCENT}]Encryption key[/{C_ACCENT}]", password=True)
                b_out    = Prompt.ask(f"  [{C_ACCENT}]Output directory[/{C_ACCENT}] (Enter = same dir)", default="")
                with console.status(f"[{C_INFO}]Batch encoding...[/{C_INFO}]", spinner="dots2"):
                    res = op_batch_encode(b_dir, b_payload, b_key, b_out or None, None, 1, False)
                print_batch_result(res)
            elif choice in ("q", "quit", "exit"):
                console.print(f"[{C_DIM}]Goodbye.[/{C_DIM}]")
                raise typer.Exit()
            else:
                console.print(f"[{C_WARN}]Unknown command. Type 1-9, d, b, or q (or the command name).[/{C_WARN}]")
        except (ValueError, IOError) as e:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        except KeyboardInterrupt:
            console.print(f"\n[{C_DIM}]Cancelled.[/{C_DIM}]")

        # Prompt to continue
        if Confirm.ask(f"\n  [{C_DIM}]Return to menu?[/{C_DIM}]", default=True):
            console.print()
            console.print(table)
        else:
            break


def _launch_web(port: int = 5000):
    console.print(f"[{C_SUCCESS}]Launching Web UI at http://localhost:{port}... (Press Ctrl+C to quit)[/{C_SUCCESS}]")
    try:
        cmd_web(port, skip_banner=True)
    except KeyboardInterrupt:
        console.print(f"\n[{C_DIM}]Web UI stopped.[/{C_DIM}]")


# ── Typer commands ────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    """StegoForge — The most complete open-source steganography toolkit."""
    sysmgr.bootstrap_if_needed()
    if ctx.invoked_subcommand is None:
        interactive_menu()

@app.command("init", help="Force repair/reset of offline assets (FFmpeg, ONNX models)")
def cmd_init():
    console.print(f"[{C_INFO}]Force resolving and syncing offline assets...[/{C_INFO}]")
    sysmgr.bootstrap_if_needed(force=True)
    console.print(f"[{C_SUCCESS}]Initialization complete.[/{C_SUCCESS}]")


@app.command("update", help="Check GitHub for newer releases and update when possible")
def cmd_update(
    check_only: bool = typer.Option(False, "--check-only", help="Only check for updates"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Apply/download update without confirmation"),
):
    try:
        probe = op_update(check_only=True, auto_apply=False)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] Update check failed: {e}")
        raise typer.Exit(1)

    _print_update_versions(probe)

    if not probe.get("update_available"):
        console.print(f"[{C_SUCCESS}]You are up to date.[/{C_SUCCESS}]")
        return

    console.print(f"[{C_WARN}]Update available.[/{C_WARN}] {probe.get('release_url', '')}")
    install_kind = str(probe.get("install_kind", ""))
    if install_kind != "release-binary":
        cmd = str(probe.get("manual_update_command") or "").strip()
        if install_kind == "source-checkout":
            console.print(f"[{C_INFO}]Source checkout detected. Update your clone with:[/{C_INFO}]")
        else:
            console.print(f"[{C_INFO}]Python package install detected. Update with:[/{C_INFO}]")
        if cmd:
            console.print(f"[{C_ACCENT}]{cmd}[/{C_ACCENT}]")
        return

    if check_only:
        return

    auto_apply = bool(getattr(sys, "frozen", False)) and platform.system() != "Windows"
    if not yes:
        if not sys.stdin.isatty():
            console.print(f"[{C_WARN}]Non-interactive terminal detected. Re-run with --yes to apply/download.[/{C_WARN}]")
            raise typer.Exit(1)
        prompt = "Apply update now" if auto_apply else "Download latest update asset now"
        if not Confirm.ask(f"[{C_ACCENT}]{prompt}?[/{C_ACCENT}]", default=True):
            return

    try:
        result = op_update(check_only=False, auto_apply=auto_apply)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] Update failed: {e}")
        raise typer.Exit(1)

    if result.get("applied"):
        console.print(f"[{C_SUCCESS}]Update applied successfully.[/{C_SUCCESS}]")
        console.print(f"[{C_DIM}]Restart StegoForge to run the new version.[/{C_DIM}]")
    elif result.get("downloaded_path"):
        console.print(f"[{C_SUCCESS}]Update downloaded:[/{C_SUCCESS}] {result['downloaded_path']}")
        if platform.system() == "Windows" and getattr(sys, "frozen", False):
            console.print(f"[{C_DIM}]Windows blocks replacing a running executable. Close app and replace manually.[/{C_DIM}]")
    else:
        console.print(f"[{C_WARN}]No suitable update asset could be downloaded automatically.[/{C_WARN}]")


@app.command("encode", help="Embed a payload into a carrier file")
def cmd_encode(
    carrier:   str  = typer.Option(..., "-c", "--carrier",   help="Path to carrier file"),
    payload:   str  = typer.Option(..., "-p", "--payload",   help="Path to payload file"),
    key:       Optional[str] = typer.Option(None, "-k", "--key", help="Encryption passphrase (optional)"),
    output:    Optional[str] = typer.Option(None, "-o", "--output",  help="Output path (auto if omitted)"),
    method:    Optional[str] = typer.Option(None,       "--method",  help="Encoding method (auto-detected from extension)"),
    depth:     int  = typer.Option(1,    "--depth",     help="Bit depth 1-4 (higher = more capacity, less invisible)"),
    decoy:     Optional[str] = typer.Option(None,       "--decoy",   help="Decoy payload file (enables dual-payload mode)"),
    decoy_key: Optional[str] = typer.Option(None,       "--decoy-key", help="Key for decoy payload"),
    wet_paper: bool = typer.Option(False, "--wet-paper", help="Apply Reed-Solomon wet paper protection for lossy survivability"),
    target: Optional[str] = typer.Option(None, "--target", help="Target platform profile: twitter, instagram, telegram, discord, whatsapp, facebook, tiktok, linkedin, reddit, signal"),
    test_survival: bool = typer.Option(False, "--test-survival", help="Simulate target platform recompression and test extraction locally"),
    preserve_fingerprint: bool = typer.Option(
        False,
        "--preserve-fingerprint",
        help="Use PRNU-aware embedding for real-camera images (slower, reduced effective capacity)",
    ),
    cover: Optional[str] = typer.Option(None, "--cover", help="Cover text file for linguistic mode (Tier A)"),
    topic: Optional[str] = typer.Option(None, "--topic", help="Topic prompt for linguistic generation mode (Tier B)"),
    llm_model: Optional[str] = typer.Option(None, "--llm-model", help="LLM model or endpoint descriptor for linguistic Tier B"),
    target_ip: Optional[str] = typer.Option(None, "--target-ip", help="Target IP for network covert methods"),
    target_port: Optional[int] = typer.Option(None, "--target-port", help="Target port for network covert methods"),
    listen_ip: Optional[str] = typer.Option(None, "--listen-ip", help="Listener IP for decode/network receive paths"),
    listen_port: Optional[int] = typer.Option(None, "--listen-port", help="Listener port for decode/network receive paths"),
    channel: Optional[str] = typer.Option(None, "--channel", help="Network channel: ip_id|tcp_seq|ttl|timing"),
    timing_delta: int = typer.Option(50, "--timing-delta", help="Timing channel delta in milliseconds"),
    json_mode: bool = typer.Option(False, "--json",      help="Output JSON instead of formatted text"),
):
    try:
        result = op_encode(
            carrier,
            payload,
            key,
            output,
            method,
            depth,
            decoy,
            decoy_key,
            wet_paper,
            target,
            test_survival,
            preserve_fingerprint,
            cover,
            topic,
            llm_model,
            json_mode,
            target_ip=target_ip,
            target_port=target_port,
            listen_ip=listen_ip,
            listen_port=listen_port,
            channel=channel,
            timing_delta=timing_delta,
        )
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_encode_result(result)
    except (ValueError, IOError) as e:
        if json_mode:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        raise typer.Exit(1)


@app.command("decode", help="Extract and decrypt a hidden payload")
def cmd_decode(
    file:      str  = typer.Option(..., "-f", "--file",   help="Path to stego file"),
    key:       Optional[str] = typer.Option(None, "-k", "--key", help="Decryption passphrase (optional)"),
    output:    Optional[str] = typer.Option(None, "-o", "--output", help="Output path (auto if omitted)"),
    method:    Optional[str] = typer.Option(None,       "--method", help="Encoding method (auto-detected if omitted)"),
    wet_paper: bool = typer.Option(False, "--wet-paper", help="Decode payload as wet paper encoded before decryption"),
    target_ip: Optional[str] = typer.Option(None, "--target-ip", help="Target IP for network covert methods"),
    target_port: Optional[int] = typer.Option(None, "--target-port", help="Target port for network covert methods"),
    listen_ip: Optional[str] = typer.Option(None, "--listen-ip", help="Listener IP for network covert methods"),
    listen_port: Optional[int] = typer.Option(None, "--listen-port", help="Listener port for network covert methods"),
    channel: Optional[str] = typer.Option(None, "--channel", help="Network channel: ip_id|tcp_seq|ttl|timing"),
    timing_delta: int = typer.Option(50, "--timing-delta", help="Timing channel delta in milliseconds"),
    json_mode: bool = typer.Option(False, "--json",     help="Output JSON"),
):
    try:
        result = op_decode(
            file,
            key,
            output,
            method,
            wet_paper,
            json_mode,
            target_ip=target_ip,
            target_port=target_port,
            listen_ip=listen_ip,
            listen_port=listen_port,
            channel=channel,
            timing_delta=timing_delta,
        )
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_decode_result(result)
    except (ValueError, IOError) as e:
        if json_mode:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        raise typer.Exit(1)


@app.command("detect", help="Analyze a file for hidden content")
def cmd_detect(
    file:         str  = typer.Option(..., "-f", "--file", help="File to analyze"),
    chi2:         bool = typer.Option(False, "--chi2",     help="Run chi-square LSB detector"),
    rs:           bool = typer.Option(False, "--rs",       help="Run RS analysis"),
    exif:         bool = typer.Option(False, "--exif",     help="Run EXIF/metadata scanner"),
    blind:        bool = typer.Option(False, "--blind",    help="Run blind brute-force extractor"),
    ml:           bool = typer.Option(False, "--ml",       help="Run ML steganalysis (downloads small Hugging Face ONNX model on first use)"),
    fingerprint:  bool = typer.Option(False, "--fingerprint", help="Run PRNU inconsistency detector"),
    binary:       bool = typer.Option(False, "--binary",   help="Run ELF/PE binary slack anomaly detector"),
    all_detect:   bool = typer.Option(False, "--all",      help="Run all detectors"),
    json_mode:    bool = typer.Option(False, "--json",     help="Output JSON"),
    stdin:        bool = typer.Option(False, "--stdin",    help="Read file from stdin"),
):
    try:
        if stdin:
            data = sys.stdin.buffer.read()
            fd, tmpfile_path = tempfile.mkstemp(prefix="stegoforge_stdin_detect_", suffix=".bin")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                result = op_detect(tmpfile_path, chi2, rs, exif, blind, ml, fingerprint, binary, all_detect, json_mode)
            finally:
                Path(tmpfile_path).unlink(missing_ok=True)
        else:
            result = op_detect(file, chi2, rs, exif, blind, ml, fingerprint, binary, all_detect, json_mode)
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_detect_results(result)
    except (ValueError, IOError) as e:
        if json_mode:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        raise typer.Exit(1)


@app.command("ctf", help="Run full CTF forensic analysis on a file")
def cmd_ctf(
    file:      str  = typer.Option(..., "-f", "--file",    help="Suspicious file to analyze"),
    batch:     Optional[str] = typer.Option(None, "--batch", help="Directory to scan in batch mode"),
    json_mode: bool = typer.Option(False, "--json",        help="Output JSON"),
    stdin:     bool = typer.Option(False, "--stdin",       help="Read file from stdin"),
):
    try:
        if batch:
            batch_dir = Path(batch)
            if not batch_dir.is_dir():
                raise IOError(f"Batch directory not found: {batch}")
            files = list(batch_dir.glob("*"))
            all_results = []
            for f in files:
                if f.is_file():
                    try:
                        r = op_ctf(str(f), json_mode=True)
                        all_results.append(r)
                    except Exception as e:
                        all_results.append({"file": str(f), "error": str(e)})
            if json_mode:
                print(json.dumps(all_results, indent=2))
            else:
                for r in all_results:
                    if "error" not in r:
                        print_ctf_report(r)
                    else:
                        console.print(f"[{C_WARN}][SKIP][/{C_WARN}] {r['file']}: {r['error']}")
        elif stdin:
            data = sys.stdin.buffer.read()
            fd, tmpfile_path = tempfile.mkstemp(prefix="stegoforge_stdin_ctf_", suffix=".bin")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                result = op_ctf(tmpfile_path, json_mode)
                if json_mode:
                    print(json.dumps(result, indent=2))
                else:
                    print_ctf_report(result)
            finally:
                Path(tmpfile_path).unlink(missing_ok=True)
        else:
            with console.status(
                f"[{C_INFO}]Running all detectors on {Path(file).name}...[/{C_INFO}]",
                spinner="dots2",
            ):
                result = op_ctf(file, json_mode)
            if json_mode:
                print(json.dumps(result, indent=2))
            else:
                print_ctf_report(result)
    except (ValueError, IOError) as e:
        if json_mode:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        raise typer.Exit(1)


@app.command("capacity", help="Check how much data a carrier can hold")
def cmd_capacity(
    carrier: str  = typer.Option(..., "-c", "--carrier", help="Carrier file"),
    method:  Optional[str] = typer.Option(None,       "--method", help="Encoding method"),
    depth:   int  = typer.Option(1,    "--depth",     help="Bit depth 1-4"),
    json_mode: bool = typer.Option(False, "--json",   help="Output JSON"),
):
    try:
        result = op_capacity(carrier, method, depth)
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_capacity_result(result)
    except (ValueError, IOError) as e:
        if json_mode:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        raise typer.Exit(1)


@app.command("survive", help="Run local platform survivability simulation")
def cmd_survive(
    carrier: str = typer.Option(..., "-c", "--carrier", help="Carrier file"),
    payload: str = typer.Option(..., "-p", "--payload", help="Payload file"),
    key: str = typer.Option(..., "-k", "--key", help="Encryption passphrase"),
    target: str = typer.Option(..., "--target", help="Platform target: twitter|instagram|telegram|discord|whatsapp|facebook|tiktok|linkedin|reddit|signal"),
    method: Optional[str] = typer.Option(None, "--method", help="Optional method override"),
    depth: int = typer.Option(1, "--depth", help="Bit depth 1-4"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output path"),
    json_mode: bool = typer.Option(False, "--json", help="Output JSON"),
):
    try:
        result = op_encode(
            carrier,
            payload,
            key,
            output,
            method,
            depth,
            None,
            None,
            False,
            target,
            True,
            False,
            None,
            None,
            None,
            json_mode,
        )
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_encode_result(result)
    except (ValueError, IOError) as e:
        if json_mode:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        raise typer.Exit(1)


@deadrop_app.command("post", help="Encode and prepare a dead-drop carrier")
def deadrop_post(
    carrier: str = typer.Option(..., "-c", "--carrier", help="Carrier file"),
    payload: str = typer.Option(..., "-p", "--payload", help="Payload file"),
    key: str = typer.Option(..., "-k", "--key", help="Shared channel key"),
    method: Optional[str] = typer.Option(None, "--method", help="Encoding method"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output stego file"),
    upload_url: Optional[str] = typer.Option(None, "--upload-url", help="Optional HTTP endpoint to upload stego carrier"),
    upload_method: str = typer.Option("PUT", "--upload-method", help="HTTP upload method: PUT or POST"),
):
    result = op_encode(
        carrier,
        payload,
        key,
        output,
        method,
        1,
        None,
        None,
        False,
        None,
        False,
        False,
        None,
        None,
        None,
        False,
    )
    print_encode_result(result)

    if upload_url:
        from protocol.deadrop import upload_bytes

        payload_bytes = Path(result["output"]).read_bytes()
        upload_result = upload_bytes(upload_url, payload_bytes, method=upload_method)
        console.print(
            f"[{C_SUCCESS}]Uploaded dead-drop carrier:[/{C_SUCCESS}] "
            f"HTTP {upload_result['status']} {upload_result['reason']}"
        )


@deadrop_app.command("check", help="Fetch URL once and attempt dead-drop extraction")
def deadrop_check(
    url: str = typer.Option(..., "--url", help="Public URL hosting the carrier"),
    key: str = typer.Option(..., "-k", "--key", help="Shared channel key"),
    method: Optional[str] = typer.Option(None, "--method", help="Optional method hint"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Decoded payload output"),
):
    from protocol.deadrop import fetch_url_bytes
    import tempfile

    blob = fetch_url_bytes(url)
    suffix = Path(url.split("?")[0]).suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(blob)
        tmp.flush()
        path = tmp.name

    result = op_decode(path, key, output, method, False, False)
    print_decode_result(result)


@deadrop_app.command("monitor", help="Poll URL and extract unseen dead-drop payloads")
def deadrop_monitor(
    url: str = typer.Option(..., "--url", help="Public URL hosting rotating carriers"),
    key: str = typer.Option(..., "-k", "--key", help="Shared channel key"),
    method: Optional[str] = typer.Option(None, "--method", help="Optional method hint"),
    interval: int = typer.Option(30, "--interval", help="Polling interval in seconds"),
):
    from protocol.deadrop import monitor_loop
    import tempfile
    from urllib.parse import urlparse

    console.print(f"[{C_INFO}]Monitoring {url} every {interval}s... (Ctrl+C to stop)[/{C_INFO}]")

    def _on_new(blob: bytes, digest: str):
        try:
            suffix = Path(urlparse(url).path).suffix or ".bin"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(blob)
                tmp.flush()
                path = tmp.name
            result = op_decode(path, key, None, method, False, False)
            console.print(f"[{C_SUCCESS}]New payload extracted from hash {digest[:12]}... -> {result['output']}[/{C_SUCCESS}]")
        except Exception:
            console.print(f"[{C_DIM}]No payload extracted for hash {digest[:12]}...[/{C_DIM}]")

    monitor_loop(url, interval, _on_new)


@deadrop_keyx_app.command("initiate", help="Create local private key and embed X25519 public key in a carrier")
def deadrop_keyx_initiate(
    carrier: str = typer.Option(..., "-c", "--carrier", help="Carrier file"),
    output: str = typer.Option(..., "-o", "--output", help="Output stego carrier path"),
    private_key_file: str = typer.Option(".stegoforge_keyx.priv", "--private-key-file", help="Encrypted local private key file path"),
    local_passphrase: str = typer.Option(..., "--local-passphrase", help="Local passphrase protecting private key file"),
    method: Optional[str] = typer.Option(None, "--method", help="Embedding method"),
    depth: int = typer.Option(1, "--depth", help="Bit depth for LSB-like methods"),
):
    """Security note: forward secrecy depends on keeping local private-key file and passphrase secure."""
    from protocol.keyexchange import generate_ephemeral_keypair, save_private_key_file

    m = method or auto_detect_method(carrier)
    encoder = get_encoder(m)
    carrier_path = Path(carrier)
    carrier_bytes = carrier_path.read_bytes()
    priv_raw, pub_raw = generate_ephemeral_keypair()

    kwargs = {"depth": depth}
    ext = carrier_path.suffix.lower()
    if m in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
        kwargs["ext"] = ext
    if m in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(carrier_path)

    cap = encoder.capacity(carrier_bytes, **kwargs)
    if len(pub_raw) > cap:
        raise typer.BadParameter(f"Carrier capacity too small for key exchange payload ({cap} bytes)")

    stego = encoder.encode(carrier_bytes, pub_raw, **kwargs)
    Path(output).write_bytes(stego)
    save_private_key_file(private_key_file, priv_raw, local_passphrase)

    console.print(f"[{C_SUCCESS}]Key exchange initiate complete.[/{C_SUCCESS}]")
    console.print(f"[{C_INFO}]Public key embedded carrier: {output}[/{C_INFO}]")
    console.print(f"[{C_WARN}]Security note:[/{C_WARN}] protect local passphrase/private key file; compromise breaks session secrecy.")


@deadrop_keyx_app.command("complete", help="Extract peer public key and derive shared session key")
def deadrop_keyx_complete(
    received_file: str = typer.Option(..., "-f", "--file", help="Received stego carrier containing peer public key"),
    private_key_file: str = typer.Option(".stegoforge_keyx.priv", "--private-key-file", help="Encrypted local private key file path"),
    local_passphrase: str = typer.Option(..., "--local-passphrase", help="Local passphrase protecting private key file"),
    method: Optional[str] = typer.Option(None, "--method", help="Method hint"),
    output_key_file: Optional[str] = typer.Option(None, "--output-key-file", help="Optional file to save derived session key"),
):
    """Security note: X25519 provides forward secrecy, but carrier secrecy still matters."""
    from protocol.keyexchange import load_private_key_file, derive_shared_secret, derive_session_key_hex

    file_path = Path(received_file)
    data = file_path.read_bytes()
    ext = file_path.suffix.lower()

    methods = [method] if method else []
    if not methods:
        suggested = auto_detect_method(received_file)
        methods = [suggested]

    peer_pub = None
    for m in methods:
        encoder = get_encoder(m)
        kwargs = {"depth": 1}
        if m in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
            kwargs["ext"] = ext
        if m in ("docx", "xlsx", "office"):
            kwargs["filename"] = str(file_path)
        depths = [1, 2, 3, 4] if m in ("lsb", "adaptive-lsb", "fingerprint-lsb", "audio-lsb") else [1]
        for d in depths:
            kwargs["depth"] = d
            try:
                raw = encoder.decode(data, **kwargs)
                if len(raw) == 32:
                    peer_pub = raw
                    break
            except Exception:
                continue
        if peer_pub is not None:
            break

    if peer_pub is None:
        raise typer.BadParameter("Failed to extract 32-byte peer X25519 public key from carrier")

    priv_raw = load_private_key_file(private_key_file, local_passphrase)
    shared = derive_shared_secret(priv_raw, peer_pub)
    session_key = derive_session_key_hex(shared)

    if output_key_file:
        Path(output_key_file).write_text(session_key, encoding="utf-8")
        console.print(f"[{C_SUCCESS}]Derived session key saved to {output_key_file}[/{C_SUCCESS}]")
    else:
        console.print(f"[{C_SUCCESS}]Derived session key:[/{C_SUCCESS}] {session_key}")

    console.print(
        f"[{C_WARN}]Security note:[/{C_WARN}] X25519 gives forward secrecy, but carriers must remain plausibly innocuous to passive observers."
    )


@app.command("web", help="Launch the local web UI")
def cmd_web(
    port: int = typer.Option(5000, "--port", help="Port to bind (default: 5000)"),
    skip_banner: bool = typer.Option(False, "--skip-banner", help="Skip printing the banner"),
):
    if not skip_banner:
        print_banner()
    try:
        from web.app import create_app
        flask_app = create_app()
        console.print(f"[{C_SUCCESS}]✓ Web UI running at http://localhost:{port}[/{C_SUCCESS}]")
        console.print(f"[{C_DIM}]All files processed locally. Nothing is uploaded to any server.[/{C_DIM}]")
        flask_app.run(host="127.0.0.1", port=port, debug=False)
    except ImportError:
        console.print(
            f"[{C_ERROR}][ERROR][/{C_ERROR}] Web dependencies not installed.\n"
            "Run: pip install -r requirements-web.txt"
        )
        raise typer.Exit(1)
    except (ValueError, IOError, OSError) as e:
        console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] Failed to start web UI: {e}")
        raise typer.Exit(1)


@app.command("diff", help="Compare an original carrier against its stego version — shows changed pixels/bytes and saves a heatmap")
def cmd_diff(
    carrier:     str           = typer.Option(..., "-c", "--carrier",       help="Original (clean) carrier file"),
    stego:       str           = typer.Option(..., "-s", "--stego",         help="Stego carrier file to compare"),
    save_heatmap: Optional[str] = typer.Option(None,    "--save-heatmap",   help="Path to save amplified diff heatmap PNG (auto-named if omitted)"),
    json_mode:   bool          = typer.Option(False,    "--json",           help="Output JSON"),
):
    """
    Compares two files and reports exactly which pixels (images) or bytes (audio/binary)
    were modified during encoding. Useful for verifying stealth and diagnosing artifacts.

    Saves a heatmap PNG where bright regions indicate modified pixels.

    Examples:
      stegoforge diff -c cover.png -s stego.png
      stegoforge diff -c cover.png -s stego.png --save-heatmap report_heat.png --json
    """
    try:
        result = op_diff(carrier, stego, save_heatmap)
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_diff_result(result)
    except (ValueError, IOError) as e:
        if json_mode:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        raise typer.Exit(1)


@app.command("batch", help="Encode a payload into every compatible carrier in a directory")
def cmd_batch(
    batch_dir:  str           = typer.Option(..., "-d", "--dir",       help="Directory containing carrier files"),
    payload:    str           = typer.Option(..., "-p", "--payload",   help="Payload file to embed in each carrier"),
    key:        str           = typer.Option("",  "-k", "--key",       help="Encryption passphrase (or set STEGOFORGE_KEY env var)"),
    output_dir: Optional[str]  = typer.Option(None,    "-o", "--output", help="Output directory for stego files (defaults to source dir)"),
    method:     Optional[str]  = typer.Option(None,    "--method",    help="Force encoding method (auto-detected per file if omitted)"),
    depth:      int            = typer.Option(1,        "--depth",     help="Bit depth 1-4 for LSB-based methods"),
    wet_paper:  bool           = typer.Option(False,    "--wet-paper", help="Enable Reed-Solomon wet-paper protection on each file"),
    json_mode:  bool           = typer.Option(False,    "--json",      help="Output JSON summary"),
):
    """
    Walks a directory and embeds the same payload into every supported carrier file.
    Supported formats: PNG, BMP, TIFF, WEBP, JPG, GIF, WAV, MP3, FLAC, OGG, MP4,
    MKV, AVI, PDF, DOCX, XLSX, TXT.

    Each output file is named <original>_stego.<ext> and saved alongside the original
    (or in --output if specified).

    Examples:
      stegoforge batch -d ./images/ -p secret.txt -k mykey
      stegoforge batch -d ./carriers/ -p msg.pdf -k mykey -o ./out/ --depth 2 --json
    """
    try:
        result = op_batch_encode(batch_dir, payload, key, output_dir, method, depth, wet_paper)
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_batch_result(result)
    except (ValueError, IOError) as e:
        if json_mode:
            print(json.dumps({"status": "error", "message": str(e)}))
        else:
            console.print(f"[{C_ERROR}][ERROR][/{C_ERROR}] {e}")
        raise typer.Exit(1)


@app.command("completion", help="Print shell completion script for bash, zsh, or fish")
def cmd_completion(
    shell: str = typer.Argument("bash", help="Shell type: bash | zsh | fish"),
):
    """
    Prints a shell completion script for StegoForge commands.

    Usage:
      # bash (add to ~/.bashrc):
      eval "$(stegoforge completion bash)"

      # zsh (add to ~/.zshrc):
      eval "$(stegoforge completion zsh)"

      # fish:
      stegoforge completion fish | source
    """
    commands = [
        "encode", "decode", "detect", "ctf", "capacity",
        "survive", "diff", "batch", "web", "update", "init", "completion",
    ]
    if shell == "bash":
        cmds_str = " ".join(commands)
        script = f"""# StegoForge bash completion
_stegoforge_complete() {{
    local cur prev words cword
    _init_completion || return
    local commands="{cmds_str}"
    if [[ $cword -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
        return
    fi
    case "$prev" in
        -f|--file|-c|--carrier|-s|--stego|-p|--payload|-o|--output)
            COMPREPLY=( $(compgen -f -- "$cur") ); return ;;
        -d|--dir|--output)
            COMPREPLY=( $(compgen -d -- "$cur") ); return ;;
        --method)
            COMPREPLY=( $(compgen -W "lsb adaptive-lsb fingerprint-lsb dct alpha palette audio-lsb phase spectrogram unicode pdf docx xlsx video-dct video-motion elf pe linguistic" -- "$cur") ); return ;;
        --target)
            COMPREPLY=( $(compgen -W "twitter instagram telegram discord whatsapp facebook tiktok linkedin reddit signal" -- "$cur") ); return ;;
    esac
    COMPREPLY=( $(compgen -W "--help" -- "$cur") )
}}
complete -F _stegoforge_complete stegoforge
"""
        print(script)
    elif shell == "zsh":
        cmds_str = "\n    ".join(f"'{c}'" for c in commands)
        script = f"""# StegoForge zsh completion
#compdef stegoforge
_stegoforge() {{
    local -a commands
    commands=(
    {cmds_str}
    )
    _describe 'command' commands
}}
_stegoforge
"""
        print(script)
    elif shell == "fish":
        lines = [f"complete -c stegoforge -f -a '{c}'" for c in commands]
        print("\n".join(lines))
    else:
        console.print(f"[{C_ERROR}]Unknown shell '{shell}'. Use: bash, zsh, or fish.[/{C_ERROR}]")
        raise typer.Exit(1)




import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    app()
