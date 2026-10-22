#!/usr/bin/env python3
"""
stegoforge.py — StegoForge CLI

Animated ASCII banner, interactive menu, and direct bypass arguments.
All features accessible both interactively and via direct args.
"""
import contextlib
import json
import errno
import os
import sys
import time
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
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.align import Align
from rich.live import Live
from rich.prompt import Prompt, Confirm
from rich import box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
import multiprocessing

# ── Ops split (canonical implementations live in stegoforge_ops/) ─────────────
# stegoforge.py keeps CLI + Typer commands; ops are re-exported for compat
# (`from stegoforge import op_encode` keeps working).
from stegoforge_ops.registry import (
    DECODE_METHODS,
    ENCODE_METHODS,
    EXT_TO_METHOD,
    HYBRID_METHODS,
    METHOD_CATEGORY_ORDER,
    STEALTH_SCORES,
    _group_encode_methods,
    _guess_payload_ext,
    _is_audio_ext,
    _is_binary_ext,
    _is_document_ext,
    _is_image_ext,
    _is_video_ext,
    _read_key_file,
    _resize_carrier_if_needed,
    _scrub_secret,
    _stealth_bar,
    _warn_argv_key,
    auto_detect_method,
    get_encoder,
    get_output_path,
    guess_payload_ext,
)
from stegoforge_ops.ui import (
    C_ACCENT,
    C_DIM,
    C_ERROR,
    C_GOLD,
    C_INFO,
    C_SUCCESS,
    C_TITLE,
    C_WARN,
    console,
    detector_details,
    detector_summary,
    detector_table,
    error_payload,
    fmt_bytes,
    headline,
    meter,
    print_error,
    print_result,
    print_warning,
)
from stegoforge_ops.encode_ops import op_encode
from stegoforge_ops.decode_ops import op_decode
from stegoforge_ops.detect_ops import (
    _SkippedDetector,
    _VideoAudioBlindDetector,
    _result_to_dict,
    op_ctf,
    op_detect,
)
from stegoforge_ops.capacity_ops import op_batch_encode, op_capacity, op_diff

