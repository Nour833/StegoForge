# StegoForge Threat Model

## Protects against

- Passive carrier inspection (AES-256-GCM + Argon2id `t=3`, fresh salt/nonce per embed).
- Naive extraction (keyed traversal v2 + method-bound AAD v2 + decoy v2 framing).
- Accidental plaintext leaks (fail-closed `allow_plaintext`, weak-password warnings or `--enforce-strong-pass` refusal).
- Supply-chain accidents (update SHA/cosign pins with refuse-unpinned default, model `.sha256` sidecar + `assets.sha256`, 0600 key files, HKDF not password-KDF for DH).
- Drive-by and cross-site attacks on the local UI: `Host` allow-list (DNS rebinding), `Origin` check on every POST (cross-site form posts), anchored localhost-only CORS, constant-time token compare, POST rate limit, no inline rendering of downloads, no server paths or exception text in responses. Binding anything but loopback requires `STEGOFORGE_WEB_TOKEN`.
- Hostile files being *analysed*: every string that originates in a file (metadata, filenames, detector notes) is escaped before it reaches the page.
- SSRF via dead-drop/LLM helpers (http(s) allowlist, private-host blocks, size caps).

## Does NOT fully protect against

- Active MITM on unsigned v1 keyx (use `keyx initiate --sign-key-file` + `complete --verify-key-file` with out-of-band identity; v2 peer-bound HKDF always used on complete).
- Forensic detection when using standard headers (`SFRG`, `WETP`, `/StegoData`, Office part names are detectable by design; use `--no-magic` key-derived headers to remove the static magic — decoy mode then unavailable).
- Length oracles without `--pad-to`; transplant of legacy v1 payloads (use `--require-v2` to refuse them).
- Lossy transforms (use wet-paper + `--target`/`--test-survival`, but expect failures; video embeds are written losslessly and any lossy re-encode destroys them).
- Endpoint compromise: `-k` on argv is warned, not blocked (use `--key-file`); CPython string scrubbing is best-effort (documented limitation); `STEGOFORGE_KEY` inherited by children.
- Malicious carriers (decompression/ZIP caps + `MAX_IMAGE_PIXELS` mitigate, but media parsers remain complex).
- Detector over-trust: every detector is triage. Chi-square and RS are weak on small or adaptive payloads, the ML detector is a heuristic fallback, and an inconclusive or clean result never proves a file is clean (see `DETECTOR-EVAL.md`).

## Operator guidance

Use strong 12+ char mixed passphrases (`--enforce-strong-pass` in scripts), `--pad-to 128` for sensitive sizes, `--no-save` triage on evidence, `STEGOFORGE_WEB_TOKEN=auto` for the UI, `--require-v2` where compat allows, and verify asset hashes offline.

