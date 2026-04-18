# Changelog

All notable changes to StegoForge are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.1.0] — 2026-04-17

### 🚀 New CLI Commands

- **`stegoforge diff`** — Compare an original carrier against its stego version.
  Reports changed pixels / differing bytes, plus saves an amplified heatmap PNG
  that visually highlights every modified region.
  ```
  stegoforge diff -c cover.png -s stego.png
  stegoforge diff -c cover.png -s stego.png --save-heatmap heat.png --json
  ```

- **`stegoforge batch`** — Encode a payload into an entire directory of carriers in one command.
  Supported formats: PNG, BMP, TIFF, WEBP, JPG, GIF, WAV, MP3, FLAC, OGG,
  MP4, MKV, AVI, PDF, DOCX, XLSX, TXT. Displays a live Rich table with
  per-file status, method, capacity, and output path.
  ```
  stegoforge batch -d ./images/ -p secret.txt -k mykey
  stegoforge batch -d ./carriers/ -p msg.pdf -k mykey -o ./out/ --depth 2
  ```

- **`stegoforge completion`** — Generate tab-completion scripts for bash, zsh, and fish.
  ```
  eval "$(stegoforge completion bash)"    # add to ~/.bashrc
  eval "$(stegoforge completion zsh)"     # add to ~/.zshrc
  stegoforge completion fish | source
  ```

### ✨ CLI Enhancements

- **Stealth score** added to `stegoforge capacity` output — a composite 0–100 rating
  (weighted by chi-square resistance, RS resistance, ML evasion, and perceptual
  invisibility) shown as a colour bar for each method.
- **Smart capacity-exceeded errors** — when a payload is too large, StegoForge now
  shows the exact gap in bytes, then lists accurate suggestions:
  which `--depth` level would fit the payload, whether `adaptive-lsb` would help,
  and whether compressing the payload first is a viable option.
- **`STEGOFORGE_KEY` environment variable** — both `encode` and `decode` now fall
  back to this env var when `-k / --key` is not provided, so passwords no longer
  need to appear in shell history or CI scripts.
- **Interactive menu** updated with `d` (Diff) and `b` (Batch) entries.

### 🌐 Web UI Enhancements

- **Payload preview in Decode tab** — after successful decoding the payload is
  rendered inline: images show as `<img>`, audio plays via `<audio>`, text
  appears in a scrollable pane. No file-system access needed.
- **Smart download extension** — the Decode and CTF tabs now correctly name the
  downloaded file (e.g. `decoded_payload.png`, `decoded_payload.mp3`) instead of
  always using `.bin`, based on magic-byte detection covering 15 common formats.
- **CTF SFRG blob advisory** — when the blind extractor finds a `SFRG`-magic payload
  (a StegoForge-encrypted blob), the UI shows a clear advisory explaining how to
  decrypt it with the correct key.
- **Key strength meter** — live Shannon-entropy bar under every passphrase input
  (Encode and Decode tabs), scored 0-100 from length, character variety, and entropy.
- **Carrier image preview** — dropping an image carrier in the Encode tab shows
  an immediate thumbnail preview.
- **Mobile hamburger nav** — the header navigation collapses behind a hamburger on
  screens ≤ 600 px wide.
- **Artifact cleanup** — old web temp files (> 1 hour) are cleaned up on startup.

### 🐛 Bug Fixes

- **B1** — Fixed `DeprecationWarning: Image.Image.getdata` in `core/image/palette.py`
  (Pillow 14 compatibility). Uses `numpy.array(img).flatten()` instead.
- **B2** — Replaced hardcoded `/tmp/stegoforge_stdin_*.bin` paths in `cmd_detect`
  and `cmd_ctf` stdin handlers with `tempfile.mkstemp()` for cross-platform safety.
- **B3** — Removed dead code block (unreachable dashboard panel after `return result`
  in `op_update`).
- **B6** — Web artifact temp files (prefixed `stegoforge_web_artifact_`) are now
  automatically deleted on startup if older than 1 hour.

---

## [1.0.0] — 2026-04-14  *(Initial Public Release)*

### 🎉 First release

StegoForge launched on GitHub and received **41 stars + 13 forks** within 72 hours.

#### Carrier support (20 encoding methods)
| Carrier | Methods |
|---------|---------|
| **Image** | LSB · Adaptive-LSB · Fingerprint-LSB · DCT (JPEG) · Alpha · Palette |
| **Audio** | LSB · Phase · Spectrogram |
| **Video** | DCT · Motion-vector |
| **Document** | Unicode zero-width · PDF · DOCX · XLSX |
| **Binary** | ELF slack · PE slack |
| **Network** | IP-ID · TCP-Seq · TTL · Timing channel |
| **Linguistic** | ML-guided cover-text generation |

#### Detection engines (11 engines)
Chi-square · RS Analysis · EXIF/Metadata · blind brute-force · ML (ONNX) ·
PRNU/Fingerprint · Binary slack · Survival simulator

#### Core features
- AES-256-GCM encryption with Argon2id KDF
- Reed-Solomon wet-paper protection for JPEG social-media survival
- Dual payload (decoy/real) deniability
- X25519 ephemeral key exchange over dead-drop carriers
- Dead-drop protocol: post / check / monitor
- Batch CTF forensic analysis (`--batch`)
- Platform survivability profiles: Twitter, Instagram, Telegram, Discord,
  WhatsApp, Facebook, TikTok, LinkedIn, Reddit, Signal
- Cross-platform binaries (Linux, macOS, Windows) via GitHub Actions
- Web UI: glassmorphism dark theme, SSE streaming, capacity matrix
- Auto-update via GitHub releases

[1.1.0]: https://github.com/nourali460/StegoForge/releases/tag/v1.1.0
[1.0.0]: https://github.com/nourali460/StegoForge/releases/tag/v1.0.0
