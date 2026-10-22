"""
core/document/office.py — DOCX / XLSX custom-XML-part steganography.

DOCX and XLSX are OPC (ZIP) packages. The payload is added as one extra XML
part that Office never displays::

    DOCX  word/custom/stegodata.xml     (relationship from word/_rels/document.xml.rels)
    XLSX  xl/custom/stegodata.xml       (relationship from xl/_rels/workbook.xml.rels)

To keep the package valid for strict OPC readers the part is registered in
``[Content_Types].xml`` and linked with a relationship whose *target resolves*
(relative to the source part's folder) and whose type is a private StegoForge
type, so Word/Excel never treat it as one of their own part kinds. All edits
use real XML namespaces (lxml); existing relationships and content types are
preserved untouched.

Payload: ``base64('SFRG_OFFICE' + zlib([4-byte length][payload]))``.
"""
from __future__ import annotations

import base64
import io
import posixpath
import struct
import zipfile
import zlib

from lxml import etree

from core.base import BaseEncoder
from core.bits import validate_payload_not_empty
from core.config import get_config

STEGO_FILENAME_DOCX = "word/custom/stegodata.xml"
STEGO_FILENAME_XLSX = "xl/custom/stegodata.xml"
RELS_DOCX = "word/_rels/document.xml.rels"
RELS_XLSX = "xl/_rels/workbook.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"

MAGIC = b"SFRG_OFFICE"
HEADER_SIZE = 4

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
STEGO_NS = "http://stegoforge.io/custom"
RELATIONSHIP_TYPE = "http://stegoforge.io/relationships/stegodata"
RELATIONSHIP_ID = "rIdStegoForge"

def _parser() -> etree.XMLParser:
    """Parser for untrusted XML: no entity expansion, no network, no huge trees.

    Created per call — lxml parsers must not be shared between threads.
    """
    return etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)


def _serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _make_stego_xml(payload: bytes) -> bytes:
    body = zlib.compress(struct.pack(">I", len(payload)) + payload, level=9)
    root = etree.Element(f"{{{STEGO_NS}}}StegoData", nsmap={None: STEGO_NS})
    root.text = base64.b64encode(MAGIC + body).decode("ascii")
    return _serialize(root)


def _parse_stego_xml(xml_bytes: bytes) -> bytes:
    try:
        root = etree.fromstring(xml_bytes, _parser())
    except etree.XMLSyntaxError as exc:
        raise ValueError(f"Corrupted Office stego XML: {exc}") from exc
    text = (root.text or "").strip()
    if not text:
        raise ValueError("Empty StegoData XML element")
    try:
        raw = base64.b64decode(text)
    except Exception as exc:
        raise ValueError(f"Corrupted Office stego encoding: {exc}") from exc
    if not raw.startswith(MAGIC):
        raise ValueError("Invalid Office steganography marker")

    cap = get_config().decomp_max_bytes
    try:
        inflater = zlib.decompressobj()
        data = inflater.decompress(raw[len(MAGIC):], cap)
    except zlib.error as exc:
        raise ValueError(f"Corrupted Office payload (decompression failed): {exc}") from exc
    if inflater.unconsumed_tail:
        raise ValueError("Office payload exceeds the decompression cap")
    if len(data) < HEADER_SIZE:
        raise ValueError("Corrupted Office payload header")
    length = struct.unpack(">I", data[:HEADER_SIZE])[0]
    if length <= 0 or length > cap:
        raise ValueError(f"Invalid Office payload length: {length}")
    payload = data[HEADER_SIZE:HEADER_SIZE + length]
    if len(payload) < length:
        raise ValueError("Incomplete Office payload data")
    return payload


def _add_relationship(rels_xml: bytes | None, rels_part: str, stego_part: str) -> bytes:
    """Return the rels part with a StegoForge relationship (replacing any earlier one)."""
    root = etree.fromstring(rels_xml, _parser()) if rels_xml else etree.Element(f"{{{REL_NS}}}Relationships", nsmap={None: REL_NS})
    for child in list(root):
        if child.get("Id") == RELATIONSHIP_ID:
            root.remove(child)
    # Targets resolve against the *source part's* folder: word/_rels/x.rels -> word/
    source_dir = posixpath.dirname(posixpath.dirname(rels_part))
    etree.SubElement(
        root,
        f"{{{REL_NS}}}Relationship",
        Id=RELATIONSHIP_ID,
        Type=RELATIONSHIP_TYPE,
        Target=posixpath.relpath(stego_part, source_dir),
    )
    return _serialize(root)


