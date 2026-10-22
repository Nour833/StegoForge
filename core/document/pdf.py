"""
core/document/pdf.py — PDF metadata steganography.

The payload is zlib-compressed, base64-encoded and stored under a non-standard
key (``/StegoData``) of the document ``/Info`` dictionary. The rest of the
document is cloned unchanged (pages, outlines, forms, XMP, page labels,
attachments), so it opens exactly as before in every viewer and the hidden data
is not rendered anywhere. It is, however, trivially visible to anyone who dumps
the PDF metadata — this is concealment, not stealth.

Wire format of the value: ``base64('SFRG_PDF' + zlib([4-byte length][payload]))``.
"""
from __future__ import annotations

import base64
import io
import logging
import struct
import zlib

from pypdf import PdfReader, PdfWriter

from core.base import BaseEncoder
from core.bits import validate_payload_not_empty
from core.config import get_config

log = logging.getLogger(__name__)

STEGO_KEY = "/StegoData"
MAGIC = b"SFRG_PDF"
HEADER_SIZE = 4  # 4-byte big-endian length prefix


def _open(data: bytes) -> PdfReader:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("Encrypted PDFs that need a password are not supported")
    return reader


class PDFEncoder(BaseEncoder):
    name = "pdf"
    supported_extensions = [".pdf"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        # Metadata injection has no hard limit; embedding more than the PDF itself
        # weighs is impractical, so use the carrier size as a ceiling (min 512 KiB).
        return max(len(carrier_bytes), 512 * 1024)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, PDF capacity: {cap} bytes")

        compressed = zlib.compress(struct.pack(">I", len(payload_bytes)) + bytes(payload_bytes), level=9)
        encoded = base64.b64encode(MAGIC + compressed).decode("ascii")

        writer = PdfWriter(clone_from=_open(carrier_bytes))
        writer.add_metadata({STEGO_KEY: encoded})  # merges with the existing /Info
        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        try:
            meta = _open(stego_bytes).metadata
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Invalid PDF carrier: {exc}") from exc

        if meta is None or STEGO_KEY not in meta:
            raise ValueError("No StegoForge payload found in PDF metadata")
        try:
            raw = base64.b64decode(str(meta[STEGO_KEY]))
        except Exception as exc:
            raise ValueError(f"Corrupted PDF stego metadata: {exc}") from exc
        if not raw.startswith(MAGIC):
            raise ValueError("Invalid PDF steganography marker — wrong file or not encoded by StegoForge")

        cap = get_config().decomp_max_bytes
        try:
            inflater = zlib.decompressobj()
            decompressed = inflater.decompress(raw[len(MAGIC):], cap)
        except zlib.error as exc:
            raise ValueError(f"Corrupted PDF payload (decompression failed): {exc}") from exc
        if inflater.unconsumed_tail:
            raise ValueError("PDF payload exceeds the decompression cap")

        if len(decompressed) < HEADER_SIZE:
            raise ValueError("Corrupted PDF payload header")
        length = struct.unpack(">I", decompressed[:HEADER_SIZE])[0]
        if length <= 0 or length > cap:
            raise ValueError(f"Invalid PDF payload length: {length}")
        payload = decompressed[HEADER_SIZE:HEADER_SIZE + length]
        if len(payload) < length:
            raise ValueError("Incomplete PDF payload data")
        return payload
