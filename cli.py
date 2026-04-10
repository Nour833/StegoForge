#!/usr/bin/env python3
"""
cli.py — StegoForge CLI

Animated ASCII banner, interactive menu, and direct bypass arguments.
All features accessible both interactively and via direct args.
"""
import json
import os
import sys
import time
import io
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
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
    "Hide in Images  ·  Hide in Audio  ·  Hide in Documents",
    "Detect What Others Hide  ·  Survive Forensics",
    "AES-256-GCM  ·  Argon2id  ·  Polymorphic Embedding",
    "Chi-Square  ·  RS Analysis  ·  EXIF Forensics  ·  Blind Extraction",
    "CTF-Ready  ·  Pipe-Friendly  ·  JSON Output  ·  Zero Compromise",
]


def print_banner():
    """Print the animated StegoForge banner."""
    # Gradient banner colors cycling
    banner_text = Text(BANNER)
    banner_text.stylize("bold bright_cyan", 0, len(BANNER) // 3)
    banner_text.stylize("bold cyan", len(BANNER) // 3, 2 * len(BANNER) // 3)
    banner_text.stylize("bold blue", 2 * len(BANNER) // 3)

    console.print(banner_text)

    # Animated tagline
    tagline = TAGLINES[int(time.time()) % len(TAGLINES)]
    console.print(f"  [dim cyan]❯[/dim cyan] [italic bright_white]{tagline}[/italic bright_white]\n")

    # Version + stats bar
    info_text = (
        f"[{C_DIM}]v1.0.0  ·  12 encoding methods  ·  "
        f"4 detection engines  ·  AES-256-GCM  ·  CTF-Ready[/{C_DIM}]"
    )
    console.print(f"  {info_text}\n")


# ── Method registry ───────────────────────────────────────────────────────────
ENCODE_METHODS = {
    "lsb":          ("Image",    "LSB — Least Significant Bit in image pixels (PNG/BMP)"),
    "dct":          ("Image",    "DCT — Frequency domain injection (JPEG)"),
    "alpha":        ("Image",    "Alpha — Hide in transparency channel (PNG/WebP)"),
    "palette":      ("Image",    "Palette — GIF/indexed PNG color reordering"),
    "audio-lsb":    ("Audio",    "Audio LSB — PCM sample bit manipulation (WAV/FLAC)"),
    "phase":        ("Audio",    "Phase — Segment phase coding, MP3-tolerant"),
    "spectrogram":  ("Audio",    "Spectrogram — Embed visible image/text in audio spectrum"),
    "unicode":      ("Document", "Unicode — Zero-width character encoding (TXT)"),
    "pdf":          ("Document", "PDF — Stream/metadata injection (PDF)"),
    "docx":         ("Document", "DOCX — Custom XML stream injection (DOCX)"),
    "xlsx":         ("Document", "XLSX — Custom XML stream injection (XLSX)"),
}

DECODE_METHODS = {k: v for k, v in ENCODE_METHODS.items()}

EXT_TO_METHOD = {
    ".png":  "lsb", ".bmp": "lsb", ".tiff": "lsb",
    ".jpg":  "dct", ".jpeg": "dct",
    ".gif":  "palette",
    ".wav":  "audio-lsb", ".flac": "audio-lsb",
    ".mp3":  "phase", ".ogg": "phase",
    ".txt":  "unicode",
    ".pdf":  "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".webp": "alpha",
}


def auto_detect_method(filepath: str) -> str:
    ext = Path(filepath).suffix.lower()
    return EXT_TO_METHOD.get(ext, "lsb")


def get_encoder(method: str):
    """Return encoder instance for given method name."""
    if method == "lsb":
        from core.image.lsb import LSBEncoder
        return LSBEncoder()
    elif method == "dct":
        from core.image.dct import DCTEncoder
        return DCTEncoder()
    elif method == "alpha":
        from core.image.alpha import AlphaEncoder
        return AlphaEncoder()
    elif method == "palette":
        from core.image.palette import PaletteEncoder
        return PaletteEncoder()
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
    elif method == "pdf":
        from core.document.pdf import PDFEncoder
        return PDFEncoder()
    elif method in ("docx", "xlsx", "office"):
        from core.document.office import OfficeEncoder
        return OfficeEncoder()
    else:
        raise ValueError(f"Unknown method: {method}")


def get_output_path(carrier_path: str, output: str | None, suffix: str = "_stego") -> Path:
    p = Path(carrier_path)
    if output:
        return Path(output)
    return p.with_stem(p.stem + suffix)


# ── Core operation helpers ────────────────────────────────────────────────────

def op_encode(
    carrier: str,
    payload: str,
    key: str,
    output: str | None,
    method: str | None,
    depth: int,
    decoy: str | None,
    decoy_key: str | None,
    json_mode: bool,
) -> dict:
    carrier_path = Path(carrier)
    payload_path = Path(payload)

    if not carrier_path.exists():
        raise IOError(f"Carrier file not found: {carrier}")
    if not payload_path.exists():
        raise IOError(f"Payload file not found: {payload}")

    carrier_bytes = carrier_path.read_bytes()
    payload_bytes = payload_path.read_bytes()

    method = method or auto_detect_method(carrier)
    encoder = get_encoder(method)

    # Encrypt payload
    from core.crypto import aes
    if decoy and decoy_key:
        from core.crypto import decoy as decoy_mod
        decoy_payload = Path(decoy).read_bytes()
        decoy_enc = aes.encrypt(decoy_payload, decoy_key)
        real_enc = aes.encrypt(payload_bytes, key)
        embed_bytes = decoy_mod.SEPARATOR.join([decoy_enc, real_enc])
        # Actually use proper dual encode
        embed_bytes = decoy_mod.encode_dual(decoy_payload, decoy_key, payload_bytes, key)
    else:
        embed_bytes = aes.encrypt(payload_bytes, key)

    # Build kwargs before capacity check so audio ext is included
    ext = carrier_path.suffix.lower()
    kwargs = {"depth": depth, "key": key}
    if method in ("audio-lsb", "phase", "spectrogram"):
        kwargs["ext"] = ext
    if method in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(carrier_path)

    # Capacity check — pass same kwargs so audio encoders receive ext
    cap_kwargs = {k: v for k, v in kwargs.items() if k != "key"}  # capacity doesn't need key
    cap = encoder.capacity(carrier_bytes, **cap_kwargs)
    if len(embed_bytes) > cap:
        raise ValueError(
            f"Encrypted payload too large: {len(embed_bytes)} bytes, "
            f"method '{method}' capacity: {cap} bytes.\n"
            f"Try: smaller payload, larger carrier, or higher --depth."
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
    }
    return result


def op_decode(
    file: str,
    key: str,
    output: str | None,
    method: str | None,
    json_mode: bool,
) -> dict:
    file_path = Path(file)
    if not file_path.exists():
        raise IOError(f"File not found: {file}")

    stego_bytes = file_path.read_bytes()
    method = method or auto_detect_method(file)
    encoder = get_encoder(method)

    ext = file_path.suffix.lower()
    kwargs = {"key": key}
    if method in ("audio-lsb", "phase", "spectrogram"):
        kwargs["ext"] = ext
    if method in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(file_path)

    # Guess depth — try 1 first, fallback to higher if we got data
    for depth in [1, 2, 3, 4]:
        try:
            kwargs["depth"] = depth
            raw_bytes = encoder.decode(stego_bytes, **kwargs)
            break
        except ValueError:
            if depth == 4:
                raise
            continue

    # Decrypt
    from core.crypto import aes, decoy as decoy_mod
    try:
        payload = decoy_mod.decode_dual(raw_bytes, key)
    except ValueError:
        try:
            payload = aes.decrypt(raw_bytes, key)
        except ValueError:
            raise ValueError("Decryption failed — wrong key or no encrypted payload found")

    # Save output
    if output:
        out_path = Path(output)
    else:
        stem = file_path.stem.replace("_stego", "")
        out_path = file_path.with_stem(stem + "_decoded")

    out_path.write_bytes(payload)

    result = {
        "status": "success",
        "method": method,
        "file": str(file_path),
        "payload_size": len(payload),
        "output": str(out_path),
    }
    return result


def op_detect(
    file: str,
    chi2: bool,
    rs: bool,
    exif: bool,
    blind: bool,
    all_detectors: bool,
    json_mode: bool,
) -> dict:
    file_path = Path(file)
    if not file_path.exists():
        raise IOError(f"File not found: {file}")

    file_bytes = file_path.read_bytes()
    filename = file_path.name
    results = []

    if chi2 or all_detectors:
        from detect.chi2 import Chi2Detector
        results.append(Chi2Detector().analyze(file_bytes, filename))
    if rs or all_detectors:
        from detect.rs import RSDetector
        results.append(RSDetector().analyze(file_bytes, filename))
    if exif or all_detectors:
        from detect.exif import EXIFDetector
        results.append(EXIFDetector().analyze(file_bytes, filename))
    if blind or all_detectors:
        from detect.blind import BlindExtractor
        results.append(BlindExtractor().analyze(file_bytes, filename))

    if not results:
        # Default: run all
        from detect.chi2 import Chi2Detector
        from detect.rs import RSDetector
        from detect.exif import EXIFDetector
        from detect.blind import BlindExtractor
        results = [
            Chi2Detector().analyze(file_bytes, filename),
            RSDetector().analyze(file_bytes, filename),
            EXIFDetector().analyze(file_bytes, filename),
            BlindExtractor().analyze(file_bytes, filename),
        ]

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

    from detect.chi2 import Chi2Detector
    from detect.rs import RSDetector
    from detect.exif import EXIFDetector
    from detect.blind import BlindExtractor

    detectors = [Chi2Detector(), RSDetector(), EXIFDetector(), BlindExtractor()]
    results = []
    for det in detectors:
        results.append(det.analyze(file_bytes, filename))

    # Save extracted payloads from blind extractor
    saved_files = []
    for r in results:
        if r.extracted_payload and r.method == "blind":
            save_path = file_path.parent / f"extracted_{file_path.stem}.bin"
            save_path.write_bytes(r.extracted_payload)
            saved_files.append(str(save_path))

    overall_confidence = max((r.confidence for r in results), default=0.0)
    any_detected = any(r.detected for r in results)

    return {
        "status": "success",
        "file": str(file_path),
        "file_size": file_size,
        "overall_verdict": "STEGO DETECTED" if any_detected else "CLEAN",
        "overall_confidence": round(overall_confidence, 4),
        "results": [_result_to_dict(r) for r in results],
        "saved_payloads": saved_files,
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
    if method in ("audio-lsb", "phase", "spectrogram"):
        kwargs["ext"] = ext
    if method in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(carrier_path)

    cap = encoder.capacity(carrier_bytes, **kwargs)

    return {
        "status": "success",
        "carrier": str(carrier_path),
        "method": method,
        "depth": depth,
        "capacity_bytes": cap,
        "capacity_kb": round(cap / 1024, 2),
        "capacity_mb": round(cap / (1024 * 1024), 4),
    }


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
    console.print(Panel(panel_content, title=f"[{C_TITLE}]StegoForge — Encode Result[/{C_TITLE}]",
                        border_style="cyan", padding=(1, 2)))


def print_decode_result(result: dict):
    panel_content = (
        f"[{C_SUCCESS}]✓ Payload successfully extracted & decrypted[/{C_SUCCESS}]\n\n"
        f"  [dim]Method    :[/dim]  [{C_ACCENT}]{result['method'].upper()}[/{C_ACCENT}]\n"
        f"  [dim]Input     :[/dim]  {result['file']}\n"
        f"  [dim]Output    :[/dim]  [{C_SUCCESS}]{result['output']}[/{C_SUCCESS}]\n"
        f"  [dim]Payload   :[/dim]  {result['payload_size']:,} bytes"
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

    if report["saved_payloads"]:
        console.print(f"\n[{C_SUCCESS}]Extracted payloads saved:[/{C_SUCCESS}]")
        for path in report["saved_payloads"]:
            console.print(f"  [{C_ACCENT}]→[/{C_ACCENT}] {path}")


def print_capacity_result(result: dict):
    panel_content = (
        f"  [dim]Carrier  :[/dim] {result['carrier']}\n"
        f"  [dim]Method   :[/dim] [{C_ACCENT}]{result['method'].upper()}[/{C_ACCENT}]\n"
        f"  [dim]Depth    :[/dim] {result['depth']} bit(s)\n\n"
        f"  [{C_SUCCESS}]Capacity:[/{C_SUCCESS}]\n"
        f"    [{C_GOLD}]{result['capacity_bytes']:>12,}[/{C_GOLD}] bytes\n"
        f"    [{C_GOLD}]{result['capacity_kb']:>12.2f}[/{C_GOLD}] KB\n"
        f"    [{C_GOLD}]{result['capacity_mb']:>12.4f}[/{C_GOLD}] MB"
    )
    console.print(Panel(panel_content, title=f"[{C_TITLE}]StegoForge — Capacity Check[/{C_TITLE}]",
                        border_style="yellow", padding=(1, 2)))


def _print_single_result(r: dict):
    detected = r["detected"]
    confidence_pct = int(r["confidence"] * 100)
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

    details = r.get("details", {})
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
    elif r["method"] == "blind":
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
    console.print(f"\n  [dim]Available methods:[/dim]")
    auto_method = auto_detect_method(carrier)
    for i, (m, (cat, desc)) in enumerate(ENCODE_METHODS.items(), 1):
        marker = f"[{C_SUCCESS}] ✓ auto[/{C_SUCCESS}]" if m == auto_method else ""
        console.print(f"    [{C_DIM}]{i:2}.[/{C_DIM}] [{C_ACCENT}]{m:12}[/{C_ACCENT}] {desc} {marker}")

    method_input = Prompt.ask(
        f"\n  [{C_ACCENT}]Method[/{C_ACCENT}] (name or number, Enter for auto)",
        default=auto_method,
    )
    # Resolve numeric input
    method_names = list(ENCODE_METHODS.keys())
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
        result = op_encode(carrier, payload, key, output or None, method, depth, decoy, decoy_key, False)
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
        result = op_decode(file, key, output or None, method_input or None, False)
    print_decode_result(result)


def interactive_detect():
    """Interactive detect wizard."""
    console.print(f"\n[{C_TITLE}]── DETECT ──────────────────────────────────────[/{C_TITLE}]")
    file = Prompt.ask(f"  [{C_ACCENT}]File to analyze[/{C_ACCENT}] (path)")
    console.print(f"  [{C_DIM}]Detectors: chi2, rs, exif, blind, all[/{C_DIM}]")
    which = Prompt.ask(f"  [{C_ACCENT}]Detectors to run[/{C_ACCENT}]", default="all")

    chi2_flag = "chi2" in which or which == "all"
    rs_flag = "rs" in which or which == "all"
    exif_flag = "exif" in which or which == "all"
    blind_flag = "blind" in which or which == "all"

    console.print()
    with console.status(f"[{C_INFO}]Analyzing file...[/{C_INFO}]", spinner="dots"):
        result = op_detect(file, chi2_flag, rs_flag, exif_flag, blind_flag, which == "all", False)
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


def interactive_menu():
    """Main interactive menu."""
    print_banner()

    menu_items = [
        ("[bold cyan]1[/bold cyan]", "Encode",    "Embed a secret payload in any carrier"),
        ("[bold cyan]2[/bold cyan]", "Decode",    "Extract & decrypt a hidden payload"),
        ("[bold cyan]3[/bold cyan]", "Detect",    "Analyze a file for hidden content"),
        ("[bold cyan]4[/bold cyan]", "CTF Mode",  "Run all detectors, get full forensic report"),
        ("[bold cyan]5[/bold cyan]", "Capacity",  "Check how much data a carrier can hold"),
        ("[bold cyan]6[/bold cyan]", "Web UI",    "Launch the local web interface"),
        ("[bold cyan]q[/bold cyan]", "Quit",      "Exit StegoForge"),
    ]

    table = Table(box=box.ROUNDED, show_header=False, border_style="cyan", padding=(0, 2))
    table.add_column("Key",  style="bold cyan",  width=4)
    table.add_column("Action", style="bold white", width=12)
    table.add_column("Description", style="dim")

    for key, action, desc in menu_items:
        table.add_row(key, action, desc)

    console.print(table)

    while True:
        choice = Prompt.ask(f"\n  [{C_TITLE}]Command[/{C_TITLE}]").strip().lower()

        try:
            if choice == "1" or choice == "encode":
                interactive_encode()
            elif choice == "2" or choice == "decode":
                interactive_decode()
            elif choice == "3" or choice == "detect":
                interactive_detect()
            elif choice == "4" or choice == "ctf":
                interactive_ctf()
            elif choice == "5" or choice == "capacity":
                interactive_capacity()
            elif choice == "6" or choice == "web":
                console.print(f"[{C_INFO}]Starting web UI...[/{C_INFO}]")
                _launch_web()
                break
            elif choice in ("q", "quit", "exit"):
                console.print(f"[{C_DIM}]Goodbye.[/{C_DIM}]")
                raise typer.Exit()
            else:
                console.print(f"[{C_WARN}]Unknown command. Type 1-6 or q.[/{C_WARN}]")
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
    import subprocess
    import sys
    venv_python = Path(__file__).parent / "venv" / "bin" / "python"
    py = str(venv_python) if venv_python.exists() else sys.executable
    subprocess.Popen([py, "-m", "web.app", "--port", str(port)])
    console.print(f"[{C_SUCCESS}]Web UI launched at http://localhost:{port}[/{C_SUCCESS}]")


# ── Typer commands ────────────────────────────────────────────────────────────

@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context):
    """StegoForge — The most complete open-source steganography toolkit."""
    if ctx.invoked_subcommand is None:
        interactive_menu()


@app.command("encode", help="Embed a payload into a carrier file")
def cmd_encode(
    carrier:   str  = typer.Option(..., "-c", "--carrier",   help="Path to carrier file"),
    payload:   str  = typer.Option(..., "-p", "--payload",   help="Path to payload file"),
    key:       str  = typer.Option(..., "-k", "--key",       help="Encryption passphrase"),
    output:    Optional[str] = typer.Option(None, "-o", "--output",  help="Output path (auto if omitted)"),
    method:    Optional[str] = typer.Option(None,       "--method",  help="Encoding method (auto-detected from extension)"),
    depth:     int  = typer.Option(1,    "--depth",     help="Bit depth 1-4 (higher = more capacity, less invisible)"),
    decoy:     Optional[str] = typer.Option(None,       "--decoy",   help="Decoy payload file (enables dual-payload mode)"),
    decoy_key: Optional[str] = typer.Option(None,       "--decoy-key", help="Key for decoy payload"),
    json_mode: bool = typer.Option(False, "--json",      help="Output JSON instead of formatted text"),
):
    try:
        result = op_encode(carrier, payload, key, output, method, depth, decoy, decoy_key, json_mode)
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
    key:       str  = typer.Option(..., "-k", "--key",    help="Decryption passphrase"),
    output:    Optional[str] = typer.Option(None, "-o", "--output", help="Output path (auto if omitted)"),
    method:    Optional[str] = typer.Option(None,       "--method", help="Encoding method (auto-detected if omitted)"),
    json_mode: bool = typer.Option(False, "--json",     help="Output JSON"),
):
    try:
        result = op_decode(file, key, output, method, json_mode)
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
    all_detect:   bool = typer.Option(False, "--all",      help="Run all detectors"),
    json_mode:    bool = typer.Option(False, "--json",     help="Output JSON"),
    stdin:        bool = typer.Option(False, "--stdin",    help="Read file from stdin"),
):
    try:
        if stdin:
            data = sys.stdin.buffer.read()
            tmpfile = Path("/tmp/stegoforge_stdin_detect.bin")
            tmpfile.write_bytes(data)
            result = op_detect(str(tmpfile), chi2, rs, exif, blind, all_detect, json_mode)
        else:
            result = op_detect(file, chi2, rs, exif, blind, all_detect, json_mode)
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
            tmpfile = Path("/tmp/stegoforge_stdin_ctf.bin")
            tmpfile.write_bytes(data)
            result = op_ctf(str(tmpfile), json_mode)
            if json_mode:
                print(json.dumps(result, indent=2))
            else:
                print_ctf_report(result)
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


@app.command("web", help="Launch the local web UI")
def cmd_web(
    port: int = typer.Option(5000, "--port", help="Port to bind (default: 5000)"),
):
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


if __name__ == "__main__":
    app()
