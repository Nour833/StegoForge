"""StegoForge ops split — canonical implementations (imported by stegoforge.py for compat)."""
from __future__ import annotations

import contextlib
import logging
import sys

from pathlib import Path


from core.guess import guess_payload_ext as _guess_impl
from stegoforge_ops.ui import C_WARN, err_console

log = logging.getLogger(__name__)

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


METHOD_ALIASES = {
    "lsb": "lsb",
    "adaptive-lsb": "adaptive-lsb",
    "adaptive": "adaptive-lsb",
    "dct": "dct",
    "video-dct": "video-dct",
    "video-motion": "video-motion",
    "alpha": "alpha",
    "palette": "palette",
    "fingerprint-lsb": "fingerprint-lsb",
    "fingerprint": "fingerprint-lsb",
    "audio-lsb": "audio-lsb",
    "phase": "phase",
    "spectrogram": "spectrogram",
    "unicode": "unicode",
    "unicode-ws": "unicode",
    "linguistic": "linguistic",
    "pdf": "pdf",
    "docx": "docx",
    "xlsx": "xlsx",
    "office": "office",
    "elf": "elf",
    "pe": "pe",
    "tcp-covert": "tcp-covert",
    "timing-covert": "timing-covert",
}

# Methods served by one encoder share one crypto binding label, so an embed made
# with `--method office` opens when the decoder tries `docx` or `xlsx`.
_CRYPTO_FAMILY = {"docx": "office", "xlsx": "office"}


def canonical_method(method: str) -> str:
    """Resolve an alias (``adaptive``, ``unicode-ws``, ...) to the canonical method name."""
    canonical = METHOD_ALIASES.get(str(method or "").strip().lower())
    if canonical is None:
        raise ValueError(f"Unknown method: {method}")
    return canonical


def crypto_method_label(method: str) -> str:
    """The method string authenticated inside the AES envelope (stable across aliases)."""
    canonical = canonical_method(method)
    return _CRYPTO_FAMILY.get(canonical, canonical)


def get_encoder(method: str):
    """Return encoder instance for given method name."""
    if not isinstance(method, str) or not method:
        raise ValueError("Unknown method: empty method name")
    normalized = method.strip().lower()
    mapping = METHOD_ALIASES
    canonical = mapping.get(normalized)
    if canonical is None:
        import difflib

        suggestion = difflib.get_close_matches(normalized, mapping.keys(), n=1)
        hint = f". Did you mean '{suggestion[0]}'?" if suggestion else ""
        raise ValueError(f"Unknown method: {method}{hint}")
    method = canonical
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


def get_output_path(carrier_path: str, output: str | None, suffix: str = "_stego", encoder=None) -> Path:
    """Where the stego file goes; the default name carries the extension the encoder really produces."""
    p = Path(carrier_path)
    if output:
        return Path(output)
    ext = encoder.output_suffix(p.suffix) if encoder is not None else p.suffix
    return p.with_name(p.stem + suffix + ext)


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
    ext_l = ext.lower()
    if ext_l == ".gif":
        # Preserve GIF format: resize first frame, keep palette mode.
        out = img.convert("RGB").resize(resized, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        out.convert("P", palette=Image.Palette.ADAPTIVE, colors=256).save(buf, format="GIF")
        return buf.getvalue(), img.size, resized
    out = img.convert("RGB").resize(resized, Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    if ext_l in (".jpg", ".jpeg"):
        out.save(buf, format="JPEG", quality=95, subsampling=0)
    elif ext_l == ".webp":
        out.save(buf, format="WEBP", lossless=True)
    elif ext_l == ".bmp":
        out.save(buf, format="BMP")
    else:
        out.save(buf, format="PNG")
    return buf.getvalue(), img.size, resized


# ── Core operation helpers ────────────────────────────────────────────────────

def _read_key_file(path: str | None) -> str | None:
    """Read passphrase from a file (avoids argv/ps/history exposure)."""
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8").strip()


def _warn_argv_key() -> None:
    """Warn when passphrase passed via argv (visible in ps/shell history)."""
    try:
        argv = list(sys.argv)
    except Exception:
        return
    if "-k" in argv or "--key" in argv or any(a.startswith("--key=") for a in argv):
        err_console.print(
            f"[{C_WARN}]Passphrase on command line is visible in process list/history. "
            f"Prefer --key-file, prompt, or STEGOFORGE_KEY.[/{C_WARN}]"
        )


def _scrub_secret(value: str | None) -> None:
    """Best-effort secret scrubbing (CPython strings are immutable; this only
    drops references — documented limitation, see THREAT-MODEL.md)."""
    try:
        if value:
            value = "\x00" * len(value)
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            del value


def guess_payload_ext(data: bytes) -> str:
    """Shared payload-type sniffing (single source)."""
    return _guess_impl(data)


def _guess_payload_ext(data: bytes) -> str:
    """Backward-compat alias (stegoforge.py historical name)."""
    return _guess_impl(data)
