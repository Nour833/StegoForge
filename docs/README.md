# StegoForge Documentation

## Contents

- `API.md` — Python API (`op_encode`, `op_decode`, `op_detect`, `op_ctf`, `op_capacity`, `op_diff`, `op_batch_encode`)
- `PROTOCOL.md` — wire formats (`SFRG` v1/v2, obfuscated headers, `DCOY` legacy + length-prefix v2, `SKX1/SKX2`, dead-drop HTTP)
- `METHODS.md` — carrier/method capacity + stealth + survival notes
- `stegoforge schema [--json] [NAME]` — `--json` output schemas (human Markdown, or machine JSON Schema); the files live in `stegoforge_ops/schemas/` so they ship with every install
- `THREAT-MODEL.md` — what StegoForge protects against (and does not)
- `OFFLINE.md` — offline install (ffmpeg, ONNX), air-gap notes
- `ERRORS.md` — error catalog (fail-closed plaintext, depth, capacity, corruption)
- `MODEL-CARD.md` — ML steganalysis model card (measured TPR/FPR + sidecar integrity)
- `DETECTOR-EVAL.md` — ROC corpus results + threshold guidance
- `OPENAPI.md` — web API summary; `openapi.yaml` — machine OpenAPI 3.0
- `stegoforge.1` — man page
