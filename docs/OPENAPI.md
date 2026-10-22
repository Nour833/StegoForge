# StegoForge Web OpenAPI (summary)

Base: `http://127.0.0.1:5000`. Auth: `X-Stego-Token` (or `?token=` for plain download links) when `STEGOFORGE_WEB_TOKEN` is set. Requests whose `Host` is not loopback (or listed in `STEGOFORGE_ALLOWED_HOSTS`) and POSTs with a foreign `Origin` get 403. Encode and survive accept `allow_plaintext=1`; without it an empty key is refused with 400.

- `GET /` → HTML UI. `GET /survive` → survive tab.
- `GET /artifact/<id>` → stego artifact bytes by opaque ID (404 on unknown/expired).
- `GET /api/platform-profiles` → `{profiles}`.
- `POST /api/capacity-matrix` (multipart `file`, optional `payload`, `depth=1-4`) → `{file, payload_size, depth, rows[]}`.
- `POST /api/survive` (`carrier`, `payload`, `key`, `target`, `method`, `depth`) → `op_encode` result with `survival_test`.
- `POST /api/encode-stream` (SSE) → `progress{pct}` events then `success{result, artifact_id, download_name}` or `error`.
- `POST /api/detect-stream` (SSE) → `log` per detector then `success{report}`.
- `POST /encode` → stego bytes download. `POST /decode` → payload download.
- `POST /detect` → `{file, results[]}`. `POST /ctf` → `{verdict, confidence, results[], has_extracted_payload, notes[]}`.
- `POST /capacity`, `POST /diff` → op results. `413` returns JSON `Upload exceeds limit`.

Error shape: `{error: string}` with 400 (usage) / 401 (token) / 404 / 500 (generic, no internals).
