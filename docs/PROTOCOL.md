# StegoForge Protocol Spec

## AES payloads (`core/crypto/aes.py`)

- v1 legacy: `SFRG(4) | salt(16) | nonce(12) | ct+tag`. AAD = none. Still decoded.
- v2: `SFRG(4) | 0x02(1) | salt(16) | nonce(12) | ct+tag`. AAD = `stegoforge-v2|<method-lower>`.
- Obfuscated (`--no-magic`, `encrypt_obfuscated`): `H(4) | 0x02 | salt | nonce | ct+tag` where `H = SHA256("stegoforge-magic-v1|"+method+"|"+password)[:4]` — no global static magic; decoders try v2 → legacy → obfuscated.
- `PROTOCOL_VERSION = 2`. New embeds use v2 when `method` is known; decoders try v2 then v1. `--require-v2` refuses legacy.
- Optional padding: `pad_to_block` (PKCS#7 to `N`, 1–256, e.g. 128) before encryption; `unpad_from_block` best-effort on decode.

## Decoy (`core/crypto/decoy.py`)

- v2 (produced): `u32 decoy_len | decoy_enc | real_enc` (unambiguous, no separator collision).
- v1 legacy (decoded only): `decoy_enc | DCOY | real_enc`.
- `split_slots` tries v2 (both slots must start with `SFRG`) then v1.

## Key exchange (`protocol/keyexchange.py`)

- `SKX1`: `SKX1 | salt | nonce | ct(private X25519)`. Session: `HKDF-SHA256(info=stegoforge-keyx-v1)`.
- `SKX2`/`v2`: peer-bound `HKDF(info=stegoforge-keyx-v2|pubA|pubB)` via `derive_session_key_hex_v2` + Ed25519 `sign_exchange/verify_exchange`, wired into CLI (`keyx initiate --sign-key-file`, `complete --verify-key-file/--peer-pub-file`, 0600 key output).
- Private files written `0o600`.

## Self-update (`stegoforge.py:op_update`)

- Upstream repo pinned (`Nour833/StegoForge`, no env override). Downloaded assets verified via cosign bundle (`STEGOFORGE_UPDATE_SIG_URL`, when cosign installed) or SHA256 pin (`STEGOFORGE_UPDATE_SHA256`); unpinned auto-apply refused unless `STEGOFORGE_UPDATE_UNPINNED=1`.

## Dead-drop (`protocol/deadrop.py`)

- `fetch_url_bytes(url, timeout, max_bytes)`: http(s) only, blocks private/link-local/loopback/metadata hosts, status-checked, capped streaming (limits default to 20s / 64MiB via `StegoConfig`).
- `upload_bytes`: PUT/POST octet-stream, size-capped.
- `monitor_loop(..., max_iterations=None)`: first poll is baseline (no fire), `seen` bounded to 1024.

## Carrier magics (detectable by design)

`SFRG`, `DCOY`(legacy), `WETP`, `SFEL`, `SFPE`, `SFVD`, `SFVM`, `SFTC`, `SFTM`, `/StegoData`, `SFRG_PDF`, `word/custom/stegodata.xml`, `SFRG_OFFICE`. Static headers aid forensics; do not claim invisibility for PDF/Office/decoy modes. See `THREAT-MODEL.md`.