# Compatibility surface: external scripts do `from stegoforge import op_encode` and friends.
__all__ = [
    "auto_detect_method",
    "DECODE_METHODS",
    "ENCODE_METHODS",
    "EXT_TO_METHOD",
    "get_encoder",
    "get_output_path",
    "guess_payload_ext",
    "HYBRID_METHODS",
    "METHOD_CATEGORY_ORDER",
    "op_batch_encode",
    "op_capacity",
    "op_ctf",
    "op_decode",
    "op_detect",
    "op_diff",
    "op_encode",
    "STEALTH_SCORES",
    "_group_encode_methods",
    "_guess_payload_ext",
    "_is_audio_ext",
    "_is_binary_ext",
    "_is_document_ext",
    "_is_image_ext",
    "_is_video_ext",
    "_read_key_file",
    "_resize_carrier_if_needed",
    "_result_to_dict",
    "_scrub_secret",
    "_SkippedDetector",
    "_stealth_bar",
    "_VideoAudioBlindDetector",
    "_warn_argv_key",
]

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
    "Adaptive LSB  ·  Argon2id Key Derivation  ·  AES-256-GCM",
    "Wet-Paper Error Correction  ·  Platform Survival Simulation  ·  Audio Phase Coding",
    "Decoy Containers  ·  Network Covert Channels  ·  Offline-First",
    "Secure Dead Drops  ·  X25519 Key Exchange  ·  Blind Extraction",
]
PRIMARY_TAGLINE = "Hide Data in Digital Carriers  ·  Detect What Others Hid"

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
# Pinned upstream repo — no env override (an attacker-controlled repo URL would
# turn auto-update into remote code execution).
GITHUB_REPO = "Nour833/StegoForge"
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
    colors = ["#f0c870", "#e4b560", "#d6a243", "#c4912f", "#a87a26", "#8a6420"]

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
        console.print(Align.center(f"[dim]{highlight}[/dim]"), highlight=False)
        _ui_sleep(0.3)
    else:
        console.print(Align.center(f"[bold white]{PRIMARY_TAGLINE}[/bold white]"), highlight=False)

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
    info_text.append("Encryption: ", style=C_ACCENT)
    info_text.append("AES-256-GCM", style="bold white")
    info_text.append("   ·   ", style="dim")
    info_text.append("Network: ", style=C_ACCENT)
    from core.config import get_config

    info_text.append("disabled" if get_config().offline else "only when you ask", style="bold white")

    panel = Panel(
        Align.center(info_text),
        title="[bold white]StegoForge[/bold white]",
        subtitle=f"[{C_ACCENT}]Made by nour833[/{C_ACCENT}]",
        border_style=C_ACCENT,
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

    repo_path_str = str(repo_root)
    if (repo_path_str.startswith("/usr/") and not repo_path_str.startswith("/usr/local/")) or repo_path_str.startswith("/opt/"):
        return "system-package"

    return "python-package"


def _manual_update_command(install_kind: str) -> str:
    if install_kind == "source-checkout":
        repo_root = Path(__file__).resolve().parent
        return f'git -C "{repo_root}" pull --ff-only'

    if install_kind == "python-package":
        py_exec = Path(sys.executable).resolve()
        return f'"{py_exec}" -m pip install --upgrade stegoforge'

    if install_kind == "system-package":
        return "Download the latest .deb from GitHub Releases or update via your system package manager (e.g. apt upgrade stegoforge)."

    return ""


def _print_update_versions(probe: dict):
    current = _display_version(str(probe.get("current", "unknown")))
    latest = _display_version(str(probe.get("latest", "unknown")))
    console.print(f"[{C_INFO}]Current version: {current}[/{C_INFO}]")
    console.print(f"[{C_INFO}]Latest release: {latest}[/{C_INFO}]")


def _is_archive_asset(name: str) -> bool:
    lower = name.lower()
    return lower.endswith(".zip") or lower.endswith(".tar.gz") or lower.endswith(".tgz")


def _select_release_asset(assets: list[dict]) -> dict | None:
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


def _certifi_ssl_context() -> ssl.SSLContext | None:
    try:
        import certifi
    except Exception:
        return None

    cafile = certifi.where()
    if not cafile:
        return None
    return ssl.create_default_context(cafile=cafile)


def _urlopen_with_ca_fallback(req: urllib.request.Request, timeout: int):
    from core.config import get_config

    if get_config().offline:
        raise ValueError("offline mode is on (--offline / STEGOFORGE_OFFLINE): network access is disabled")
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


def _verify_downloaded_asset(path: Path) -> None:
    """Verify downloaded self-update asset.

    Enforcement order:
    1. If cosign is installed and STEGOFORGE_UPDATE_SIG_URL is set, verify the
       Sigstore/cosign bundle ( Pin set → enforce.
    3. Otherwise refuse auto-apply (download-only) unless STEGOFORGE_UPDATE_UNPINNED=1.
    """
    import hashlib
    import shutil
    import subprocess

    expected = os.getenv("STEGOFORGE_UPDATE_SHA256", "").strip().lower()
    sig_url = os.getenv("STEGOFORGE_UPDATE_SIG_URL", "").strip()
    if sig_url and shutil.which("cosign"):
        try:
            subprocess.run(
                ["cosign", "verify-blob", "--yes", "--bundle", sig_url, str(path)],
                check=True,
                capture_output=True,
                timeout=60,
            )
            return
        except Exception as exc:
            raise ValueError(f"Update cosign verification failed: {exc}") from exc
    if expected:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for blk in iter(lambda: f.read(65536), b""):
                h.update(blk)
        if h.hexdigest().lower() != expected:
            raise ValueError("Update asset SHA256 mismatch — refusing to apply (possible MITM)")
        return
    if os.getenv("STEGOFORGE_UPDATE_UNPINNED", "") not in ("1", "true", "yes"):
        raise ValueError(
            "Refusing to auto-apply unpinned update (no STEGOFORGE_UPDATE_SHA256 or "
            "STEGOFORGE_UPDATE_SIG_URL). Set STEGOFORGE_UPDATE_UNPINNED=1 to allow download-only."
        )
    console.print(
        f"[{C_WARN}]No update pin set — asset authenticity "
        f"relies on TLS + GitHub release trust only.[/{C_WARN}]"
    )


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
        _verify_downloaded_asset(tmp_target)

        if platform.system() != "Windows" and not _is_archive_asset(asset_name):
            with contextlib.suppress(OSError):
                tmp_target.chmod(tmp_target.stat().st_mode | 0o111)

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


# ── Rich output helpers ───────────────────────────────────────────────────────

def print_encode_result(result: dict):
    from rich.text import Text

    size = f"{result['payload_size']:,} B → {result['encrypted_size']:,} B encrypted"
    used = result["encrypted_size"] / max(result["capacity"], 1) * 100
    rows = [
        ("Output", Text(str(result["output"]), style=C_SUCCESS)),
        ("Carrier", result["carrier"]),
        ("Method", f"{result['method']}  ·  depth {result['depth']}"),
        ("Size", f"{size}  ({used:.1f}% of {result['capacity']:,} B capacity)"),
    ]
    if result.get("decoy_mode"):
        rows.append(("Decoy", "second payload embedded"))
    if result.get("wet_paper"):
        rows.append(("Wet paper", "Reed-Solomon redundancy enabled"))
    if result.get("preserve_fingerprint"):
        rows.append(("Fingerprint", "preservation mode (slightly reduced capacity)"))
    if result.get("target_profile"):
        t = result["target_profile"]
        rows.append(("Target", f"{t['platform']}  ({t['notes']})"))
    if result.get("resized"):
        rows.append(("Resized", f"{result['resized']['from']} → {result['resized']['to']}"))
    if result.get("survival_test"):
        st = result["survival_test"]
        verdict = Text("survived" if st.get("survived") else "did not survive", style=C_SUCCESS if st.get("survived") else C_ERROR)
        verdict.append(f"  ({st.get('target')}, corrected bits {st.get('corrected_bits', 0)})", style="dim")
        rows.append(("Survival", verdict))
        if not st.get("survived") and st.get("error"):
            rows.append(("", Text(str(st["error"]), style="dim")))
    notes = [Text.assemble(("! ", C_WARN), w) for w in result.get("warnings", [])]
    print_result(headline(True, "Payload embedded"), rows, notes)


def print_decode_result(result: dict):
    rows = [
        ("Output", Text(str(result["output"]), style=C_SUCCESS)),
        ("Input", result["file"]),
        ("Method", result["method"]),
        ("Size", f"{result['payload_size']:,} B"),
    ]
    if result.get("wet_paper"):
        rows.append(("Wet paper", f"corrected bits: {result.get('wet_corrected_bits', 0)}"))
    print_result(headline(True, "Payload extracted"), rows)


def _detector_block(report: dict) -> None:
    results = report["results"]
    console.print(detector_table(results))
    details = detector_details(results)
    if details:
        console.print()
        for line in details:
            console.print(line)
    console.print()
    console.print(detector_summary(results))


def print_detect_results(report: dict):
    from rich.text import Text

    console.print(Text.assemble(("Detection report  ", C_TITLE), (str(report["file"]), "bold"),
                                (f"  ·  {report['detectors_run']} detectors", "dim")))
    console.print()
    _detector_block(report)
    console.print(Text("Results are indicators, not proof. An inconclusive or clean result never proves a file is clean.", style="dim"))


def print_ctf_report(report: dict):
    from rich.text import Text

    verdict = report["overall_verdict"]
    detected = "DETECTED" in verdict
    signal = int(report["overall_confidence"] * 100)
    console.print(Text.assemble(("CTF analysis  ", C_TITLE), (str(report["file"]), "bold"),
                                (f"  ·  {fmt_bytes(report['file_size'])}", "dim")))
    console.print(Text.assemble(("Verdict  ", "dim"), (verdict, C_ERROR if detected else C_SUCCESS),
                                (f"   strongest detector signal {signal}%", "dim")))
    console.print()
    _detector_block(report)

    if report.get("notes"):
        console.print(f"\n[{C_WARN}]Notes[/{C_WARN}]")
        for note in report["notes"]:
            console.print(Text.assemble("  · ", str(note)))

    if report["saved_payloads"]:
        console.print(f"\n[{C_SUCCESS}]Extracted payloads saved[/{C_SUCCESS}]")
        for path in report["saved_payloads"]:
            console.print(Text.assemble(("  → ", C_ACCENT), str(path)))


def print_capacity_result(result: dict):
    from rich.text import Text

    stealth = STEALTH_SCORES.get(result.get("method", ""), 0)
    rows = [
        ("Carrier", result["carrier"]),
        ("Method", f"{result['method']}  ·  depth {result['depth']}"),
        ("Capacity", Text.assemble((f"{result['capacity_bytes']:,} bytes", C_GOLD), (f"   {result['capacity_kb']:.2f} KB", "dim"))),
        ("Stealth", Text.assemble(meter(stealth / 100, higher_is_better=True), (f" {stealth}/100", "dim"))),
    ]
    if result.get("jnd_safe_dct_capacity"):
        j = result["jnd_safe_dct_capacity"]
        rows.append(("Perceptually safe", f"{j['bytes']:,} bytes ({j['kb']} KB)  ·  {j['note']}"))
    if result.get("video_context"):
        v = result["video_context"]
        rows.append(("Video", f"{v.get('duration_seconds')} s  ·  {v.get('frames')} frames  ·  {v.get('usable_frames', v.get('keyframes'))} usable"))
        rows.append(("", Text(str(v.get("capacity_note", "")), style="dim")))
    print_result(headline(True, "Capacity"), rows)


def print_diff_result(result: dict):
    """Pretty-print the result of op_diff."""
    from rich.text import Text

    kind = result.get("type", "binary")
    rows = [("Original", result["carrier"]), ("Modified", result["stego"])]
    if kind == "image":
        pct = result["changed_percent"]
        tone = C_SUCCESS if pct < 0.1 else (C_WARN if pct < 1.0 else C_ERROR)
        rows += [
            ("Size", f"{result['dimensions'][0]}×{result['dimensions'][1]} px"),
            ("Changed", Text(f"{result['changed_pixels']:,} of {result['total_pixels']:,} pixels ({pct}%)", style=tone)),
            ("Delta", f"max {result['max_delta']} per channel  ·  mean {result['mean_delta']:.4f}"),
        ]
        if result.get("heatmap"):
            rows.append(("Heatmap", Text(str(result["heatmap"]), style=C_SUCCESS)))
    else:
        rows.append(("Changed", f"{result.get('differing_bytes', 'n/a'):,} bytes ({result.get('differing_percent', 'n/a')}%)"
                     if isinstance(result.get("differing_bytes"), int) else "n/a"))
    print_result(headline(True, f"Comparison ({kind})"), rows)


def print_batch_result(result: dict):
    """Pretty-print the result of op_batch_encode."""
    from rich.text import Text

    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style="dim", padding=(0, 2, 0, 0))
    table.add_column("File", overflow="fold")
    table.add_column("", no_wrap=True)
    table.add_column("Method", no_wrap=True)
    table.add_column("Size", justify="right", no_wrap=True)
    table.add_column("Output / error", overflow="fold")

    for row in result["rows"]:
        if row["status"] == "success":
            pct = round(row["payload_size"] / max(row["capacity"], 1) * 100, 1)
            table.add_row(Text(row["file"]), Text("✓", style=C_SUCCESS), row["method"],
                          f"{row['payload_size']:,} B", Text(f"{Path(row['output']).name}  ({pct}% full)", style="dim"))
        else:
            table.add_row(Text(row["file"]), Text("✗", style=C_ERROR), "–", "–", Text(str(row.get("error", ""))[:120], style=C_ERROR))

    console.print(table)
    ok = result["failed"] == 0
    console.print(Text.assemble((f"{result['passed']} encoded", C_SUCCESS if result["passed"] else "dim"), "  ·  ",
                                (f"{result['failed']} failed", C_WARN if not ok else "dim"), "  ·  ",
                                (f"{result['total']} total", "dim")))


