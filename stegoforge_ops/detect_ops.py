"""StegoForge ops split — canonical implementations (imported by stegoforge.py for compat)."""
from __future__ import annotations

import logging
import re
import tempfile

from pathlib import Path
from typing import Any


from detect.base import DetectionResult
from stegoforge_ops.registry import (
    _is_audio_ext,
    _is_binary_ext,
    _is_document_ext,
    _is_image_ext,
    _is_video_ext,
)
from core.version import __version__ as APP_VERSION

log = logging.getLogger(__name__)

def op_detect(
    file: str,
    chi2: bool,
    rs: bool,
    exif: bool,
    blind: bool,
    ml: bool,
    fingerprint: bool,
    binary: bool,
    all_detectors: bool,
    json_mode: bool,
    case_id: str | None = None,
) -> dict:
    import hashlib as _hl

    file_path = Path(file)
    if not file_path.exists():
        raise OSError(f"File not found: {file}")

    file_bytes = file_path.read_bytes()
    file_sha256 = _hl.sha256(file_bytes).hexdigest()
    file_path = Path(file)
    if not file_path.exists():
        raise OSError(f"File not found: {file}")

    file_bytes = file_path.read_bytes()
    filename = file_path.name
    ext = file_path.suffix.lower()
    results = []

    is_image = _is_image_ext(ext)
    is_audio = _is_audio_ext(ext)
    is_video = _is_video_ext(ext)
    is_document = _is_document_ext(ext)
    is_pdf = ext == ".pdf"
    is_binary = _is_binary_ext(ext) or file_bytes.startswith(b"\x7fELF") or file_bytes.startswith(b"MZ")
    any_requested = any([chi2, rs, exif, blind, ml, fingerprint, binary, all_detectors])

    if (chi2 or all_detectors) and is_image:
        from detect.chi2 import Chi2Detector
        results.append(Chi2Detector().analyze(file_bytes, filename))
    if (rs or all_detectors) and is_image:
        from detect.rs import RSDetector
        results.append(RSDetector().analyze(file_bytes, filename))
    if exif or all_detectors:
        from detect.exif import EXIFDetector
        results.append(EXIFDetector().analyze(file_bytes, filename))
    if blind or all_detectors:
        if is_video:
            results.append(_VideoAudioBlindDetector().analyze(file_bytes, filename))
        else:
            from detect.blind import BlindExtractor
            results.append(BlindExtractor().analyze(file_bytes, filename))
    if (fingerprint or all_detectors) and is_image:
        from detect.fingerprint import FingerprintDetector
        results.append(FingerprintDetector().analyze(file_bytes, filename))
    if (binary or all_detectors) and is_binary:
        from detect.binary import BinaryDetector
        results.append(BinaryDetector().analyze(file_bytes, filename))
    if (ml or all_detectors) and is_image:
        from detect.ml_steganalysis import MLSteganalysisDetector
        classical = {
            "chi2": next((r.confidence for r in results if r.method == "chi2"), 0.0),
            "rs": next((r.confidence for r in results if r.method == "rs"), 0.0),
        }
        results.append(MLSteganalysisDetector().analyze(file_bytes, filename, classical=classical))
    if (all_detectors or (exif and blind)) and is_audio:
        from detect.audio_anomaly import AudioAnomalyDetector
        results.append(AudioAnomalyDetector().analyze(file_bytes, filename))
    if (all_detectors or (exif and blind)) and is_pdf:
        from detect.pdf_anomaly import PDFAnomalyDetector
        results.append(PDFAnomalyDetector().analyze(file_bytes, filename))
    if (all_detectors or (exif and blind)) and is_document and not is_pdf:
        from detect.document_anomaly import DocumentAnomalyDetector
        results.append(DocumentAnomalyDetector().analyze(file_bytes, filename))
    if (all_detectors or (exif and blind)) and is_video:
        from detect.video_anomaly import VideoAnomalyDetector
        results.append(VideoAnomalyDetector().analyze(file_bytes, filename))

    if not results:
        if any_requested:
            # Caller explicitly selected detectors that don't apply to this
            # file type — honor the choice and report zero runs instead of
            # silently running unrelated detectors.
            return {
                "status": "success",
                "file": str(file_path),
                "detectors_run": 0,
                "results": [],
                "note": "Requested detectors do not apply to this file type",
            }
        # Default: run all applicable detectors for the file type
        from detect.exif import EXIFDetector
        from detect.blind import BlindExtractor
        results = [EXIFDetector().analyze(file_bytes, filename)]
        if is_video:
            results.append(_VideoAudioBlindDetector().analyze(file_bytes, filename))
        else:
            results.append(BlindExtractor().analyze(file_bytes, filename))
        if is_image:
            from detect.chi2 import Chi2Detector
            from detect.rs import RSDetector
            from detect.fingerprint import FingerprintDetector
            from detect.ml_steganalysis import MLSteganalysisDetector

            chi2_r = Chi2Detector().analyze(file_bytes, filename)
            rs_r = RSDetector().analyze(file_bytes, filename)
            results.extend([chi2_r, rs_r, FingerprintDetector().analyze(file_bytes, filename)])
            results.append(MLSteganalysisDetector().analyze(
                file_bytes,
                filename,
                classical={"chi2": chi2_r.confidence, "rs": rs_r.confidence},
            ))
        if is_binary:
            from detect.binary import BinaryDetector
            results.append(BinaryDetector().analyze(file_bytes, filename))
        if is_audio:
            from detect.audio_anomaly import AudioAnomalyDetector
            results.append(AudioAnomalyDetector().analyze(file_bytes, filename))
        if is_pdf:
            from detect.pdf_anomaly import PDFAnomalyDetector
            results.append(PDFAnomalyDetector().analyze(file_bytes, filename))
        if is_document and not is_pdf:
            from detect.document_anomaly import DocumentAnomalyDetector
            results.append(DocumentAnomalyDetector().analyze(file_bytes, filename))
        if is_video:
            from detect.video_anomaly import VideoAnomalyDetector
            results.append(VideoAnomalyDetector().analyze(file_bytes, filename))

    return {
        "status": "success",
        "report_version": 1,
        "tool_version": APP_VERSION,
        "file": str(file_path),
        "file_sha256": file_sha256,
        "case_id": case_id,
        "detectors_run": len(results),
        "results": [_result_to_dict(r) for r in results],
    }


