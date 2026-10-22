"""stegoforge_ops.ui — shared consoles, palette and renderers for every CLI command.

The palette matches the web UI (warm graphite, one amber accent; green and red only
for status). Everything dynamic — file names, exception text, detector notes — goes
through ``Text`` objects, never into markup strings: a path or an error message
containing ``[`` must not be interpreted as Rich markup.

Diagnostics and errors go to **stderr** so ``--json`` and piped stdout stay clean.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from rich import box
from rich.console import Console
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

console = Console()
# Warnings and diagnostics go to stderr so `--json` stdout stays machine-readable.
err_console = Console(stderr=True)

ACCENT = "#d6a243"
OK = "#7db38a"
BAD = "#d9705f"
MUTED = "#8d8676"

C_TITLE = f"bold {ACCENT}"
C_ACCENT = ACCENT
C_SUCCESS = f"bold {OK}"
C_WARN = f"bold {ACCENT}"
C_ERROR = f"bold {BAD}"
C_INFO = "#b0a999"
C_DIM = "dim"
C_GOLD = ACCENT
C_PURPLE = ACCENT

DETECTOR_NAMES = {
    "chi2": "Chi-square", "rs": "RS analysis", "exif": "Metadata", "blind": "Blind extractor", "blind-audio": "Blind (audio)",
    "ml": "ML", "fingerprint": "Camera fingerprint", "binary": "Binary", "video-anomaly": "Video",
    "audio-anomaly": "Audio", "pdf-anomaly": "PDF", "document-anomaly": "Document",
}

# What to try next, keyed by the stable error code of StegoForgeError subclasses.
ERROR_HINTS: dict[str, str] = {
    "decryption-failed": "Check the passphrase. If you know how the file was made, pass --method to skip auto-detection.",
    "plaintext-refused": "Pass -k/--key (or --key-file, or STEGOFORGE_KEY), or --allow-plaintext to embed without encryption.",
    "weak-passphrase": "Use at least 12 characters that mix letters, digits and symbols.",
    "empty-payload": "The payload file has no bytes; there is nothing to hide.",
    "corrupted-carrier": "The file may be damaged, truncated, or not the format its extension claims.",
    "bad-depth": "Use a bit depth between 1 and 4.",
    "bad-network-args": "Check the address and port arguments.",
}


# ── errors ────────────────────────────────────────────────────────────────────

def error_payload(exc: BaseException) -> dict[str, str]:
    """The ``--json`` form of an error: a message plus, when known, a stable machine-readable code."""
    payload = {"status": "error", "message": str(exc)}
    code = getattr(exc, "code", None)
    if code and code != "stegoforge-error":
        payload["code"] = code
    return payload


def print_error(error: BaseException | str, hint: str | None = None) -> None:
    """One line on stderr, plus a dim next step when we know one."""
    message = str(error)
    hint = hint or ERROR_HINTS.get(getattr(error, "code", ""))
    err_console.print(Text.assemble(("error ", C_ERROR), message))
    if hint:
        err_console.print(Text.assemble(("hint  ", MUTED), (hint, "dim")))


def print_warning(message: str) -> None:
    err_console.print(Text.assemble(("warning ", C_WARN), message))


# ── building blocks ───────────────────────────────────────────────────────────

def headline(ok: bool, text: str) -> Text:
    glyph, style = ("✓", C_SUCCESS) if ok else ("✗", C_ERROR)
    return Text.assemble((f"{glyph} ", style), (text, "bold"))


def kv_grid(rows: Iterable[tuple[str, Any]]) -> Table:
    """Aligned ``key  value`` lines. Values may be ``Text`` (styled) or anything printable (shown as text)."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style=MUTED, no_wrap=True)
    grid.add_column(overflow="fold")
    for key, value in rows:
        if value is None or value == "":
            continue
        grid.add_row(key, value if isinstance(value, Text) else Text(str(value)))
    return grid


def print_result(title: Text, rows: Iterable[tuple[str, Any]], notes: Sequence[Text] = ()) -> None:
    console.print(title)
    console.print(Padding(kv_grid(rows), (0, 0, 0, 2), expand=False))
    for note in notes:
        console.print(Padding(note, (0, 0, 0, 2), expand=False))


def meter(value: float, width: int = 14, *, higher_is_better: bool = False) -> Text:
    """A bar for a 0..1 value. For a detector signal high is bad; for a stealth score high is good."""
    value = max(0.0, min(1.0, value))
    filled = round(value * width)
    if higher_is_better:
        tone = OK if value >= 0.75 else ACCENT if value >= 0.45 else BAD
    else:
        tone = BAD if value > 0.70 else ACCENT if value > 0.30 else OK
    return Text.assemble(("█" * filled, tone), ("░" * (width - filled), "dim"))