# ── Interactive menu ──────────────────────────────────────────────────────────

def interactive_encode():
    """Interactive encode wizard."""
    console.print(f"\n[{C_TITLE}]── ENCODE ──────────────────────────────────────[/{C_TITLE}]")
    carrier = Prompt.ask(f"  [{C_ACCENT}]Carrier file[/{C_ACCENT}] (path)")
    payload = Prompt.ask(f"  [{C_ACCENT}]Payload file[/{C_ACCENT}] (path)")
    key = Prompt.ask(f"  [{C_ACCENT}]Encryption key[/{C_ACCENT}] (passphrase)", password=True)

    # Show method options
    console.print("\n  [dim]Available methods grouped by category (hybrid-first):[/dim]")
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
    target = Prompt.ask(
        f"  [{C_ACCENT}]Platform target[/{C_ACCENT}] (Enter to skip: twitter/instagram/telegram/discord/whatsapp/signal)",
        default="",
    ) or None
    pad_str = Prompt.ask(f"  [{C_ACCENT}]Pad to N-byte blocks[/{C_ACCENT}] (0=off, 1-256)", default="0")
    pad_block = int(pad_str) if pad_str.isdigit() else 0
    allow_plaintext = False
    if not (key or "").strip():
        allow_plaintext = Confirm.ask(
            f"  [{C_ACCENT}]No key — embed plaintext explicitly?[/{C_ACCENT}]", default=False
        )
        if not allow_plaintext:
            console.print(f"[{C_ERROR}]Refusing plaintext embed without opt-in.[/{C_ERROR}]")
            raise typer.Exit(1)

    use_decoy = Confirm.ask(f"  [{C_ACCENT}]Enable decoy mode?[/{C_ACCENT}]", default=False)
    decoy = decoy_key = None
    if use_decoy:
        decoy = Prompt.ask(f"  [{C_ACCENT}]Decoy payload file[/{C_ACCENT}]")
        decoy_key = Prompt.ask(f"  [{C_ACCENT}]Decoy key[/{C_ACCENT}]", password=True)

    wet_paper = Confirm.ask(f"  [{C_ACCENT}]Wet-paper protection?[/{C_ACCENT}] (Reed-Solomon, lossy survival)", default=False)
    preserve_fingerprint = Confirm.ask(
        f"  [{C_ACCENT}]Preserve fingerprint?[/{C_ACCENT}] (PRNU-aware, slower)", default=False
    )
    cover = topic = llm_model = None
    if method == "linguistic":
        cover = Prompt.ask(f"  [{C_ACCENT}]Cover text file[/{C_ACCENT}] (Enter to skip)", default="") or None
        topic = Prompt.ask(f"  [{C_ACCENT}]Topic prompt[/{C_ACCENT}] (Enter to skip)", default="") or None
        llm_model = Prompt.ask(f"  [{C_ACCENT}]LLM endpoint[/{C_ACCENT}] (Enter to skip)", default="") or None

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
            wet_paper,
            target,
            False,
            preserve_fingerprint,
            cover,
            topic,
            llm_model,
            False,
            allow_plaintext=True if allow_plaintext else bool((key or "").strip() == ""),
            pad_block=pad_block,
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
        print_error(f"Update check failed: {e}")
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
        print_error(f"Update failed: {e}")
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
        except (OSError, ValueError) as e:
            print_error(e)
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
        cmd_web(port=port, host="127.0.0.1", skip_banner=True)
    except KeyboardInterrupt:
        console.print(f"\n[{C_DIM}]Web UI stopped.[/{C_DIM}]")