def op_ctf(
    file: str,
    json_mode: bool,
    save_payloads: bool = True,
    output_dir: str | None = None,
    case_id: str | None = None,
) -> dict:
    """Run all detectors and provide a comprehensive CTF-style report.

    Args:
        save_payloads: Write extracted payloads to disk. Disable for
            read-only forensic triage (no evidence-directory mutation).
        output_dir: Directory for extracted payloads (defaults to source dir).
    """
    file_path = Path(file)
    if not file_path.exists():
        raise OSError(f"File not found: {file}")

    file_bytes = file_path.read_bytes()
    filename = file_path.name
    file_size = len(file_bytes)
    ext = file_path.suffix.lower()

    from detect.exif import EXIFDetector
    from detect.blind import BlindExtractor

    is_image = _is_image_ext(ext)
    is_audio = _is_audio_ext(ext)
    is_video = _is_video_ext(ext)
    is_binary = _is_binary_ext(ext) or file_bytes.startswith(b"\x7fELF") or file_bytes.startswith(b"MZ")

    detectors: list[Any] = []
    if is_image:
        from detect.chi2 import Chi2Detector
        from detect.rs import RSDetector
        from detect.fingerprint import FingerprintDetector

        detectors.extend([Chi2Detector(), RSDetector(), FingerprintDetector()])
    else:
        detectors.extend([
            _SkippedDetector("chi2", "Image-only chi-square detector skipped for this file type"),
            _SkippedDetector("rs", "Image-only RS detector skipped for this file type"),
        ])

    if is_video:
        detectors.extend([EXIFDetector(), _VideoAudioBlindDetector()])
    else:
        detectors.extend([EXIFDetector(), BlindExtractor()])

    if is_audio:
        from detect.audio_anomaly import AudioAnomalyDetector
        detectors.append(AudioAnomalyDetector())
    if ext == ".pdf":
        from detect.pdf_anomaly import PDFAnomalyDetector
        detectors.append(PDFAnomalyDetector())
    if _is_document_ext(ext) and ext != ".pdf":
        from detect.document_anomaly import DocumentAnomalyDetector
        detectors.append(DocumentAnomalyDetector())

    if is_image:
        from detect.ml_steganalysis import MLSteganalysisDetector
        detectors.append(MLSteganalysisDetector())
    if is_binary:
        from detect.binary import BinaryDetector
        detectors.append(BinaryDetector())
    if is_video:
        from detect.video_anomaly import VideoAnomalyDetector
        detectors.append(VideoAnomalyDetector())

    results: list[DetectionResult] = []
    for det in detectors:
        if getattr(det, "name", "") == "ml":
            chi2_conf = next((r.confidence for r in results if r.method == "chi2"), 0.0)
            rs_conf = next((r.confidence for r in results if r.method == "rs"), 0.0)
            results.append(det.analyze(file_bytes, filename, classical={"chi2": chi2_conf, "rs": rs_conf}))
        else:
            results.append(det.analyze(file_bytes, filename))

    # Save extracted payloads from any successful keyless extraction
    saved_files = []
    if save_payloads:
        out_base = Path(output_dir) if output_dir else file_path.parent
        out_base.mkdir(parents=True, exist_ok=True)
        for idx, r in enumerate(results, start=1):
            if r.extracted_payload:
                method_slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", r.method or f"detector{idx}")
                save_path = out_base / f"extracted_{file_path.stem}_{idx:02d}_{method_slug}.bin"
                save_path.write_bytes(r.extracted_payload)
                saved_files.append(str(save_path))
    else:
        pass

    overall_confidence = max((r.confidence for r in results), default=0.0)
    any_detected = any(r.detected for r in results)

    ctf_notes = []
    if not save_payloads:
        ctf_notes.append("save_payloads=False: extracted payloads held in memory only.")
    if is_image:
        chi2_r = next((r for r in results if r.method == "chi2"), None)
        rs_r = next((r for r in results if r.method == "rs"), None)
        if chi2_r and rs_r and chi2_r.confidence < 0.3 and rs_r.confidence < 0.3:
            ctf_notes.append(
                "Clean chi-square/RS scores do not rule out adaptive embedding; run ML analysis when available."
            )
    if is_audio:
        ctf_notes.append("Audio file detected: image-only detectors were labeled SKIPPED and audio anomaly scan was included.")
    if is_video:
        ctf_notes.append("Video file detected: chi-square/RS are skipped and video anomaly scan is included.")
    if is_binary:
        ctf_notes.append("Binary file detected: binary slack/entropy analysis included.")
    if ext == ".pdf":
        ctf_notes.append("PDF file detected: PDF structural anomaly scan included.")
    if _is_document_ext(ext) and ext != ".pdf":
        ctf_notes.append("Document file detected: Office/text anomaly scan included.")

    import hashlib as _hl2

    return {
        "status": "success",
        "report_version": 1,
        "tool_version": APP_VERSION,
        "file": str(file_path),
        "file_sha256": _hl2.sha256(file_bytes).hexdigest(),
        "case_id": case_id,
        "file_size": file_size,
        "overall_verdict": "STEGO DETECTED" if any_detected else "CLEAN",
        "overall_confidence": round(overall_confidence, 4),
        "results": [_result_to_dict(r) for r in results],
        "saved_payloads": saved_files,
        "notes": ctf_notes,
    }


