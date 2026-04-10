"""
core/document/office.py — DOCX/XLSX Open XML stream injection steganography.

DOCX and XLSX are ZIP archives containing XML files.
This module adds a custom XML part to the archive:
  - DOCX: word/custom/stegodata.xml
  - XLSX: xl/custom/stegodata.xml

And registers a relationship entry in the appropriate _rels file.

The output document opens correctly in Microsoft Word/Excel/LibreOffice.
The custom XML part is never displayed in the document UI.

Payload: zlib-compressed + base64-encoded for clean XML embedding.
"""
import io
import os
import zlib
import struct
import base64
import zipfile
import xml.etree.ElementTree as ET

from core.base import BaseEncoder

STEGO_FILENAME_DOCX = "word/custom/stegodata.xml"
STEGO_FILENAME_XLSX = "xl/custom/stegodata.xml"
RELS_DOCX = "word/_rels/document.xml.rels"
RELS_XLSX = "xl/_rels/workbook.xml.rels"

MAGIC = b"SFRG_OFFICE"
HEADER_SIZE = 4

RELATIONSHIP_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml"
RELATIONSHIP_ID = "rIdStegoForge"


def _make_stego_xml(payload_bytes: bytes) -> bytes:
    header = struct.pack(">I", len(payload_bytes))
    compressed = zlib.compress(header + payload_bytes, level=9)
    encoded = base64.b64encode(MAGIC + compressed).decode("ascii")

    root = ET.Element("StegoData", xmlns="http://stegoforge.io/custom")
    root.text = encoded
    tree = ET.ElementTree(root)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()


def _parse_stego_xml(xml_bytes: bytes) -> bytes:
    root = ET.fromstring(xml_bytes)
    encoded_str = root.text
    if not encoded_str:
        raise ValueError("Empty StegoData XML element")

    raw = base64.b64decode(encoded_str)
    if not raw.startswith(MAGIC):
        raise ValueError("Invalid Office steganography marker")

    compressed = raw[len(MAGIC):]
    decompressed = zlib.decompress(compressed)
    length = struct.unpack(">I", decompressed[:HEADER_SIZE])[0]
    payload = decompressed[HEADER_SIZE:HEADER_SIZE + length]
    if len(payload) < length:
        raise ValueError("Incomplete Office payload data")
    return payload


def _add_relationship(rels_content: bytes, custom_xml_path: str) -> bytes:
    """Add a relationship entry to the _rels XML file."""
    try:
        root = ET.fromstring(rels_content)
    except ET.ParseError:
        # Create minimal rels file
        root = ET.Element("Relationships",
                           xmlns="http://schemas.openxmlformats.org/package/2006/relationships")

    # Remove existing StegoForge relationship if present
    for child in list(root):
        if child.get("Id") == RELATIONSHIP_ID:
            root.remove(child)

    # Determine relative target from word/ or xl/
    target = f"../{custom_xml_path.split('/', 1)[1]}" if "/" in custom_xml_path else custom_xml_path

    ET.SubElement(root, "Relationship",
                  Id=RELATIONSHIP_ID,
                  Type=RELATIONSHIP_TYPE,
                  Target=target)

    buf = io.BytesIO()
    ET.ElementTree(root).write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()


class OfficeEncoder(BaseEncoder):
    name = "office"
    supported_extensions = [".docx", ".xlsx"]

    def _detect_type(self, carrier_bytes: bytes, filename: str = "") -> str:
        """Return 'docx' or 'xlsx' based on filename or content inspection."""
        fn = filename.lower()
        if fn.endswith(".xlsx"):
            return "xlsx"
        if fn.endswith(".docx"):
            return "docx"
        # Peek into ZIP to guess type
        try:
            with zipfile.ZipFile(io.BytesIO(carrier_bytes)) as zf:
                names = zf.namelist()
                if any(n.startswith("word/") for n in names):
                    return "docx"
                if any(n.startswith("xl/") for n in names):
                    return "xlsx"
        except zipfile.BadZipFile:
            pass
        return "docx"  # default

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        # Office documents are ZIP archives. Custom XML injection is effectively
        # only limited by disk space, but we return the carrier's own size as a
        # practical ceiling (no point hiding more than the carrier itself weighs).
        # Floor at 512KB so tiny test files report sensible numbers.
        return max(len(carrier_bytes), 512 * 1024)

    def encode(
        self,
        carrier_bytes: bytes,
        payload_bytes: bytes,
        filename: str = "",
        **kwargs,
    ) -> bytes:
        doc_type = self._detect_type(carrier_bytes, filename)
        stego_file = STEGO_FILENAME_DOCX if doc_type == "docx" else STEGO_FILENAME_XLSX
        rels_file = RELS_DOCX if doc_type == "docx" else RELS_XLSX

        stego_xml = _make_stego_xml(payload_bytes)

        buf = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(carrier_bytes), "r") as zin:
            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == stego_file:
                        continue  # will be replaced
                    if item.filename == rels_file:
                        data = _add_relationship(data, stego_file)
                    zout.writestr(item, data)

                # Add stego XML part
                zout.writestr(stego_file, stego_xml)

                # Add relationship if file didn't exist
                if rels_file not in [i.filename for i in zin.infolist()]:
                    fake_rels = b'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
                    new_rels = _add_relationship(fake_rels, stego_file)
                    zout.writestr(rels_file, new_rels)

        return buf.getvalue()

    def decode(
        self,
        stego_bytes: bytes,
        filename: str = "",
        **kwargs,
    ) -> bytes:
        doc_type = self._detect_type(stego_bytes, filename)
        stego_file = STEGO_FILENAME_DOCX if doc_type == "docx" else STEGO_FILENAME_XLSX

        try:
            with zipfile.ZipFile(io.BytesIO(stego_bytes), "r") as zf:
                if stego_file not in zf.namelist():
                    raise ValueError(
                        f"No StegoForge payload found in Office document "
                        f"(missing: {stego_file})"
                    )
                xml_data = zf.read(stego_file)
        except zipfile.BadZipFile as e:
            raise ValueError(f"Invalid Office document (bad ZIP): {e}") from e

        return _parse_stego_xml(xml_data)