# ── Typer commands ────────────────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    offline: bool = typer.Option(False, "--offline", help="Disable all network access (dead drops, update check, remote fonts)"),
):
    """StegoForge — The most complete open-source steganography toolkit."""
    import os as _os

    if offline:
        _os.environ["STEGOFORGE_OFFLINE"] = "1"
    if ctx.invoked_subcommand is None:
        interactive_menu()

@app.command("init", help="(Re)install the bundled ML model into ~/.stegoforge (no network)")
def cmd_init():
    ok, message = sysmgr.install_bundled_model()
    style = C_SUCCESS if ok else C_WARN
    console.print(f"[{style}]{message}[/{style}]")


@app.command("doctor", help="Check this installation: dependencies, video/audio support, ML model")
def cmd_doctor(
    json_mode: bool = typer.Option(False, "--json", help="Output JSON"),
):
    checks = sysmgr.diagnose()
    failed_required = [c for c in checks if c.required and not c.ok]
    if json_mode:
        print(json.dumps({"ok": not failed_required, "checks": [
            {"name": c.name, "ok": c.ok, "required": c.required, "detail": c.detail} for c in checks]}, indent=2))
    else:
        table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False)
        table.add_column("", width=1, no_wrap=True)
        table.add_column("Component", style="bold")
        table.add_column("Status", overflow="fold")
        for c in checks:
            mark, style = ("✓", C_SUCCESS) if c.ok else (("✗", C_ERROR) if c.required else ("–", C_WARN))
            table.add_row(f"[{style}]{mark}[/{style}]", c.name, c.detail if c.ok else f"[{style}]{c.detail}[/{style}]")
        console.print(table)
        if failed_required:
            console.print(f"[{C_ERROR}]{len(failed_required)} required component(s) missing.[/{C_ERROR}]")
        else:
            console.print(f"[{C_SUCCESS}]All required components are present.[/{C_SUCCESS}] "
                          f"[{C_DIM}](– marks optional features that are unavailable)[/{C_DIM}]")
    if failed_required:
        raise typer.Exit(1)