class _SkippedDetector:
    def __init__(self, name: str, reason: str):
        self.name = name
        self._reason = reason

    def analyze(self, file_bytes: bytes, filename: str = ""):
        from detect.base import DetectionResult
        return DetectionResult(
            method=self.name,
            detected=False,
            confidence=0.0,
            details={"skipped": True, "interpretation": self._reason},
        )


class _VideoAudioBlindDetector:
    name = "blind-audio"

    def analyze(self, file_bytes: bytes, filename: str = ""):
        import subprocess

        from detect.blind import BlindExtractor
        from detect.base import DetectionResult
        from core.audio._convert import _ffmpeg_cmd

        ffmpeg_cmd = _ffmpeg_cmd()
        if not ffmpeg_cmd:
            return DetectionResult(
                method=self.name,
                detected=False,
                confidence=0.0,
                details={
                    "skipped": True,
                    "interpretation": "ffmpeg unavailable for video audio-track extraction",
                },
            )

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as in_tmp:
            in_tmp.write(file_bytes)
            in_tmp.flush()
            in_path = in_tmp.name

        try:
            proc = subprocess.run(
                [
                    ffmpeg_cmd,
                    "-y",
                    "-i",
                    in_path,
                    "-vn",
                    "-f",
                    "wav",
                    "pipe:1",
                ],
                capture_output=True,
                timeout=30,
            )
            if proc.returncode != 0 or not proc.stdout:
                return DetectionResult(
                    method=self.name,
                    detected=False,
                    confidence=0.0,
                    details={
                        "skipped": True,
                        "interpretation": "Audio track extraction failed for video blind analysis",
                    },
                )

            r = BlindExtractor().analyze(proc.stdout, "video_audio.wav")
            r.method = self.name
            return r
        finally:
            Path(in_path).unlink(missing_ok=True)


def _result_to_dict(result) -> dict:
    return {
        "method": result.method,
        "detected": result.detected,
        "confidence": result.confidence,
        "details": result.details,
        "findings": getattr(result, "findings", []),
        "has_payload": result.extracted_payload is not None,
    }


