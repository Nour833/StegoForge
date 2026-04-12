"""
detect/ml_steganalysis.py - Optional ONNX-based ML steganalysis.

Training note for maintainers:
- Intended model family: SRNet-lite style binary steganalysis CNN.
- Typical training datasets: BOSSbase and BOWS2 with balanced clean/stego pairs.
- Typical labels: 0=clean, 1=stego; training covers multiple embedding rates.
- Recommended references: SRNet papers and open steganalysis repositories that
  export ONNX inference graphs for CPU execution.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from detect.base import BaseDetector, DetectionResult

MODEL_BUNDLED_REL = Path(os.getenv("STEGOFORGE_ML_BUNDLED_MODEL", "models/model_quantized.onnx").strip())
MODEL_NAME = MODEL_BUNDLED_REL.name or "model_quantized.onnx"


def bundled_model_paths() -> list[Path]:
    candidates: list[Path] = []

    # Source tree location (repo checkout).
    candidates.append((Path(__file__).resolve().parent.parent / MODEL_BUNDLED_REL).resolve())

    # PyInstaller onefile extraction dir.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append((Path(meipass) / MODEL_BUNDLED_REL).resolve())

    # Side-by-side next to executable/script.
    try:
        candidates.append((Path(sys.argv[0]).resolve().parent / MODEL_BUNDLED_REL).resolve())
    except Exception:
        pass

    # Keep order but remove duplicates.
    deduped: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        key = str(p)
        if key not in seen:
            deduped.append(p)
            seen.add(key)
    return deduped


class MLSteganalysisDetector(BaseDetector):
    name = "ml"
    supported_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff"]

    def analyze(self, file_bytes: bytes, filename: str = "", classical: dict | None = None) -> DetectionResult:
        classical = classical or {}
        self._last_model_error = ""
        try:
            import onnxruntime as ort  # type: ignore
        except Exception:
            return self._heuristic_fallback(
                file_bytes,
                classical,
                reason="onnxruntime is not installed",
                install="pip install onnxruntime",
            )

        model_path = self._ensure_model()
        if not model_path:
            return self._heuristic_fallback(
                file_bytes,
                classical,
                reason=(
                    "Model unavailable (bundled model not found)"
                    if not self._last_model_error
                    else f"Model unavailable: {self._last_model_error}"
                ),
                install=(
                    "Install onnxruntime and ensure bundled model exists at "
                    f"{MODEL_BUNDLED_REL.as_posix()}"
                ),
            )

        try:
            sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
            input_meta = sess.get_inputs()[0]
            self._validate_session(sess)
            input_name = input_meta.name
            x = self._preprocess(file_bytes, input_meta.shape)
            raw = sess.run(None, {input_name: x})[0]
            conf = self._confidence_from_output(raw)

            verdict = "CLEAN"
            if conf >= 0.7:
                verdict = "LIKELY_STEGO"
            elif conf >= 0.35:
                verdict = "SUSPICIOUS"

            hints = self._derive_hints(conf, classical)
            return DetectionResult(
                method=self.name,
                detected=conf >= 0.35,
                confidence=round(conf, 4),
                details={
                    "verdict": verdict,
                    "hints": hints,
                    "model": MODEL_NAME,
                    "model_source": "bundled",
                    "skipped": False,
                    "interpretation": f"ML detector verdict: {verdict}",
                },
            )
        except Exception as exc:
            return self._heuristic_fallback(
                file_bytes,
                classical,
                reason=f"ONNX inference failed: {exc}",
            )

    def _validate_session(self, sess) -> None:
        outputs = sess.get_outputs()
        if not outputs:
            raise ValueError("ONNX model has no outputs")

        shape = outputs[0].shape
        # Expected binary steganalysis heads are usually [N,1] or [N,2].
        if len(shape) < 2:
            return

        cls_dim = shape[-1]
        if isinstance(cls_dim, int) and cls_dim > 2:
            raise ValueError(
                f"Incompatible ONNX model output shape {shape}; expected binary steganalysis head"
            )

    def _shape_dim(self, shape_value, default: int) -> int:
        if isinstance(shape_value, int) and shape_value > 0:
            return int(shape_value)
        return int(default)

    def _preprocess(self, file_bytes: bytes, input_shape) -> np.ndarray:
        c = self._shape_dim(input_shape[1] if len(input_shape) > 1 else None, 3)
        h = self._shape_dim(input_shape[2] if len(input_shape) > 2 else None, 224)
        w = self._shape_dim(input_shape[3] if len(input_shape) > 3 else None, 224)

        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        img = img.resize((w, h), Image.BILINEAR)
        arr = np.asarray(img, dtype=np.float32) / 255.0

        if c <= 1:
            gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.float32)
            return gray[np.newaxis, np.newaxis, :, :]

        chw = np.transpose(arr, (2, 0, 1))
        if c < 3:
            chw = chw[:c, :, :]
        elif c > 3:
            pad = np.zeros((c - 3, h, w), dtype=np.float32)
            chw = np.concatenate([chw, pad], axis=0)
        return chw[np.newaxis, :, :, :]

    def _confidence_from_output(self, raw: np.ndarray) -> float:
        arr = np.asarray(raw, dtype=np.float32)
        if arr.size == 0:
            return 0.0
        if arr.size == 1:
            conf = float(arr.reshape(-1)[0])
            if conf < 0.0 or conf > 1.0:
                conf = float(1.0 / (1.0 + np.exp(-conf)))
            return float(np.clip(conf, 0.0, 1.0))

        flat = arr.reshape(-1)
        max_v = float(np.max(flat))
        exps = np.exp(np.clip(flat - max_v, -60.0, 60.0))
        probs = exps / max(float(np.sum(exps)), 1e-9)
        return float(np.clip(float(np.max(probs)), 0.0, 1.0))

    def _ensure_model(self) -> Path | None:
        # Preferred path: bundled offline model shipped with repo/release.
        for bundled in bundled_model_paths():
            if bundled.exists() and bundled.stat().st_size > 0:
                return bundled

        try:
            from core import sysmgr
            sys_model = sysmgr.MODELS_DIR / MODEL_NAME
            if sys_model.exists() and sys_model.stat().st_size > 0:
                return sys_model
        except ImportError:
            pass

        root = Path(__file__).resolve().parent.parent
        model_dir = root / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / MODEL_NAME
        if model_path.exists() and model_path.stat().st_size > 0:
            return model_path
        self._last_model_error = f"Bundled model not found. Expected file: {MODEL_BUNDLED_REL.as_posix()}"
        return None

    def _heuristic_fallback(self, file_bytes: bytes, classical: dict, reason: str, install: str | None = None) -> DetectionResult:
        # Fallback keeps the detector operational when model/runtime is unavailable.
        img = Image.open(io.BytesIO(file_bytes)).convert("L")
        arr = np.array(img, dtype=np.float32) / 255.0
        hp = np.abs(arr[:, 1:] - arr[:, :-1]).mean() + np.abs(arr[1:, :] - arr[:-1, :]).mean()
        texture_conf = float(np.clip((hp - 0.20) * 1.8, 0.0, 1.0))
        classical_conf = max(float(classical.get("chi2", 0.0) or 0.0), float(classical.get("rs", 0.0) or 0.0))
        conf = float(np.clip(0.6 * texture_conf + 0.4 * classical_conf, 0.0, 1.0))

        verdict = "CLEAN"
        if conf >= 0.7:
            verdict = "LIKELY_STEGO"
        elif conf >= 0.35:
            verdict = "SUSPICIOUS"

        details = {
            "verdict": verdict,
            "hints": self._derive_hints(conf, classical),
            "model": "heuristic-fallback",
            "model_source": "fallback",
            "skipped": False,
            "fallback_reason": reason,
            "interpretation": f"Heuristic ML fallback verdict: {verdict}",
        }
        if "Incompatible ONNX model" in reason:
            details["model_validation"] = "rejected-non-binary-output"
        if install:
            details["install"] = install

        return DetectionResult(
            method=self.name,
            detected=conf >= 0.35,
            confidence=round(conf, 4),
            details=details,
        )

    def _derive_hints(self, ml_conf: float, classical: dict) -> list[str]:
        hints = []
        chi2_conf = float(classical.get("chi2", 0.0) or 0.0)
        rs_conf = float(classical.get("rs", 0.0) or 0.0)

        if ml_conf >= 0.7 and chi2_conf < 0.3 and rs_conf < 0.3:
            hints.append("Adaptive LSB or DCT-like embedding is plausible")
        if ml_conf >= 0.7 and (chi2_conf >= 0.6 or rs_conf >= 0.6):
            hints.append("Uniform LSB-style embedding is plausible")
        if not hints and ml_conf >= 0.35:
            hints.append("Potential stego artifact detected by learned features")
        return hints
