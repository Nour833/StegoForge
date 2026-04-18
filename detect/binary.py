"""
detect/binary.py - ELF/PE binary anomaly detector.
"""
from __future__ import annotations

import math

from detect.base import BaseDetector, DetectionResult


class BinaryDetector(BaseDetector):
    name = "binary"
    supported_extensions = [".elf", ".exe", ".dll", ".bin"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
        findings = []

        if file_bytes.startswith(b"\x7fELF"):
            btype = "ELF"
            regions = _elf_slack_regions(file_bytes)
        elif file_bytes[:2] == b"MZ":
            btype = "PE"
            regions = _pe_slack_regions(file_bytes)
        else:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={"skipped": True, "interpretation": "Not an ELF/PE binary"},
            )

        total = 0
        suspicious = 0
        high_entropy_regions = 0
        nonzero_regions = 0

        for start, end, label in regions:
            if end <= start or start < 0 or end > len(file_bytes):
                continue
            chunk = file_bytes[start:end]
            total += len(chunk)
            nz = sum(1 for b in chunk if b != 0)
            ent = _entropy(chunk)

            if nz > 0:
                nonzero_regions += 1
                findings.append({
                    "field": label,
                    "description": f"non-zero bytes in normally slack region ({nz} bytes)",
                    "suspicion": "high" if nz > 16 else "medium",
                })
                suspicious += min(1.0, nz / max(1, len(chunk)))

            if ent > 6.5:
                high_entropy_regions += 1
                findings.append({
                    "field": label,
                    "description": f"section slack entropy higher than expected ({ent:.2f})",
                    "suspicion": "medium",
                })
                suspicious += 0.4

        conf = 0.0
        if regions:
            conf = min(1.0, suspicious / max(1.0, len(regions)))
            
        extracted = None
        try:
            if btype == "PE":
                from core.binary.pe import PEEncoder
                extracted = PEEncoder().decode(file_bytes)
            elif btype == "ELF":
                from core.binary.elf import ELFEncoder
                extracted = ELFEncoder().decode(file_bytes)
        except Exception:
            pass

        if extracted is not None:
            conf = 1.0
            nonzero_regions += 1
            findings.insert(0, {
                "field": "Slack Space",
                "description": "Valid StegoForge payload identified and blindly extracted!",
                "suspicion": "high"
            })

        detected = conf >= 0.2 or nonzero_regions > 0
        res = DetectionResult(
            method=self.name,
            detected=detected,
            confidence=round(conf, 4),
            details={
                "binary_type": btype,
                "regions_scanned": len(regions),
                "high_entropy_regions": high_entropy_regions,
                "nonzero_regions": nonzero_regions,
                "interpretation": (
                    "Binary slack/notes anomalies OR valid payload detected" if detected else "No strong anomalies detected"
                ),
            },
            findings=findings,
        )
        res.extracted_payload = extracted
        return res


def _entropy(data: bytes) -> float:
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    ent = 0.0
    for c in counts:
        if c:
            p = c / n
            ent -= p * math.log2(p)
    return ent


def _elf_slack_regions(data: bytes):
    from core.binary.elf import parse_elf_regions
    return parse_elf_regions(data)


def _pe_slack_regions(data: bytes):
    from core.binary.pe import parse_pe_regions
    return parse_pe_regions(data)
