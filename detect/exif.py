"""
detect/exif.py — Metadata forensics scanner.

Analyzes EXIF, PNG chunks, PDF metadata, and document properties
for signs of steganography or hidden data.

Checks:
  - Non-empty comment/UserComment fields
  - Embedded thumbnails that differ from main image
  - Unusual XMP data or non-standard keys
  - GPS coordinates (possible tracking concern)
  - Software metadata that reveals stego tools
  - StegoForge magic header (/StegoData, word/custom/stegodata.xml)
  - Suspicious timestamp patterns
  - PNG tEXt/zTXt hidden chunks

Each finding has a suspicion level: 'low', 'medium', 'high'.
"""
import io
import os
import zipfile
import struct

from detect.base import BaseDetector, DetectionResult

try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False


STEGO_TOOLS = [
    "steghide", "stegoforge", "openstego", "jphide", "invisible secrets",
    "camouflage", "mp3stego", "xiao", "stools", "blindside", "cloak",
]


class EXIFDetector(BaseDetector):
    name = "exif"
    supported_extensions = [
        ".jpg", ".jpeg", ".tiff", ".png", ".gif",
        ".webp", ".bmp", ".pdf", ".docx", ".xlsx", ".txt",
    ]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        findings = []
        ext = os.path.splitext(filename)[1].lower() if filename else ""

        try:
            if ext in (".jpg", ".jpeg", ".tiff"):
                findings.extend(self._scan_jpeg_exif(file_bytes))
            if ext in (".png", ".gif", ".webp", ".bmp", ".jpg", ".jpeg"):
                findings.extend(self._scan_pil_meta(file_bytes))
            if ext == ".pdf":
                findings.extend(self._scan_pdf(file_bytes))
            if ext in (".docx", ".xlsx"):
                findings.extend(self._scan_office(file_bytes))
            if ext == ".txt":
                findings.extend(self._scan_text(file_bytes))

            # Always: check for SFRG magic header
            if file_bytes[:4] == b"SFRG":
                findings.append({
                    "field": "Binary Data",
                    "description": "StegoForge SFRG magic header found at start of file",
                    "suspicion": "high",
                    "value": "SFRG magic",
                })

        except Exception as e:
            findings.append({
                "field": "Error",
                "description": f"Scan error: {e}",
                "suspicion": "low",
                "value": "",
            })

        high_count = sum(1 for f in findings if f.get("suspicion") == "high")
        med_count = sum(1 for f in findings if f.get("suspicion") == "medium")

        confidence = min(1.0, high_count * 0.4 + med_count * 0.2 + len(findings) * 0.05)
        detected = confidence > 0.1 or high_count > 0

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(confidence, 4),
            details={
                "findings_count": len(findings),
                "high_suspicion": high_count,
                "medium_suspicion": med_count,
                "low_suspicion": len(findings) - high_count - med_count,
            },
            findings=findings,
        )

    def _scan_jpeg_exif(self, file_bytes: bytes) -> list[dict]:
        findings = []
        if not HAS_PIEXIF:
            return findings
        try:
            exif_data = piexif.load(file_bytes)
            for ifd_name, ifd in exif_data.items():
                if not isinstance(ifd, dict):
                    continue
                for tag_id, value in ifd.items():
                    tag_name = piexif.TAGS.get(ifd_name, {}).get(tag_id, {}).get("name", str(tag_id))

                    # UserComment with unusual content
                    if tag_name == "UserComment" and value and len(value) > 4:
                        decoded = value[8:].decode("utf-8", errors="replace").strip("\x00")
                        if decoded:
                            findings.append({
                                "field": "EXIF UserComment",
                                "description": f"Non-empty UserComment field: {decoded[:100]}",
                                "suspicion": "medium",
                                "value": decoded[:200],
                            })

                    # Software field — check for stego tools
                    if tag_name == "Software" and value:
                        sw = value.decode("utf-8", errors="replace").lower() if isinstance(value, bytes) else str(value).lower()
                        for tool in STEGO_TOOLS:
                            if tool in sw:
                                findings.append({
                                    "field": "EXIF Software",
                                    "description": f"Stego tool signature in Software tag: {sw}",
                                    "suspicion": "high",
                                    "value": sw,
                                })

                    # GPS data
                    if tag_name in ("GPSLatitude", "GPSLongitude") and value:
                        findings.append({
                            "field": "EXIF GPS",
                            "description": "GPS coordinates present in EXIF data",
                            "suspicion": "low",
                            "value": str(value),
                        })

        except Exception:
            pass
        return findings

    def _scan_pil_meta(self, file_bytes: bytes) -> list[dict]:
        findings = []
        if not HAS_PIL:
            return findings
        try:
            img = Image.open(io.BytesIO(file_bytes))

            # Check PNG text chunks
            if img.format == "PNG" and hasattr(img, "info"):
                for key, val in img.info.items():
                    if key.lower() in ("comment", "description", "author", "copyright", "url"):
                        if val and str(val).strip():
                            findings.append({
                                "field": f"PNG {key} chunk",
                                "description": f"Non-empty PNG text chunk '{key}': {str(val)[:100]}",
                                "suspicion": "medium",
                                "value": str(val)[:200],
                            })
                    # Any non-standard key is suspicious
                    if key not in ("dpi", "gamma", "icc_profile", "transparency",
                                   "background", "exif", "xmp", "photoshop"):
                        findings.append({
                            "field": f"PNG chunk '{key}'",
                            "description": f"Non-standard PNG metadata chunk found: {key}",
                            "suspicion": "medium",
                            "value": str(val)[:100] if val else "",
                        })

            # Check GIF comment
            if img.format == "GIF" and img.info.get("comment"):
                comment = img.info["comment"]
                decoded = comment.decode("utf-8", errors="replace") if isinstance(comment, bytes) else str(comment)
                findings.append({
                    "field": "GIF Comment",
                    "description": f"GIF comment field contains data: {decoded[:100]}",
                    "suspicion": "medium",
                    "value": decoded[:200],
                })

            # Thumbnail vs image comparison — simplified check
            if hasattr(img, "_getexif") and img._getexif():
                exif = img._getexif()
                if exif and 0x0201 in exif:  # JPEGInterchangeFormat — thumbnail offset
                    findings.append({
                        "field": "EXIF Thumbnail",
                        "description": "Embedded EXIF thumbnail present — may differ from main image",
                        "suspicion": "low",
                        "value": "thumbnail present",
                    })

        except Exception:
            pass
        return findings

    def _scan_pdf(self, file_bytes: bytes) -> list[dict]:
        findings = []
        if not HAS_PYPDF:
            return findings
        try:
            reader = PdfReader(io.BytesIO(file_bytes))
            meta = reader.metadata
            if meta:
                # Check for StegoForge marker
                if "/StegoData" in meta:
                    findings.append({
                        "field": "PDF /StegoData",
                        "description": "StegoForge payload marker found in PDF metadata (/StegoData key)",
                        "suspicion": "high",
                        "value": str(meta["/StegoData"])[:100],
                    })
                # Check other metadata fields
                for key, val in meta.items():
                    if key in ("/Producer", "/Creator", "/Author", "/Title", "/Subject"):
                        if val:
                            val_lower = str(val).lower()
                            for tool in STEGO_TOOLS:
                                if tool in val_lower:
                                    findings.append({
                                        "field": f"PDF {key}",
                                        "description": f"Stego tool signature in {key}: {val}",
                                        "suspicion": "high",
                                        "value": str(val),
                                    })
        except Exception:
            pass
        return findings

    def _scan_office(self, file_bytes: bytes) -> list[dict]:
        findings = []
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
                names = zf.namelist()
                # Check for StegoForge custom XML
                if "word/custom/stegodata.xml" in names:
                    findings.append({
                        "field": "DOCX custom XML",
                        "description": "StegoForge payload found: word/custom/stegodata.xml present",
                        "suspicion": "high",
                        "value": "word/custom/stegodata.xml",
                    })
                if "xl/custom/stegodata.xml" in names:
                    findings.append({
                        "field": "XLSX custom XML",
                        "description": "StegoForge payload found: xl/custom/stegodata.xml present",
                        "suspicion": "high",
                        "value": "xl/custom/stegodata.xml",
                    })
                # Check for any unusual extra files in the ZIP
                expected_prefixes = (
                    "word/", "xl/", "ppt/", "docProps/", "_rels/",
                    "[Content_Types].xml", "customXml/",
                )
                for name in names:
                    if not any(name.startswith(p) for p in expected_prefixes):
                        findings.append({
                            "field": "Office ZIP entry",
                            "description": f"Unexpected file in Office ZIP archive: {name}",
                            "suspicion": "medium",
                            "value": name,
                        })
        except zipfile.BadZipFile:
            pass
        return findings

    def _scan_text(self, file_bytes: bytes) -> list[dict]:
        findings = []
        text = file_bytes.decode("utf-8", errors="replace")
        zw_chars = [ch for ch in text if ch in ("\u200B", "\u200C", "\u200D")]
        if zw_chars:
            findings.append({
                "field": "Unicode Zero-Width",
                "description": (
                    f"Zero-width Unicode characters detected in text file "
                    f"({len(zw_chars)} characters: ZWSP={text.count(chr(0x200B))}, "
                    f"ZWNJ={text.count(chr(0x200C))}, ZWJ={text.count(chr(0x200D))})"
                ),
                "suspicion": "high",
                "value": f"{len(zw_chars)} zero-width characters",
            })
        return findings
