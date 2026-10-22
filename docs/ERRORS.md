# StegoForge Error Catalog

With `--json`, an error is `{"status": "error", "message": "...", "code": "<code>"}`. `code` is present for the typed errors below and is stable; messages may be reworded. In text mode the error goes to **stderr** (`error ...`, then a `hint ...` line when one is known) and stdout stays empty.

| Code | Meaning |
|---|---|
| `decryption-failed` | Wrong passphrase, wrong method, damaged data: one message for all three |
| `plaintext-refused` | No key and no explicit `--allow-plaintext` |
| `weak-passphrase` | Refused under `--enforce-strong-pass` |
| `empty-payload` | Zero-length payload |
| `capacity-exceeded` | Encrypted payload does not fit; the message lists remedies |
| `corrupted-carrier` | The carrier could not be parsed, or a self-check failed |
| `bad-depth` | Bit depth outside 1-4 |

- `Depth must be 1-4` — `core/bits.py:validate_depth`, `op_encode/capacity`, web forms.
- `Payload ... is empty — refusing ... zero-length` — encode-side empty policy.
- `Refusing plaintext embed without a key` — pass `-k`, `STEGOFORGE_KEY`, or `--allow-plaintext` / `allow_plaintext=True` (`STEGOFORGE_ALLOW_PLAINTEXT` bypass for scripts).
- `Encrypted payload too large ... Gap ... Suggestions` — capacity with depth/adaptive/compress hints.
- `Failed to decode payload: ... Last error: ...` / `... Tried: m1, m2, ...` — wrong key/method/corruption aggregate (no oracle beyond generic AES message). `Last error` is shown when a method was named or a payload structure was found but would not decrypt; otherwise the methods that were tried are listed.
- `Decryption failed — wrong password or corrupted data` — unified for header/wrong-key/truncation.
- `Corrupted ... (decompression failed)` — PDF/Office zlib cap failures.
- `Corrupted wet paper payload (error correction failed)` — Reed-Solomon failure.
- `Corrupted ELF/PE region table` — OOB offsets clamped/rejected.
- `video-dct: the video has too few usable frames for this payload` — see `capacity`; `self-check failed` means the lossless re-encode did not return the payload and no file is written.
- `Requested detectors do not apply` — explicit mismatched `op_detect` returns 0 runs.
- `No TCP covert payload found` / `Invalid listen-ip/port` — network validation.
- Web: `Depth must be 1-4`, upload size limits, `Missing or invalid web token` (401), generic `Encode/decode/detect/CTF/capacity failed` (500, no internals).