def fmt_bytes(n: float) -> str:
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} B" if unit == "B" else f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# ── detector results ──────────────────────────────────────────────────────────

def detector_state(result: dict) -> str:
    """``skipped`` / ``detected`` / ``inconclusive`` / ``clean`` — an unsure detector is never "clean"."""
    details = result.get("details", {}) or {}
    if details.get("skipped"):
        return "skipped"
    if result.get("detected"):
        return "detected"
    if details.get("reliable") is False or details.get("inconclusive"):
        return "inconclusive"
    return "clean"


_CHIPS = {
    "skipped": ("SKIPPED", "dim"),
    "detected": ("DETECTED", f"bold {BAD}"),
    "inconclusive": ("INCONCLUSIVE", ACCENT),
    "clean": ("CLEAN", OK),
}


def detector_table(results: Sequence[dict]) -> Table:
    table = Table(box=box.SIMPLE_HEAD, show_edge=False, pad_edge=False, header_style=MUTED, padding=(0, 2, 0, 0))
    table.add_column("Detector", no_wrap=True)
    table.add_column("Result", no_wrap=True)
    table.add_column("Signal", no_wrap=True)
    table.add_column("Note", overflow="fold", ratio=1)
    for r in results:
        state = detector_state(r)
        label, style = _CHIPS[state]
        confidence = float(r.get("confidence", 0.0))
        if state in ("skipped", "inconclusive"):
            signal = Text("–", style="dim")
        else:
            signal = Text.assemble(meter(confidence), (f" {round(confidence * 100):>3d}%", "dim"))
        note = (r.get("details", {}) or {}).get("interpretation", "")
        name = DETECTOR_NAMES.get(r.get("method", ""), str(r.get("method", "")).upper())
        table.add_row(Text(name, style="bold"), Text(label, style=style), signal, Text(str(note), style="dim"))
    return table


def detector_details(results: Sequence[dict]) -> list[Text]:
    """Evidence worth reading in full: metadata findings, blind-extractor hits, extracted payloads."""
    lines: list[Text] = []
    for r in results:
        method = r.get("method", "")
        details = r.get("details", {}) or {}
        name = DETECTOR_NAMES.get(method, method.upper())
        if detector_state(r) != "detected" and method in ("chi2", "rs"):
            continue  # numbers for a clean result are noise; show them when they are the evidence
        if method == "chi2" and "p_value" in details:
            lines.append(Text.assemble((f"{name:<20}", MUTED), f"p = {details['p_value']:.4f}   χ² = {details.get('chi2_statistic', 0):.2f}"))
        elif method == "rs" and "estimated_payload_fraction" in details:
            lines.append(Text.assemble((f"{name:<20}", MUTED), f"~{details['estimated_payload_fraction'] * 100:.1f}% of pixels look modified"))
        elif method == "exif":
            for finding in (r.get("findings") or [])[:5]:
                glyph = {"high": ("▲", BAD), "medium": ("●", ACCENT)}.get(finding.get("suspicion"), ("·", MUTED))
                lines.append(Text.assemble((f"{name:<20}", MUTED), (glyph[0] + " ", glyph[1]),
                                           f"{finding.get('field', '')}: {str(finding.get('description', ''))[:80]}"))
        elif method in ("blind", "blind-audio"):
            for cand in (details.get("candidates") or [])[:3]:
                lines.append(Text.assemble((f"{name:<20}", MUTED), ("● ", ACCENT),
                                           f"channel {cand.get('channel')}, depth {cand.get('depth')}, {cand.get('row_order')}: "
                                           f"{cand.get('payload_bytes')} bytes [{cand.get('payload_type', '?')}]"))
        if r.get("has_payload"):
            lines.append(Text.assemble((f"{name:<20}", MUTED), ("✓ ", C_SUCCESS), "payload extracted (see the saved file)"))
    return lines


def detector_summary(results: Sequence[dict]) -> Text:
    counts = {"detected": 0, "inconclusive": 0, "clean": 0, "skipped": 0}
    for r in results:
        counts[detector_state(r)] += 1
    parts = [(f"{counts['detected']} detected", BAD if counts["detected"] else "dim"),
             (f"{counts['inconclusive']} inconclusive", ACCENT if counts["inconclusive"] else "dim"),
             (f"{counts['clean']} clean", "dim"), (f"{counts['skipped']} skipped", "dim")]
    text = Text()
    for i, (label, style) in enumerate(parts):
        if i:
            text.append("  ·  ", style="dim")
        text.append(label, style=style)
    return text
