# ML Steganalysis Model Card

- Location: `models/model_quantized.onnx` (bundled, 3.6MB) + `~/.stegoforge/models` cache.
- Runtime: `onnxruntime` via `detect/ml_steganalysis.py` (heuristic fallback when missing).
- Compatibility note (verified 2026-09-22 by loading the file): the bundled
  weights expose a **1001-class ImageNet head** (`pixel_values` in,
  `logits[batch,1001]` out), not a binary steganalysis head. Session validation
  rejects it, so the detector **always runs the heuristic fallback** in practice.
  Do not treat `ml` output as neural-network evidence until compatible weights ship.
- Fallback (calibrated 2026-09-22): texture-gradient signal only (photographic
  content scores ~0.44 whether clean or stego, hence the 0.5 flag threshold);
  classical chi2/rs priors are reported under `priors_consulted` but no longer
  blended into the score (the blend inflated clean-image scores into false
  positives). Measured fallback: TPR ~0, FPR 0 — triage-only by design, never
  fires alone.
- Integrity: `models/model_quantized.onnx.sha256` sidecar verified on load
  (`verify_model_sidecar`); additionally `STEGOFORGE_MODEL_SHA256` pin and
  `assets.sha256` manifest. No signature infrastructure (integrity only).
- Intended use: corroborating hint only; verdicts come from blind/chi2/rs/fingerprint. See `THREAT-MODEL.md`.
