"""
core/document/pdf.py — PDF stream injection steganography.

Injects payload as a custom object in the PDF's object tree with a
non-standard key (/StegoData). The payload is zlib-compressed and
hex-encoded before insertion, making it invisible in all viewers.

Also supports embedding in the /Info metadata dictionary.

The output PDF opens correctly in all PDF viewers (Adobe, Evince,
browser PDF viewers, etc.). The hidden data is not rendered anywhere.
"""
import io
import zlib
import struct
import base64

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, ByteStringObject, DecodedStreamObject,
    DictionaryObject, NameObject, NumberObject, TextStringObject,
    StreamObject,
)

from core.base import BaseEncoder

STEGO_KEY = "/StegoData"
MAGIC = b"SFRG_PDF"
HEADER_SIZE = 4  # 4-byte big-endian length prefix


class PDFEncoder(BaseEncoder):
    name = "pdf"
    supported_extensions = [".pdf"]

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        # PDF metadata injection has no hard limit, but embedding more than
        # the PDF itself weighs is impractical. Use carrier size as ceiling,
        # floored at 512KB for tiny test PDFs.
        return max(len(carrier_bytes), 512 * 1024)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, **kwargs) -> bytes:
        reader = PdfReader(io.BytesIO(carrier_bytes))
        writer = PdfWriter()

        # Copy all pages
        for page in reader.pages:
            writer.add_page(page)

        # Encode payload: prepend 4-byte length, zlib compress, base64
        header = struct.pack(">I", len(payload_bytes))
        compressed = zlib.compress(header + payload_bytes, level=9)
        encoded = base64.b64encode(MAGIC + compressed).decode("ascii")

        # Add custom metadata key
        writer.add_metadata({
            "/StegoData": encoded,
        })

        buf = io.BytesIO()
        writer.write(buf)
        return buf.getvalue()

    def decode(self, stego_bytes: bytes, **kwargs) -> bytes:
        reader = PdfReader(io.BytesIO(stego_bytes))
        meta = reader.metadata

        if meta is None or "/StegoData" not in meta:
            raise ValueError("No StegoForge payload found in PDF metadata")

        encoded_str = meta["/StegoData"]
        raw = base64.b64decode(encoded_str)

        if not raw.startswith(MAGIC):
            raise ValueError("Invalid PDF steganography marker — wrong file or not encoded by StegoForge")

        compressed = raw[len(MAGIC):]
        decompressed = zlib.decompress(compressed)

        length = struct.unpack(">I", decompressed[:HEADER_SIZE])[0]
        payload = decompressed[HEADER_SIZE:HEADER_SIZE + length]

        if len(payload) < length:
            raise ValueError("Incomplete PDF payload data")

        return payload