def _ensure_content_type(content_types_xml: bytes | None, stego_part: str) -> bytes:
    """Return [Content_Types].xml with an Override for the StegoForge part."""
    if content_types_xml:
        root = etree.fromstring(content_types_xml, _parser())
    else:
        root = etree.Element(f"{{{CT_NS}}}Types", nsmap={None: CT_NS})
        etree.SubElement(root, f"{{{CT_NS}}}Default", Extension="rels",
                         ContentType="application/vnd.openxmlformats-package.relationships+xml")
        etree.SubElement(root, f"{{{CT_NS}}}Default", Extension="xml", ContentType="application/xml")
    part_name = "/" + stego_part
    if not any(c.tag == f"{{{CT_NS}}}Override" and c.get("PartName") == part_name for c in root):
        etree.SubElement(root, f"{{{CT_NS}}}Override", PartName=part_name, ContentType="application/xml")
    return _serialize(root)


class OfficeEncoder(BaseEncoder):
    name = "office"
    supported_extensions = [".docx", ".xlsx"]

    @staticmethod
    def _detect_type(carrier_bytes: bytes, filename: str = "") -> str:
        """Return 'docx' or 'xlsx' from the file name, else by peeking into the ZIP."""
        fn = filename.lower()
        if fn.endswith(".xlsx"):
            return "xlsx"
        if fn.endswith(".docx"):
            return "docx"
        try:
            with zipfile.ZipFile(io.BytesIO(carrier_bytes)) as zf:
                names = zf.namelist()
        except zipfile.BadZipFile:
            return "docx"
        if any(n.startswith("xl/") for n in names) and not any(n.startswith("word/") for n in names):
            return "xlsx"
        return "docx"

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        # Effectively limited only by disk space; use the carrier's own size as a
        # practical ceiling (min 512 KiB so tiny test files report sensible numbers).
        return max(len(carrier_bytes), 512 * 1024)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, filename: str = "", **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, Office capacity: {cap} bytes")

        kind = self._detect_type(carrier_bytes, filename)
        stego_part = STEGO_FILENAME_DOCX if kind == "docx" else STEGO_FILENAME_XLSX
        rels_part = RELS_DOCX if kind == "docx" else RELS_XLSX
        cfg = get_config()

        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(carrier_bytes), "r") as zin:
            infos = zin.infolist()
            if len(infos) > cfg.zip_max_entries:
                raise ValueError("Office document has too many ZIP entries")
            if sum(i.file_size for i in infos) > cfg.zip_max_total_bytes:
                raise ValueError("Office document exceeds the size cap")
            names = {i.filename for i in infos}
            with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                for item in infos:
                    if item.filename == stego_part:
                        continue  # replaced below
                    data = zin.read(item.filename)
                    if item.filename == rels_part:
                        data = _add_relationship(data, rels_part, stego_part)
                    elif item.filename == CONTENT_TYPES:
                        data = _ensure_content_type(data, stego_part)
                    zout.writestr(item, data)
                zout.writestr(stego_part, _make_stego_xml(bytes(payload_bytes)))
                if rels_part not in names:
                    zout.writestr(rels_part, _add_relationship(None, rels_part, stego_part))
                if CONTENT_TYPES not in names:
                    zout.writestr(CONTENT_TYPES, _ensure_content_type(None, stego_part))
        return out.getvalue()

    def decode(self, stego_bytes: bytes, filename: str = "", **kwargs) -> bytes:
        kind = self._detect_type(stego_bytes, filename)
        stego_part = STEGO_FILENAME_DOCX if kind == "docx" else STEGO_FILENAME_XLSX
        with zipfile.ZipFile(io.BytesIO(stego_bytes), "r") as zf:
            try:
                info = zf.getinfo(stego_part)
            except KeyError:
                raise ValueError(f"No StegoForge payload found in Office document (missing: {stego_part})") from None
            if info.file_size > 2 * get_config().decomp_max_bytes:
                raise ValueError("Office payload part exceeds the size cap")
            xml = zf.read(info)
        return _parse_stego_xml(xml)
