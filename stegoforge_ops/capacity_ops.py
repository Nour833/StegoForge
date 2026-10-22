"""StegoForge ops split — canonical implementations (imported by stegoforge.py for compat)."""
from __future__ import annotations

import logging
import os

from pathlib import Path
from typing import Any


from core.bits import validate_depth
from stegoforge_ops.encode_ops import op_encode
from stegoforge_ops.registry import (
    EXT_TO_METHOD,
    STEALTH_SCORES,
    auto_detect_method,
    get_encoder,
    get_output_path,
    _is_audio_ext,
    _is_image_ext,
)

log = logging.getLogger(__name__)

def op_capacity(carrier: str, method: str | None, depth: int) -> dict:

    validate_depth(int(depth))
    carrier_path = Path(carrier)
    if not carrier_path.exists():
        raise OSError(f"Carrier file not found: {carrier}")

    carrier_bytes = carrier_path.read_bytes()
    method = method or auto_detect_method(carrier)
    encoder = get_encoder(method)

    ext = carrier_path.suffix.lower()
    kwargs: dict[str, Any] = {"depth": depth}
    if method in ("audio-lsb", "phase", "spectrogram", "video-dct", "video-motion"):
        kwargs["ext"] = ext
    if method in ("docx", "xlsx", "office"):
        kwargs["filename"] = str(carrier_path)

    cap = encoder.capacity(carrier_bytes, **kwargs)

    result = {
        "status": "success",
        "carrier": str(carrier_path),
        "method": method,
        "depth": depth,
        "capacity_bytes": cap,
        "capacity_kb": round(cap / 1024, 2),
        "capacity_mb": round(cap / (1024 * 1024), 4),
        "stealth_score": STEALTH_SCORES.get(method, 0),
    }

    if method == "dct":
        try:
            jnd = encoder.jnd_safe_capacity(carrier_bytes)
            result["jnd_safe_dct_capacity"] = {
                "bytes": jnd,
                "kb": round(jnd / 1024, 2),
                "note": "JND-safe DCT capacity estimates perceptually conservative embedding budget",
            }
        except Exception:
            pass

    if method in ("video-dct", "video-motion"):
        try:
            from core.video.scan import scan_video

            scan = scan_video(carrier_bytes)
            usable = encoder.eligible_frames(scan.frames)
            kind = "anchor frames (every 12th)" if method == "video-dct" else "inter frames"
            result["video_context"] = {
                "duration_seconds": round(scan.duration_sec, 3),
                "frames": scan.frames,
                "keyframes": scan.keyframes,
                "usable_frames": usable,
                "capacity_note": f"up to {round(cap / 1024, 2)} KB across {usable} {kind}",
            }
        except ValueError as exc:
            log.debug("video_context scan failed: %s", exc)

    return result


def op_diff(carrier: str, stego: str, save_heatmap: str | None = None) -> dict:
    """Compare an original carrier against its stego version byte/pixel-by-pixel."""
    carrier_path = Path(carrier)
    stego_path   = Path(stego)
    for p in (carrier_path, stego_path):
        if not p.exists():
            raise OSError(f"File not found: {p}")

    ext = carrier_path.suffix.lower()
    result: dict = {"carrier": str(carrier_path), "stego": str(stego_path)}

    if _is_image_ext(ext):
        from PIL import Image
        import numpy as np

        img_a = Image.open(carrier_path).convert("RGB")
        img_b = Image.open(stego_path).convert("RGB")
        if img_a.size != img_b.size:
            img_b = img_b.resize(img_a.size, Image.Resampling.LANCZOS)

        arr_a = np.array(img_a, dtype=np.int16)
        arr_b = np.array(img_b, dtype=np.int16)
        diff  = np.abs(arr_a - arr_b)

        changed_pixels = int(np.any(diff > 0, axis=2).sum())
        total_pixels   = img_a.size[0] * img_a.size[1]
        max_delta      = int(diff.max())
        mean_delta     = float(diff.mean())

        result.update({
            "type": "image",
            "dimensions": list(img_a.size),
            "total_pixels": total_pixels,
            "changed_pixels": changed_pixels,
            "changed_percent": round(changed_pixels / total_pixels * 100, 4),
            "max_delta": max_delta,
            "mean_delta": round(mean_delta, 4),
            "heatmap": None,
        })

        # Build amplified heatmap (bright = changed pixel, dark = unchanged)
        amp = np.clip(diff.max(axis=2).astype(np.float32) * 20, 0, 255).astype(np.uint8)
        heat_img = Image.fromarray(amp, mode="L").convert("RGB")
        heat_w = min(img_a.width, 800)
        heat_h = min(img_a.height, 800)
        heat_img = heat_img.resize((heat_w, heat_h), Image.Resampling.NEAREST)
        out_heat = save_heatmap or str(
            carrier_path.with_stem(carrier_path.stem + "_diff_heatmap").with_suffix(".png")
        )
        heat_img.save(out_heat)
        result["heatmap"] = out_heat

    elif _is_audio_ext(ext):
        data_a = carrier_path.read_bytes()
        data_b = stego_path.read_bytes()
        min_len = min(len(data_a), len(data_b))
        diff_bytes = sum(1 for x, y in zip(data_a[:min_len], data_b[:min_len], strict=True) if x != y)
        diff_percent = round(diff_bytes / max(min_len, 1) * 100, 4)
        result.update({
            "type": "audio",
            "size_original": len(data_a),
            "size_stego": len(data_b),
            "differing_bytes": diff_bytes,
            "differing_percent": diff_percent,
            # Compatibility aliases used by the web UI.
            "changed_bytes": diff_bytes,
            "changed_percent": diff_percent,
        })
    else:
        data_a = carrier_path.read_bytes()
        data_b = stego_path.read_bytes()
        min_len = min(len(data_a), len(data_b))
        diff_bytes = sum(1 for x, y in zip(data_a[:min_len], data_b[:min_len], strict=True) if x != y)
        diff_percent = round(diff_bytes / max(min_len, 1) * 100, 4)
        result.update({
            "type": "binary",
            "size_original": len(data_a),
            "size_stego": len(data_b),
            "differing_bytes": diff_bytes,
            "differing_percent": diff_percent,
            # Compatibility aliases used by the web UI.
            "changed_bytes": diff_bytes,
            "changed_percent": diff_percent,
        })

    return result