@app.command("update", help="Check GitHub for newer releases and update when possible")
def cmd_update(
    check_only: bool = typer.Option(False, "--check-only", help="Only check for updates"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Apply/download update without confirmation"),
):
    try:
        probe = op_update(check_only=True, auto_apply=False)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, ValueError) as e:
        print_error(f"Update check failed: {e}")
        raise typer.Exit(1) from None

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
        print_error(f"Update failed: {e}")
        raise typer.Exit(1) from None

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
    key:       Optional[str] = typer.Option(None, "-k", "--key", help="Encryption passphrase (required unless --allow-plaintext; or set STEGOFORGE_KEY)"),
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
    allow_plaintext: bool = typer.Option(False, "--allow-plaintext/--no-plaintext", help="Explicitly allow unencrypted embed (fail-closed without a key)"),
    no_encrypt: bool = typer.Option(False, "--no-encrypt", help="Alias for --allow-plaintext"),
    pad_block: int = typer.Option(0, "--pad-to", help="Pad plaintext to N-byte blocks before encryption (1-256, e.g. 128)"),
    require_v2: bool = typer.Option(False, "--require-v2", help="Refuse legacy v1 crypto paths"),
    enforce_strong: bool = typer.Option(False, "--enforce-strong-pass", help="Refuse weak passphrases instead of warning"),
    key_file: Optional[str] = typer.Option(None, "--key-file", help="Read passphrase from file (avoids shell history)"),
    no_magic: bool = typer.Option(False, "--no-magic", help="Embed with no fixed header bytes, so nothing identifies the payload as StegoForge's (not combinable with --decoy)"),
    i_understand_root: bool = typer.Option(False, "--i-understand-root", help="Acknowledge live network covert ops authorization"),
):
    try:
        key = _read_key_file(key_file) or key
        _warn_argv_key()
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
            allow_plaintext=bool(allow_plaintext or no_encrypt),
            pad_block=pad_block,
            require_v2=require_v2,
            enforce_strong=enforce_strong,
            header_mode="obfuscated" if no_magic else "standard",
            i_understand_root=i_understand_root,
        )
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_encode_result(result)
    except (OSError, ValueError) as e:
        if json_mode:
            print(json.dumps(error_payload(e)))
        else:
            print_error(e)
        raise typer.Exit(1) from None


@app.command("decode", help="Extract and decrypt a hidden payload")
def cmd_decode(
    file:      str  = typer.Option(..., "-f", "--file",   help="Path to stego file"),
    key:       Optional[str] = typer.Option(None, "-k", "--key", help="Decryption passphrase (or set STEGOFORGE_KEY; leave out only for unencrypted payloads)"),
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
    key_file: Optional[str] = typer.Option(None, "--key-file", help="Read passphrase from file (avoids shell history)"),
    require_v2: bool = typer.Option(False, "--require-v2", help="Only accept v2 method-bound payloads"),
    i_understand_root: bool = typer.Option(False, "--i-understand-root", help="Acknowledge live network covert ops authorization"),
):
    try:
        key = _read_key_file(key_file) or key
        _warn_argv_key()
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
            require_v2=require_v2,
            i_understand_root=i_understand_root,
        )
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_decode_result(result)
    except (OSError, ValueError) as e:
        if json_mode:
            print(json.dumps(error_payload(e)))
        else:
            print_error(e)
        raise typer.Exit(1) from None


@app.command("detect", help="Analyze a file for hidden content")
def cmd_detect(
    file:         Optional[str] = typer.Option(None, "-f", "--file", help="File to analyze (required unless --stdin)"),
    chi2:         bool = typer.Option(False, "--chi2",     help="Run chi-square LSB detector"),
    rs:           bool = typer.Option(False, "--rs",       help="Run RS analysis"),
    exif:         bool = typer.Option(False, "--exif",     help="Run EXIF/metadata scanner"),
    blind:        bool = typer.Option(False, "--blind",    help="Run blind brute-force extractor"),
    ml:           bool = typer.Option(False, "--ml",       help="Run ML steganalysis (uses the bundled ONNX model)"),
    fingerprint:  bool = typer.Option(False, "--fingerprint", help="Run PRNU inconsistency detector"),
    binary:       bool = typer.Option(False, "--binary",   help="Run ELF/PE binary slack anomaly detector"),
    all_detect:   bool = typer.Option(False, "--all",      help="Run all detectors"),
    json_mode:    bool = typer.Option(False, "--json",     help="Output JSON"),
    stdin:        bool = typer.Option(False, "--stdin",    help="Read file from stdin"),
    case_id: Optional[str] = typer.Option(None, "--case-id", help="Forensic case identifier for audit trail"),
):
    try:
        if stdin:
            data = sys.stdin.buffer.read()
            fd, tmpfile_path = tempfile.mkstemp(prefix="stegoforge_stdin_detect_", suffix=".bin")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                result = op_detect(tmpfile_path, chi2, rs, exif, blind, ml, fingerprint, binary, all_detect, json_mode, case_id)
            finally:
                Path(tmpfile_path).unlink(missing_ok=True)
        else:
            if not file:
                raise ValueError("Missing --file (or use --stdin to read from stdin)")
            result = op_detect(file, chi2, rs, exif, blind, ml, fingerprint, binary, all_detect, json_mode, case_id)
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_detect_results(result)
    except (OSError, ValueError) as e:
        if json_mode:
            print(json.dumps(error_payload(e)))
        else:
            print_error(e)
        raise typer.Exit(1) from None


