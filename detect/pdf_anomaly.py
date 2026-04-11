"""
detect/pdf_anomaly.py - Lightweight PDF anomaly detector.
"""
from __future__ import annotations

import math

from detect.base import BaseDetector, DetectionResult


class PDFAnomalyDetector(BaseDetector):
    name = "pdf-anomaly"
    supported_extensions = [".pdf"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        if not file_bytes.startswith(b"%PDF"):
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"skipped": True, "interpretation": "Not a PDF file"},
            )

        findings = []
        suspicious = 0.0

        eof_count = file_bytes.count(b"%%EOF")
        if eof_count > 1:
            findings.append({"field": "%%EOF", "description": "Multiple EOF markers (incremental updates)", "suspicion": "medium"})
            suspicious += 0.25

        tokens = {
            b"/EmbeddedFile": ("Embedded file objects present", 0.45, "high"),
            b"/JavaScript": ("JavaScript action objects present", 0.45, "high"),
            b"/OpenAction": ("OpenAction present", 0.25, "medium"),
            b"/AA": ("Additional action dictionary present", 0.20, "medium"),
            b"/RichMedia": ("Rich media payload present", 0.35, "high"),
            b"/ObjStm": ("Object streams present", 0.12, "low"),
        }

        for tok, (desc, weight, level) in tokens.items():
            if tok in file_bytes:
                findings.append({"field": tok.decode("latin1"), "description": desc, "suspicion": level})
                suspicious += weight

        tail = file_bytes[-65536:] if len(file_bytes) > 65536 else file_bytes
        tail_entropy = _entropy(tail)
        if tail_entropy > 7.4:
            findings.append({"field": "tail-entropy", "description": f"High entropy PDF tail region ({tail_entropy:.2f})", "suspicion": "medium"})
            suspicious += 0.25

        conf = float(max(0.0, min(1.0, suspicious)))
        detected = conf >= 0.35
        return DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(conf, 4),
            details={
                "eof_markers": eof_count,
                "tail_entropy": round(tail_entropy, 6),
                "findings_count": len(findings),
                "interpretation": (
                    "PDF structure includes suspicious embedded/active objects"
                    if detected else "No strong PDF structural stego indicators detected"
                ),
            },
            findings=findings,
        )


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    h = 0.0
    for c in counts:
        if c:
            p = c / n
            h -= p * math.log2(p)
    return h
