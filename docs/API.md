# StegoForge Python API

Canonical implementations live in `stegoforge_ops/` (`encode_ops`, `decode_ops`,
`detect_ops`, `capacity_ops`, `registry`, `report`); `stegoforge.py` re-exports
them, so both import paths work:

```python
from stegoforge import op_encode, op_decode, op_detect, op_ctf, op_capacity, op_diff, op_batch_encode
from stegoforge_ops import op_encode  # preferred for library use
from stegoforge_ops.report import canonical_json, report_hash, chain_hash
```

## `op_encode(..., allow_plaintext=False, pad_block=0, require_v2=False, enforce_strong=False, header_mode="standard", i_understand_root=False, progress_callback=None)`

- `depth`: validated `1-4` (`DepthError`, a `ValueError`).
- `allow_plaintext`: fail-closed plaintext gate (`PlaintextRefusedError` without key/opt-in). CLI: `--allow-plaintext` / `--no-encrypt`. The web UI sends `allow_plaintext` only when the user ticks the checkbox; without a key and without it, encode is refused.
- `pad_block`: pad plaintext pre-encryption (1–256, e.g. `128`) via `core/crypto/aes.py:iso_pad` to reduce length oracle; padding is signalled by an authenticated flag, never guessed at decode time.
- `header_mode`: `"standard"` (SFRG) or `"obfuscated"` (key-derived header, `--no-magic`; incompatible with decoy mode).
- `enforce_strong`: raise `WeakPassphraseError` on weak passphrases instead of warning.
- `progress_callback(done, total)`: real encoder progress (fingerprint-lsb backend + stage markers); used by web SSE.
- Encryption: v2 method-bound AES-GCM (`encrypt_with_aad`) preferred; legacy v1 fallback on decode unless `require_v2`.
- Returns `status/method/carrier/payload_size/encrypted_size/capacity/output/depth/decoy_mode/wet_paper/...`.

## `op_decode(..., require_v2=False, i_understand_root=False)`

- Auto-tries method groups; `spectrogram` excluded from auto (watermark-only).
- Tries v2 AAD → legacy → obfuscated-header decrypt; unpads via `unpad_from_block`.
- Corrupted carriers normalized to `ValueError` (never raw `zlib.error`/`ReedSolomonError`/`struct.error`).
- Live network sniff requires `i_understand_root` (or `STEGOFORGE_I_UNDERSTAND_ROOT=1`).

## `op_detect(..., case_id=None)`

Returns `file/file_sha256/case_id/detectors_run/results`. Explicit mismatched detectors return `detectors_run=0` + note instead of silently running others. Anomaly detectors run on `--all` or `exif+blind`; default (no flags) runs all applicable.

## `op_ctf(file, json_mode, save_payloads=True, output_dir=None, case_id=None)`

Set `save_payloads=False` for read-only triage. `output_dir` redirects extracts. Includes `file_sha256/case_id`.

## `op_capacity(carrier, method, depth)`

Depth-validated. `spectrogram` capacity is honest (`120` B watermark).

## `op_batch_encode(..., jobs=1)`

`jobs=1-32`; `>1` uses `ThreadPoolExecutor`.

## `op_diff(carrier, stego, save_heatmap=None)`

Image/audio/binary diff with `changed_*` aliases for the web UI.