@app.command("ctf", help="Run full CTF forensic analysis on a file")
def cmd_ctf(
    file:      Optional[str] = typer.Option(None, "-f", "--file",    help="Suspicious file to analyze (required unless --stdin/--batch)"),
    batch:     Optional[str] = typer.Option(None, "--batch", help="Directory to scan in batch mode"),
    json_mode: bool = typer.Option(False, "--json",        help="Output JSON"),
    stdin:     bool = typer.Option(False, "--stdin",       help="Read file from stdin"),
    no_save:   bool = typer.Option(False, "--no-save",     help="Do not write extracted payloads to disk (read-only triage)"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir", help="Directory for extracted payloads"),
    case_id: Optional[str] = typer.Option(None, "--case-id", help="Forensic case identifier for audit trail"),
):
    try:
        if batch:
            batch_dir = Path(batch)
            if not batch_dir.is_dir():
                raise OSError(f"Batch directory not found: {batch}")
            files = sorted(p for p in batch_dir.rglob("*") if p.is_file())
            all_results = []
            for f in files:
                if f.is_file():
                    try:
                        r = op_ctf(str(f), json_mode=True, save_payloads=not no_save, output_dir=output_dir, case_id=case_id)
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
                result = op_ctf(tmpfile_path, json_mode, save_payloads=not no_save, output_dir=output_dir, case_id=case_id)
                if json_mode:
                    print(json.dumps(result, indent=2))
                else:
                    print_ctf_report(result)
            finally:
                Path(tmpfile_path).unlink(missing_ok=True)
        else:
            if not file:
                raise ValueError("Missing --file (or use --stdin/--batch)")
            with console.status(
                f"[{C_INFO}]Running all detectors on {Path(file).name}...[/{C_INFO}]",
                spinner="dots2",
            ):
                result = op_ctf(file, json_mode, save_payloads=not no_save, output_dir=output_dir, case_id=case_id)
            if json_mode:
                print(json.dumps(result, indent=2))
            else:
                print_ctf_report(result)
    except (OSError, ValueError) as e:
        if json_mode:
            print(json.dumps(error_payload(e)))
        else:
            print_error(e)
        raise typer.Exit(1) from None


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
    except (OSError, ValueError) as e:
        if json_mode:
            print(json.dumps(error_payload(e)))
        else:
            print_error(e)
        raise typer.Exit(1) from None


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
    except (OSError, ValueError) as e:
        if json_mode:
            print(json.dumps(error_payload(e)))
        else:
            print_error(e)
        raise typer.Exit(1) from None


def _carrier_suffix(url: str) -> str:
    """File extension for a downloaded carrier, from the URL path; sanitised, never trusted as a path."""
    from urllib.parse import urlparse

    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", suffix) else ".bin"


def _unique_path(path: Path) -> Path:
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate


def _decode_downloaded(blob: bytes, url: str, key: str, output: str | None, method: str | None) -> dict:
    """Decode a downloaded carrier without leaving temp files behind.

    The payload goes to ``output`` or, if none was given, into the current directory
    (never next to a temporary file that is about to be deleted).
    """
    import tempfile

    with tempfile.TemporaryDirectory(prefix="stegoforge_deadrop_") as td:
        carrier = Path(td) / f"carrier{_carrier_suffix(url)}"
        carrier.write_bytes(blob)
        result = op_decode(str(carrier), key, output, method, False, True)
        if not output:
            dest = _unique_path(Path.cwd() / Path(result["output"]).name.replace("carrier_decoded", "deadrop_decoded"))
            shutil.move(result["output"], dest)
            result["output"] = str(dest)
        result["file"] = url
    return result


def _local_passphrase(value: str | None, *, confirm: bool) -> str:
    """The key-file passphrase: from the option if given (visible in `ps`), else a hidden prompt."""
    if value:
        print_warning("--local-passphrase on the command line is visible in the process list; omit it to be prompted.")
        return value
    return typer.prompt("Local passphrase (protects the private key file)", hide_input=True, confirmation_prompt=confirm)


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
    try:
        _deadrop_post(carrier, payload, key, output, method, upload_url, upload_method)
    except (ValueError, OSError) as e:
        print_error(e)
        raise typer.Exit(1) from None


def _deadrop_post(carrier, payload, key, output, method, upload_url, upload_method):
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
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Decoded payload output (default: current directory)"),
):
    from protocol.deadrop import fetch_url_bytes

    try:
        result = _decode_downloaded(fetch_url_bytes(url), url, key, output, method)
    except (ValueError, OSError) as e:
        print_error(e)
        raise typer.Exit(1) from None
    print_decode_result(result)


@deadrop_app.command("monitor", help="Poll URL and extract unseen dead-drop payloads")
def deadrop_monitor(
    url: str = typer.Option(..., "--url", help="Public URL hosting rotating carriers"),
    key: str = typer.Option(..., "-k", "--key", help="Shared channel key"),
    method: Optional[str] = typer.Option(None, "--method", help="Optional method hint"),
    interval: int = typer.Option(30, "--interval", help="Polling interval in seconds"),
):
    from protocol.deadrop import monitor_loop

    console.print(f"[{C_INFO}]Monitoring {url} every {interval}s... (Ctrl+C to stop)[/{C_INFO}]")

    def _on_new(blob: bytes, digest: str):
        try:
            result = _decode_downloaded(blob, url, key, None, method)
        except ValueError:
            console.print(f"[{C_DIM}]No payload extracted for hash {digest[:12]}...[/{C_DIM}]")
        except OSError as e:  # a full disk must be visible, and must not end the watch
            print_error(e)
        else:
            console.print(f"[{C_SUCCESS}]New payload extracted from hash {digest[:12]}... -> {result['output']}[/{C_SUCCESS}]")

    try:
        monitor_loop(url, interval, _on_new)
    except KeyboardInterrupt:
        console.print(f"\n[{C_DIM}]Stopped.[/{C_DIM}]")


