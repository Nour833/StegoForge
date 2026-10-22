"""
detect/binary.py — ELF/PE slack-space detector.

Evidence is limited to regions that a linker leaves *zero-filled*: the file
padding between ELF sections and the raw-size tail of PE sections. Non-zero,
non-uniform bytes there are not produced by toolchains, but are exactly what a
slack-space embed writes.

NOTE sections and PE overlays are deliberately **not** evidence: they hold real
data (build-id, GNU properties, SystemTap probes, Authenticode signatures,
installers), so "non-zero" says nothing about them. Treating them as slack made
every system binary look hidden-data-bearing. A validated StegoForge extraction
remains a definitive positive wherever the payload lives.
"""
from __future__ import annotations

import logging

import numpy as np

from detect.base import BaseDetector, DetectionResult

log = logging.getLogger(__name__)

# Region labels whose contents a toolchain leaves as zeros (anything else is informational).
_EVIDENCE_PREFIXES = ("section_padding", "section_slack")
_LOW_BITS_MAX = 3            # a 2-bit-per-byte embed turns zero padding into values 0..3
_MIN_EVIDENCE_BYTES = 4      # fewer non-zero padding bytes than this is treated as noise
_FILL_DOMINANCE = 0.9        # share of one repeated non-zero byte that makes padding a toolchain fill


class BinaryDetector(BaseDetector):
    name = "binary"
    supported_extensions = [".elf", ".exe", ".dll", ".bin"]

    def analyze(self, file_bytes: bytes, filename: str = "") -> DetectionResult:
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

        view = np.frombuffer(file_bytes, dtype=np.uint8)
        findings: list[dict] = []
        evidence_regions = 0
        evidence_bytes = 0
        two_bit_regions = 0
        informational = 0
        scanned = 0

        for start, end, label in regions:
            if end <= start or start < 0 or end > len(file_bytes):
                continue
            chunk = view[start:end]
            nonzero = int(np.count_nonzero(chunk))
            if not label.startswith(_EVIDENCE_PREFIXES):
                informational += 1 if nonzero else 0
                continue
            scanned += 1
            if nonzero == 0 or _is_toolchain_fill(chunk):
                continue
            evidence_regions += 1
            evidence_bytes += nonzero
            findings.append({
                "field": label,
                "description": f"non-zero bytes in a normally zero-filled padding region ({nonzero} of {len(chunk)} bytes)",
                "suspicion": "high" if nonzero > 16 else "medium",
            })
            if nonzero >= _MIN_EVIDENCE_BYTES and int(np.max(chunk)) <= _LOW_BITS_MAX:
                two_bit_regions += 1
                findings.append({
                    "field": label,
                    "description": "padding holds only values 0-3: the signature of a 2-bit-per-byte slack embed",
                    "suspicion": "high",
                })

        extracted = None
        try:
            if btype == "PE":
                from core.binary.pe import PEEncoder
                extracted = PEEncoder().decode(file_bytes)
            else:
                from core.binary.elf import ELFEncoder
                extracted = ELFEncoder().decode(file_bytes)
        except ValueError as exc:
            log.debug("binary: no extractable payload: %s", exc)

        if extracted is not None:
            confidence = 1.0
            findings.insert(0, {
                "field": "Slack Space",
                "description": "Valid StegoForge payload identified and extracted",
                "suspicion": "high",
            })
        elif evidence_bytes >= _MIN_EVIDENCE_BYTES:
            confidence = 0.8 if (two_bit_regions or evidence_bytes > 16) else 0.5
        else:
            confidence = 0.0

        detected = extracted is not None or evidence_bytes >= _MIN_EVIDENCE_BYTES
        res = DetectionResult(
            method=self.name,
            detected=detected,
            confidence=confidence,
            details={
                "binary_type": btype,
                "regions_scanned": scanned,
                "regions_with_data_ignored": informational,
                "suspicious_regions": evidence_regions,
                "two_bit_pattern_regions": two_bit_regions,
                "interpretation": (
                    "Valid payload extracted or non-zero data in zero-filled padding"
                    if detected else "Padding is clean; note/overlay data is not treated as slack"
                ),
            },
            findings=findings,
        )
        res.extracted_payload = extracted
        return res


def _is_toolchain_fill(chunk: np.ndarray) -> bool:
    """True for padding made of one repeated non-zero byte (0x90/0xCC/0xFF/'X'), which toolchains do emit.

    A handful of other bytes is tolerated (a rewriter may patch a few of them). Zero is excluded on
    purpose: a short payload in an otherwise zero-filled region is exactly what this detector looks for.
    """
    top = int(np.bincount(chunk, minlength=256).argmax())
    return top != 0 and float(np.count_nonzero(chunk == top)) >= _FILL_DOMINANCE * len(chunk)


def _elf_slack_regions(data: bytes):
    from core.binary.elf import parse_elf_regions
    return parse_elf_regions(data)


def _pe_slack_regions(data: bytes):
    from core.binary.pe import parse_pe_regions
    return parse_pe_regions(data)
