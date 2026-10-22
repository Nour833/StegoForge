"""core/guess.py — payload-type sniffing (single source of truth for CLI and web).

A magic number alone is not evidence: ``BM`` and ``MZ`` are two bytes, so plain
text such as "BMW sales notes" or "MZ-3 report" starts with one. Every signature
here is therefore *validated* against a field the real format must have, and
printable text is recognised before the weak signatures are consulted.
"""
from __future__ import annotations

import struct

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".mp4": "video/mp4",
    ".pdf": "application/pdf",
    ".zip": "application/zip",
    ".elf": "application/x-elf",
    ".exe": "application/x-msdownload",
    ".sfrg": "application/octet-stream",
    ".txt": "text/plain",
    ".bin": "application/octet-stream",
}

_BMP_DIB_SIZES = (12, 40, 52, 56, 64, 108, 124)


def _is_bmp(data: bytes) -> bool:
    if len(data) < 30 or data[:2] != b"BM":
        return False
    file_size, reserved1, reserved2, pixel_offset, dib_size = struct.unpack_from("<IHHII", data, 2)
    return (
        reserved1 == 0 and reserved2 == 0
        and dib_size in _BMP_DIB_SIZES
        and 14 + dib_size <= pixel_offset <= max(file_size, len(data))
    )


def _is_pe(data: bytes) -> bool:
    if len(data) < 0x40 or data[:2] != b"MZ":
        return False
    (pe_offset,) = struct.unpack_from("<I", data, 0x3C)
    return 0x40 <= pe_offset <= len(data) - 4 and data[pe_offset:pe_offset + 4] == b"PE\x00\x00"


def _is_mp3(data: bytes) -> bool:
    if data[:3] == b"ID3":
        return len(data) >= 10 and data[3] in (2, 3, 4) and data[4] != 0xFF
    # MPEG audio frame sync with a valid layer (III/II/I) and a non-reserved version
    return len(data) >= 4 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0 and (data[1] >> 3) & 3 != 1 \
        and (data[1] >> 1) & 3 != 0


def _looks_like_text(data: bytes) -> bool:
    sample = data[:2048]
    if not sample or b"\x00" in sample:
        return False
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError as exc:
        if exc.start < len(sample) - 4:  # a multi-byte character cut at the sample edge is fine
            return False
        text = sample[:exc.start].decode("utf-8")
        if not text:
            return False
    return sum(1 for c in text if c.isprintable() or c in "\n\r\t") / len(text) > 0.9


def guess_payload_ext(data: bytes) -> str:
    """Return the file extension that best describes ``data`` (``.bin`` when unknown)."""
    data = bytes(data)
    # Signatures long enough to be meaningful on their own.
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return ".tiff"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:4] == b"fLaC":
        return ".flac"
    if data[:4] == b"OggS":
        return ".ogg"
    if data[:5] == b"%PDF-":
        return ".pdf"
    if data[:4] == b"\x7fELF":
        return ".elf"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return ".mp4"
    if data[:4] == b"PK\x03\x04":
        return ".zip"
    if data[:4] == b"SFRG":
        return ".sfrg"
    # Short signatures only count if the structure behind them checks out.
    if _is_bmp(data):
        return ".bmp"
    if _is_pe(data):
        return ".exe"
    if _is_mp3(data):
        return ".mp3"
    if _looks_like_text(data):
        return ".txt"
    return ".bin"


def guess_payload_type(data: bytes) -> tuple[str, str]:
    """Return ``(mime_type, extension)`` for ``data``."""
    ext = guess_payload_ext(data)
    return _MIME.get(ext, "application/octet-stream"), ext