@deadrop_keyx_app.command("initiate", help="Create local private key and embed X25519 public key in a carrier")
def deadrop_keyx_initiate(
    carrier: str = typer.Option(..., "-c", "--carrier", help="Carrier file"),
    output: str = typer.Option(..., "-o", "--output", help="Output stego carrier path"),
    private_key_file: str = typer.Option(".stegoforge_keyx.priv", "--private-key-file", help="Encrypted local private key file path"),
    local_passphrase: Optional[str] = typer.Option(None, "--local-passphrase", help="Passphrase protecting the private key file (prompted if omitted)"),
    method: Optional[str] = typer.Option(None, "--method", help="Embedding method"),
    depth: int = typer.Option(1, "--depth", help="Bit depth for LSB-like methods"),
    sign_key_file: Optional[str] = typer.Option(None, "--sign-key-file", help="Ed25519 signing private key file (raw 32B) for authenticated exchange"),
):
    """Security note: forward secrecy depends on keeping local private-key file and passphrase secure."""
    from protocol.keyexchange import generate_ephemeral_keypair, save_private_key_file, sign_exchange

    local_passphrase = _local_passphrase(local_passphrase, confirm=True)
    m = method or auto_detect_method(carrier)
    encoder = get_encoder(m)
    carrier_path = Path(carrier)
    carrier_bytes = carrier_path.read_bytes()
    priv_raw, pub_raw = generate_ephemeral_keypair()
    payload = bytes(pub_raw)
    if sign_key_file:
        sig = sign_exchange(Path(sign_key_file).read_bytes()[:32], pub_raw)
        payload = pub_raw + sig

    kwargs = {"depth": depth}
    ext = carrier_path.suffix.lower()
    if m in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
        kwargs["ext"] = ext
    if m in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(carrier_path)

    cap = encoder.capacity(carrier_bytes, **kwargs)
    if len(payload) > cap:
        raise typer.BadParameter(f"Carrier capacity too small for key exchange payload ({cap} bytes)")

    stego = encoder.encode(carrier_bytes, payload, **kwargs)
    Path(output).write_bytes(stego)
    save_private_key_file(private_key_file, priv_raw, local_passphrase)

    console.print(f"[{C_SUCCESS}]Key exchange initiate complete.[/{C_SUCCESS}]")
    console.print(f"[{C_INFO}]Public key embedded carrier: {output}[/{C_INFO}]")
    if sign_key_file:
        console.print(f"[{C_INFO}]Exchange signature embedded (Ed25519, verify with peer key).[/{C_INFO}]")
    console.print(f"[{C_WARN}]Security note:[/{C_WARN}] protect local passphrase/private key file; compromise breaks session secrecy.")


@deadrop_keyx_app.command("complete", help="Extract peer public key and derive shared session key")
def deadrop_keyx_complete(
    received_file: str = typer.Option(..., "-f", "--file", help="Received stego carrier containing peer public key"),
    private_key_file: str = typer.Option(".stegoforge_keyx.priv", "--private-key-file", help="Encrypted local private key file path"),
    local_passphrase: Optional[str] = typer.Option(None, "--local-passphrase", help="Passphrase protecting the private key file (prompted if omitted)"),
    method: Optional[str] = typer.Option(None, "--method", help="Method hint"),
    output_key_file: Optional[str] = typer.Option(None, "--output-key-file", help="Optional file to save derived session key"),
    verify_key_file: Optional[str] = typer.Option(None, "--verify-key-file", help="Ed25519 peer verify key file (raw 32B) for authenticated exchange"),
    peer_pub_file: Optional[str] = typer.Option(None, "--peer-pub-file", help="Save extracted peer public key (32B) for v2 binding audit"),
    legacy_v1: bool = typer.Option(False, "--legacy-v1", help="Derive the session key exactly as StegoForge <= 1.1.5 did, to match a peer that has not upgraded"),
):
    """Security note: X25519 provides forward secrecy, but carrier secrecy still matters."""
    from protocol.keyexchange import (
        load_private_key_file,
        derive_shared_secret,
        derive_session_key_hex_1_1_5,
        derive_session_key_hex_v2,
        verify_exchange,
    )

    file_path = Path(received_file)
    data = file_path.read_bytes()
    ext = file_path.suffix.lower()

    methods = [method] if method else []
    if not methods:
        suggested = auto_detect_method(received_file)
        methods = [suggested]

    peer_pub = None
    peer_sig = None
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
                if len(raw) == 96:
                    # Signed exchange: pub(32) + sig(64)
                    peer_pub, peer_sig = raw[:32], raw[32:]
                    break
            except Exception:
                continue
        if peer_pub is not None:
            break

    if peer_pub is None:
        raise typer.BadParameter("Failed to extract 32-byte peer X25519 public key from carrier")

    if verify_key_file:
        if peer_sig is None:
            raise typer.BadParameter("No exchange signature found in carrier (--verify-key-file requires signed initiate)")
        verify_exchange(Path(verify_key_file).read_bytes()[:32], peer_sig, peer_pub)
        console.print(f"[{C_SUCCESS}]Exchange signature verified.[/{C_SUCCESS}]")

    local_passphrase = _local_passphrase(local_passphrase, confirm=False)
    try:
        priv_raw = load_private_key_file(private_key_file, local_passphrase)
    except (ValueError, OSError) as e:
        print_error(e)
        raise typer.Exit(1) from None
    shared = derive_shared_secret(priv_raw, peer_pub)
    if legacy_v1:
        print_warning("Using the StegoForge <= 1.1.5 session key: it is not bound to both public keys. Use it only to talk to a peer that has not upgraded.")
        session_key = derive_session_key_hex_1_1_5(shared)
    else:
        from protocol.keyexchange import public_from_private

        session_key = derive_session_key_hex_v2(shared, public_from_private(priv_raw), peer_pub)

    if peer_pub_file:
        Path(peer_pub_file).write_bytes(peer_pub)
    if output_key_file:
        fd = os.open(output_key_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(session_key)
        console.print(f"[{C_SUCCESS}]Derived session key saved to {output_key_file} (0600)[/{C_SUCCESS}]")
    else:
        console.print(f"[{C_WARN}]Session key printed to console — prefer --output-key-file (0600).[/{C_WARN}]")
        console.print(f"[{C_SUCCESS}]Derived session key:[/{C_SUCCESS}] {session_key}")

    console.print(
        f"[{C_WARN}]Security note:[/{C_WARN}] X25519 gives forward secrecy, but carriers must remain plausibly innocuous to passive observers."
    )


@app.command("web", help="Launch the local web UI")
def cmd_web(
    port: int = typer.Option(5000, "--port", help="Port to bind (default: 5000)"),
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to bind; anything but loopback requires STEGOFORGE_WEB_TOKEN"),
    skip_banner: bool = typer.Option(False, "--skip-banner", help="Skip printing the banner"),
):
    if host not in ("127.0.0.1", "localhost", "::1") and not os.getenv("STEGOFORGE_WEB_TOKEN"):
        print_error(
            f"Refusing to listen on {host} without authentication.",
            "Set STEGOFORGE_WEB_TOKEN=<secret> (or =auto to generate one) and open the UI as http://HOST:PORT/?token=<secret>.",
        )
        raise typer.Exit(1)
    if not skip_banner:
        print_banner()
    try:
        from web.app import create_app
        flask_app = create_app()
        shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
        console.print(f"[{C_SUCCESS}]✓ Web UI running at http://{shown}:{port}[/{C_SUCCESS}]")
        console.print(f"[{C_DIM}]All files processed locally. Nothing is uploaded to any server.[/{C_DIM}]")
        flask_app.run(host=host, port=port, debug=False)
    except ImportError:
        print_error("Web dependencies not installed.", "Run: pip install 'stegoforge[web]'  (or: pip install flask flask-cors)")
        raise typer.Exit(1) from None
    except (ValueError, OSError) as e:
        print_error(f"Failed to start web UI: {e}")
        raise typer.Exit(1) from None


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
    except (OSError, ValueError) as e:
        if json_mode:
            print(json.dumps(error_payload(e)))
        else:
            print_error(e)
        raise typer.Exit(1) from None


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
    jobs:       int            = typer.Option(1,        "--jobs",      help="Parallel workers for batch encode (1=sequential)"),
):
    """
    Walks a directory and embeds the same payload into every supported carrier file.
    Supported formats: PNG, BMP, TIFF, WEBP, JPG, GIF, WAV, MP3, FLAC, OGG, MP4,
    WEBM, PDF, DOCX, XLSX, TXT (see EXT_TO_METHOD; MKV/AVI are not carriers).

    Each output file is named <original>_stego.<ext> and saved alongside the original
    (or in --output if specified).

    Examples:
      stegoforge batch -d ./images/ -p secret.txt -k mykey
      stegoforge batch -d ./carriers/ -p msg.pdf -k mykey -o ./out/ --depth 2 --json
    """
    try:
        result = op_batch_encode(batch_dir, payload, key, output_dir, method, depth, wet_paper, jobs=jobs)
        if json_mode:
            print(json.dumps(result, indent=2))
        else:
            print_batch_result(result)
    except (OSError, ValueError) as e:
        if json_mode:
            print(json.dumps(error_payload(e)))
        else:
            print_error(e)
        raise typer.Exit(1) from None