def op_batch_encode(
    batch_dir: str,
    payload: str,
    key: str,
    output_dir: str | None,
    method: str | None,
    depth: int,
    wet_paper: bool,
    jobs: int = 1,
) -> dict:
    """Encode a payload into every compatible carrier file in a directory.

    Args:
        jobs: Parallel workers (>1 uses ThreadPoolExecutor; 1=sequential).
    """

    validate_depth(int(depth))
    if jobs is not None and (int(jobs) < 1 or int(jobs) > 32):
        raise ValueError("jobs must be 1-32")
    jobs = int(jobs or 1)
    key = key or os.getenv("STEGOFORGE_KEY", "")
    if not key:
        raise ValueError("Encryption key required. Pass -k / --key or set STEGOFORGE_KEY.")

    bd = Path(batch_dir)
    if not bd.is_dir():
        raise OSError(f"Batch directory not found: {batch_dir}")
    if not Path(payload).exists():
        raise OSError(f"Payload file not found: {payload}")

    if method:
        get_encoder(method)  # unknown method: fail once, up front, with the "did you mean" hint

    out_dir = Path(output_dir) if output_dir else bd
    out_dir.mkdir(parents=True, exist_ok=True)
    out_root = out_dir.resolve()

    # Supported carrier extensions minus binary/network (require special args) and bare .sfrg blobs
    skip = {".elf", ".exe", ".dll", ".bin", ".sfrg"}

    def _is_carrier(f: Path) -> bool:
        if not f.is_file() or f.suffix.lower() not in EXT_TO_METHOD or f.suffix.lower() in skip:
            return False
        if f.stem.endswith("_stego"):
            return False  # output of an earlier run
        # An output directory inside the batch directory must not be re-scanned.
        return out_root == bd.resolve() or out_root not in f.resolve().parents

    carriers = sorted(f for f in bd.rglob("*") if _is_carrier(f))

    rows: list[dict] = []
    passed = 0
    failed = 0

    def _one(cf: Path) -> dict:
        # Mirror the sub-directory layout so a/x.png and b/x.png cannot overwrite each other.
        rel = cf.relative_to(bd)
        try:
            encoder = get_encoder(method or auto_detect_method(str(cf)))
            auto_out = out_dir / rel.parent / get_output_path(str(cf), None, encoder=encoder).name
            r = op_encode(
                str(cf), payload, key, str(auto_out),
                method, depth,
                None, None, wet_paper,
                None, False, False,
                None, None, None, True,
            )
            row = {
                "file": str(rel),
                "status": "success",
                "method": r["method"],
                "output": r["output"],
                "payload_size": r["payload_size"],
                "capacity": r["capacity"],
            }
            if r.get("warnings"):
                row["warnings"] = r["warnings"]
            return row
        except (ValueError, OSError) as exc:
            return {"file": str(rel), "status": "error", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - one bad file must not abort the batch, but a bug must be visible
            log.exception("batch encode: internal error on %s", cf)
            return {"file": str(rel), "status": "error", "error": f"internal error: {type(exc).__name__}: {exc}"}

    if jobs > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=jobs) as ex:
            for row in ex.map(_one, carriers):
                rows.append(row)
                if row["status"] == "success":
                    passed += 1
                else:
                    failed += 1
    else:
        for cf in carriers:
            row = _one(cf)
            rows.append(row)
            if row["status"] == "success":
                passed += 1
            else:
                failed += 1

    return {
        "batch_dir": str(bd),
        "payload": payload,
        "total": len(carriers),
        "passed": passed,
        "failed": failed,
        "rows": rows,
    }


