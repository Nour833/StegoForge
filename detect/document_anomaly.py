"""
detect/document_anomaly.py - Lightweight document stego anomaly detector.
"""
from __future__ import annotations

import io
import zipfile

from detect.base import BaseDetector, DetectionResult


class DocumentAnomalyDetector(BaseDetector):
    name = "document-anomaly"
    supported_extensions = [".txt", ".docx", ".xlsx"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        ext = ""
        if "." in filename:
            ext = filename[filename.rfind("."):].lower()

        if ext == ".txt":
            return self._analyze_txt(file_bytes)
        if ext in {".docx", ".xlsx"}:
            return self._analyze_office_zip(file_bytes, ext)

        return DetectionResult(
            method=self.name,
            detected=False,
            confidence=0.0,
            details={"skipped": True, "interpretation": "Unsupported document extension"},
        )

    def _analyze_txt(self, file_bytes: bytes) -> DetectionResult:
        text = file_bytes.decode("utf-8", errors="ignore")
        total_chars = max(1, len(text))

        zw = sum(text.count(c) for c in ("\u200b", "\u200c", "\u200d", "\ufeff"))
        lines = text.splitlines() or [text]
        trailing = sum(1 for line in lines if line.endswith(" ") or line.endswith("\t"))

        zw_ratio = zw / total_chars
        trailing_ratio = trailing / max(1, len(lines))
        conf = min(1.0, (zw_ratio * 45.0) + (trailing_ratio * 0.8))
        detected = conf >= 0.35

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(conf, 4),
            details={
                "zero_width_chars": zw,
                "zero_width_ratio": round(zw_ratio, 6),
                "trailing_whitespace_lines": trailing,
                "interpretation": (
                    "Text contains suspicious invisible-character / whitespace patterns"
                    if detected else "No strong text stego anomaly pattern detected"
                ),
            },
        )

    def _analyze_office_zip(self, file_bytes: bytes, ext: str) -> DetectionResult:
        findings = []
        suspicious = 0.0

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
                names = zf.namelist()
        except Exception:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"skipped": True, "interpretation": "Invalid Office ZIP container"},
            )

        has_custom_xml = any(n.startswith("customXml/") for n in names)
        has_embeddings = any("/embeddings/" in n for n in names)
        has_vba = any(n.lower().endswith("vbaProject.bin".lower()) for n in names)
        very_large_xml = any((n.endswith(".xml") and len(n) > 120) for n in names)

        if has_custom_xml:
            findings.append({"field": "customXml", "description": "Custom XML parts present", "suspicion": "medium"})
            suspicious += 0.28
        if has_embeddings:
            findings.append({"field": "embeddings", "description": "Embedded objects present", "suspicion": "medium"})
            suspicious += 0.25
        if has_vba:
            findings.append({"field": "vbaProject.bin", "description": "VBA project stream present", "suspicion": "high"})
            suspicious += 0.35
        if very_large_xml:
            findings.append({"field": "xml-name-shape", "description": "Unusual XML entry name shape", "suspicion": "low"})
            suspicious += 0.08

        conf = min(1.0, suspicious)
        detected = conf >= 0.35

        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(conf, 4),
            details={
                "doc_type": ext.lstrip("."),
                "entry_count": len(names),
                "has_custom_xml": has_custom_xml,
                "has_embeddings": has_embeddings,
                "has_vba_project": has_vba,
                "interpretation": (
                    "Office container includes potentially covert-bearing streams"
                    if detected else "No strong Office container anomaly pattern detected"
                ),
            },
            findings=findings,
        )