def _schema_text(filename: str) -> str:
    """Read a bundled schema file (package data: present in a checkout, a wheel, the .deb and the binary)."""
    from importlib import resources

    return resources.files("stegoforge_ops").joinpath("schemas", filename).read_text(encoding="utf-8")


@app.command("schema", help="Print JSON output schemas for --json modes")
def cmd_schema(
    name: str = typer.Argument("all", help="Schema name: all|encode|decode|detect|ctf|capacity|diff|batch"),
    json_out: bool = typer.Option(False, "--json", help="Print the machine-readable JSON Schema"),
):
    """Print --json schemas (human markdown by default, JSON Schema with --json)."""
    if json_out:
        text = _schema_text("json-schema.json")
        if name in ("all", ""):
            print(text)
            return
        node = json.loads(text).get("definitions", {}).get(name)
        if node is None:
            print(json.dumps({"status": "error", "message": f"Unknown schema: {name}"}))
            raise typer.Exit(1)
        print(json.dumps(node, indent=2))
        return
    text = _schema_text("JSON-SCHEMA.md")
    if name in ("all", ""):
        print(text)
        return
    section = f"## {name}".lower()
    if section in text.lower():
        start = text.lower().index(section)
        print(text[start:start + 2000])
    else:
        print_error(f"Unknown schema: {name}", "Choose one of: all, encode, decode, detect, ctf, capacity, diff, batch.")
        raise typer.Exit(1)


@app.command("completion", help="Print shell completion script for bash, zsh, or fish")
def cmd_completion(
    shell: str = typer.Argument("bash", help="Shell type: bash | zsh | fish"),
):
    """
    Prints a shell completion script, generated from the live command tree.

    Usage:
      # bash (add to ~/.bashrc):
      eval "$(stegoforge completion bash)"

      # zsh: save it on your fpath and reload completions
      stegoforge completion zsh > "${fpath[1]}/_stegoforge" && compinit

      # fish:
      stegoforge completion fish | source
    """
    import typer.main

    from stegoforge_ops.completion import GENERATORS

    generator = GENERATORS.get(shell.lower())
    if generator is None:
        print_error(f"Unknown shell '{shell}'.", "Use one of: bash, zsh, fish.")
        raise typer.Exit(1)
    print(generator(typer.main.get_command(app)))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    app()
