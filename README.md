
<div align="center">

```text
███████╗████████╗███████╗ ██████╗  ██████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔════╝╚══██╔══╝██╔════╝██╔════╝ ██╔═══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
███████╗   ██║   █████╗  ██║  ███╗██║   ██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
╚════██║   ██║   ██╔══╝  ██║   ██║██║   ██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
███████║   ██║   ███████╗╚██████╔╝╚██████╔╝██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚══════╝   ╚═╝   ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

  ❯ Detect What Others Hide  ·  Survive Forensics
  Hide in Images  ·  Hide in Audio  ·  Hide in Documents  ·  Hide in Video

  🚀 v1.0.0  ·  🛡️ 20 encoding methods  ·  🔍 11 detection engines  ·  🔐 AES-256-GCM

  Made by nour833

╭────────┬────────────────┬───────────────────────────────────────────────╮
│  1     │  Encode        │  Embed a secret payload in any carrier        │
│  2     │  Decode        │  Extract & decrypt a hidden payload           │
│  3     │  Detect        │  Analyze a file for hidden content            │
│  4     │  CTF Mode      │  Run all detectors, get full forensic report  │
│  5     │  Capacity      │  Check how much data a carrier can hold       │
│  6     │  Web UI        │  Launch the local web interface               │
│  7     │  Survival      │  Platform survivability simulation            │
│  8     │  Dead Drop     │  Post/check/monitor covert channel            │
│  q     │  Quit          │  Exit StegoForge                              │
╰────────┴────────────────┴───────────────────────────────────────────────╯
```

**The most complete open-source steganography toolkit.**  
Hide in images. Hide in audio. Hide in documents. Detect what others hide. Survive forensics.

Made by nour833.

---

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)
![CTF](https://img.shields.io/badge/CTF-Ready-red?style=flat-square)

</div>

---

## What is StegoForge?

StegoForge is a **modular, extensible steganography toolkit** that covers the full spectrum — from embedding payloads into images, audio, video, documents, binaries, and controlled network channels, to detecting and extracting hidden data from suspicious files. Built for security researchers, CTF players, and digital forensics practitioners.

It does not try to be one thing. It tries to be everything stego-related, done properly.

```
$ stegoforge encode --carrier cover.png --payload secret.txt --key "mypassword" --method lsb
[+] Payload encrypted with AES-256-GCM
[+] Embedded 2048 bits across RGB channels (1-bit depth)
[+] Output: cover_stego.png
[+] Statistical profile: indistinguishable from baseline (chi² = 0.021)

$ stegoforge ctf --file suspicious.mp3
[*] Running all detectors on suspicious.mp3 ...
[⏭] Chi-square LSB anomaly      SKIPPED
[⏭] RS analysis                 SKIPPED 
[!] Blind extractor found payload at: audio-lsb, depth=1, AES encrypted blob
[+] Extracted 412 bytes → saved to extracted_payload.bin
```

---

## Feature Overview

```
stegoforge/
├── Image Carriers          PNG · JPEG · BMP · GIF · WebP
│   ├── LSB / Adaptive LSB  1–4 bit depth + WOW-style content-aware cost ordering
│   ├── DCT + JND-safe cap  JPEG frequency-domain embedding + Watson-style perceptual budget
│   ├── Fingerprint LSB     PRNU-aware embedding mode
│   └── Alpha / Palette     Transparency and indexed-color channels
│
├── Video Carriers          MP4 · WebM
│   ├── Video DCT           Keyframe embedding with block-cost ranking
│   └── Video Motion        Temporal+texture masked block embedding (MP4)
│
├── Audio Carriers          WAV · FLAC · MP3 · OGG
│   ├── Sample LSB          Psychoacoustic-style cost-ordered PCM LSB
│   ├── Phase coding        Segment-phase encoding
│   └── Spectrogram art     Visual payloads in spectrum domain
│
├── Document Carriers       TXT · PDF · DOCX · XLSX
│   ├── Unicode whitespace  Adaptive insertion-point ranking (ZWSP/ZWNJ/ZWJ)
│   ├── Linguistic mode     Key-aware synonym-channel text steganography
│   ├── PDF streams         Object/stream/metadata injection
│   └── Office XML          Custom XML parts and streams
│
├── Binary Carriers         ELF · PE/EXE/DLL (CLI)
│   ├── ELF slack/notes     2-bit masked region-cost embedding
│   └── PE slack/overlay    2-bit masked region-cost embedding
│
├── Network Covert Channels (CLI)
│   ├── TCP field channels  ip_id, tcp_seq, ttl
│   └── Timing channel      Inter-packet delay encoding
│
├── Crypto + Survivability
│   ├── AES-256-GCM + Argon2
│   ├── Decoy mode          Dual-payload plausible deniability
│   ├── Wet-paper wrapping  Reed-Solomon resilience wrapper
│   └── Platform profiles   Social-media-aware method selection/simulation
│
└── Interfaces
  ├── CLI                 Hybrid-first grouped method selection + full command mode
  ├── Web UI (Flask)      Grouped method pills, hybrid badges, local SSE streaming
  └── CTF mode            One command, all relevant detectors, ranked report
```

---

## Installation

```bash
git clone https://github.com/youruser/stegoforge
cd stegoforge
pip install -r requirements.txt
pip install -r requirements-web.txt
pip install -e .
```

Then run:
```bash
stegoforge web  # opens at http://localhost:5000
```

**Requirements:** Python 3.10+, pip. No root needed.

**Runtime dependencies for all features:**
```bash
# System ffmpeg is recommended for video/audio performance.
sudo apt install ffmpeg
```

If system ffmpeg is unavailable, StegoForge can use the bundled fallback from
`imageio-ffmpeg` (installed via `requirements.txt`).

For real ML steganalysis, `onnxruntime` and `huggingface_hub` are required
(already included in `requirements.txt`).

ML steganalysis uses a real ONNX model fetched from Hugging Face on first run
and cached in `models/srnet_lite.onnx`.
You can override source with:
`STEGOFORGE_ML_HF_REPO`, `STEGOFORGE_ML_HF_FILE`, and optional `HF_TOKEN`.

---

## Interactive Menu (Recommended for Beginners!) 🎨

Don't want to memorize terminal commands? Just run the tool on its own to access the interactive CLI!

```bash
stegoforge
```

The menu now includes a cinematic startup sequence with centered signature lines, a clearer "Ready to forge covert channels" status, and smoother transitions between sections (Encode, Decode, Detect, CTF, and more).

The interactive flow still guides you step-by-step through encoding, decrypting payloads, running CTF forensics, or spinning up the Drag-and-Drop Web UI.
Encode method selection is grouped by category with hybrid methods shown first for easier choosing.

Want instant startup for automation or demos?

```bash
STEGOFORGE_FAST_UI=1 stegoforge
```

Want to tune animation pacing instead of disabling it fully?

```bash
STEGOFORGE_UI_STAGE_DELAY=0.45 STEGOFORGE_UI_TRANSITION_DELAY=0.55 stegoforge
```


---

## Command Line Usage

### Encode a payload

```bash
# Basic LSB into PNG
stegoforge encode -c photo.png -p message.txt -k "passphrase"

# JPEG DCT with custom bit depth
stegoforge encode -c photo.jpg -p secret.bin -k "key" --method dct

# Spectrogram art — hide an image inside audio
stegoforge encode -c music.wav -p logo.png --method spectrogram

# Office document covert channel
stegoforge encode -c report.docx -p payload.txt -k "key" --method docx

# Decoy mode — two keys, two payloads
stegoforge encode -c photo.png -p real_secret.txt -k "realkey" \
                  --decoy decoy_message.txt --decoy-key "duresskey"
```

### Decode a payload

```bash
stegoforge decode -f photo_stego.png -k "passphrase"
stegoforge decode -f music_stego.wav -k "key" --method phase
```

### Detection & forensics

```bash
# Run everything at once (CTF mode — recommended)
stegoforge ctf -f suspicious.png
stegoforge ctf -f secret_audio.mp3  # Audio blind-extraction fully supported

# Individual detectors
stegoforge detect --chi2 -f image.png
stegoforge detect --rs -f image.png
stegoforge detect --exif -f document.pdf
stegoforge detect --blind -f unknown.wav   # tries all depth patterns & LSB/Phase

# JSON output for scripting
stegoforge ctf -f image.png --json > report.json

# Platform survivability simulation
stegoforge survive -c photo.png -p secret.txt -k "key" --target instagram

# Dead drop protocol
stegoforge deadrop post -c cover.png -p msg.txt -k "shared"
stegoforge deadrop check --url https://example.com/drop.png -k "shared"
stegoforge deadrop monitor --url https://example.com/drop.png -k "shared" --interval 20

# Key exchange over stego carriers
stegoforge deadrop keyx initiate -c cover.png -o keyx_init.png --local-passphrase "local-pass"
stegoforge deadrop keyx complete -f keyx_init.png --local-passphrase "local-pass" --output-key-file session.key

# Extended survivability targets
stegoforge survive -c photo.png -p secret.txt -k "key" --target facebook
stegoforge survive -c photo.png -p secret.txt -k "key" --target signal
```

### Batch mode

```bash
# Encode into all PNGs in a directory
stegoforge encode --batch ./covers/ -p secret.txt -k "key"

# Scan a whole directory for hidden data
stegoforge ctf --batch ./suspicious_files/
```

---

## Detection Methods Explained

| Method | Target | What It Finds |
|---|---|---|
| Chi-square | Images | LSB frequency distribution anomalies |
| RS Analysis | Images | Payload capacity estimation without key |
| ML Steganalysis | Images | Learned stego likelihood from ONNX model |
| Fingerprint | Images | PRNU inconsistency + in-browser tamper heatmap |
| Video anomaly | MP4/WebM | Keyframe DCT-distribution anomalies |
| Audio anomaly | WAV/FLAC/MP3/OGG | Sample bit-plane/statistical irregularities |
| PDF anomaly | PDF | Suspicious PDF structures (/EmbeddedFile, JS, tail entropy) |
| Document anomaly | TXT/DOCX/XLSX | Invisible-char / Office container anomalies |
| Binary anomaly | ELF/PE | Section-slack/entropy anomalies |
| EXIF scanner | All | Metadata, hidden thumbnails, XMP, comments |
| Blind extractor | Images/Audio/Video-audio track | Auto-tries common patterns and AES-magic payloads |

Detector routing is file-type-aware. Image-only detectors are skipped for non-image files,
and audio/video/document/binary-specific analyzers are included where applicable.
Fingerprint heatmaps are generated in-memory for web display (no root-folder artifact files).

---

## CTF Mode Output Example

```
$ stegoforge ctf --file chall.png

╔══════════════════════════════════════════════╗
║           StegoForge — CTF Report            ║
╠══════════════════════════════════════════════╣
║  File      : chall.png (1024×768, RGB PNG)   ║
║  Size      : 2.3 MB                          ║
╠══════════════════════════════════════════════╣
║  [!!] Chi-square anomaly        HIGH  94.3%  ║
║  [!!] RS estimated capacity     ~22%  pixels ║
║  [ ] DCT coefficient check      CLEAN        ║
║  [ ] Alpha channel              NOT PRESENT  ║
║  [!] EXIF comment field         NON-EMPTY    ║
╠══════════════════════════════════════════════╣
║  Blind extractor results:                    ║
║  → RGB-R, LSB-1bit, no enc → 512 bytes [!!]  ║
║  → RGB-B, LSB-2bit, AES    → encrypted blob  ║
╠══════════════════════════════════════════════╣
║  Saved: extracted_R_1bit.bin                 ║
╚══════════════════════════════════════════════╝

Note: Audio files parsed via CTF mode gracefully skip image-only forensic tooling (e.g., Chi-Square & RS Analysis are labeled `SKIPPED`) to avoid false `CLEAN` results, while seamlessly parsing PCM bitstreams directly into the upgraded audio-compatible Blind Extractor.
```

---

## Architecture

```
stegoforge/
├── core/
│   ├── image/
│   │   ├── lsb.py          LSB encode/decode, configurable depth & channels
│   │   ├── adaptive.py     WOW-style directional residual cost adaptive LSB
│   │   ├── dct.py          DCT coefficient injection for JPEG
│   │   ├── fingerprint.py  PRNU-aware embedding
│   │   ├── alpha.py        Alpha channel covert channel
│   │   └── palette.py      Indexed-color palette reordering
│   ├── audio/
│   │   ├── lsb.py          Cost-ordered PCM sample LSB embedding
│   │   ├── phase.py        Phase coding across audio segments
│   │   └── spectrogram.py  Spectrogram image embedding
│   ├── video/
│   │   ├── dct.py          Keyframe block-cost video embedding
│   │   └── motion.py       Temporal+texture masked video embedding
│   ├── binary/
│   │   ├── elf.py          ELF masked slack/notes encoder
│   │   └── pe.py           PE masked slack/overlay encoder
│   ├── network/
│   │   ├── tcp.py          TCP covert channel encoder
│   │   └── timing.py       Timing covert channel encoder
│   ├── document/
│   │   ├── unicode_ws.py   Adaptive zero-width character encoding
│   │   ├── linguistic.py   Key-aware synonym-channel linguistic stego
│   │   ├── pdf.py          PDF stream/object injection
│   │   └── office.py       DOCX/XLSX XML stream manipulation
│   └── crypto/
│       ├── aes.py          AES-256-GCM encrypt/decrypt
│       ├── kdf.py          Argon2 key derivation
│       ├── decoy.py        Dual-payload deniability system
│       └── polymorphic.py  Key-seeded encoding pattern variation
├── detect/
│   ├── chi2.py             Chi-square LSB attack
│   ├── rs.py               Regular-Singular analysis
│   ├── exif.py             Metadata forensics scanner
│   ├── blind.py            Brute-force extractor
│   ├── ml_steganalysis.py  Hugging Face-backed ONNX detector
│   ├── fingerprint.py      PRNU inconsistency detector (+ in-memory heatmap)
│   ├── audio_anomaly.py    Audio-specific anomaly detector
│   ├── pdf_anomaly.py      PDF-specific anomaly detector
│   ├── document_anomaly.py Document-specific anomaly detector
│   ├── video_anomaly.py    Video keyframe anomaly detector
│   ├── binary.py           ELF/PE anomaly detector
│   └── survival.py         Platform profile + survivability simulation
├── protocol/
│   ├── deadrop.py          Dead-drop fetch/post/monitor helpers
│   └── keyexchange.py      X25519 stego key exchange helpers
├── cli.py                  Typer-based CLI entrypoint
├── web/
│   ├── app.py              Flask local web UI
│   └── templates/
└── tests/
```

---

## Supported Formats

| Format | Encode | Decode | Detect |
|---|---|---|---|
| PNG | ✅ LSB, Alpha, Palette | ✅ | ✅ |
| JPEG | ✅ DCT | ✅ | ✅ |
| BMP | ✅ LSB | ✅ | ✅ |
| GIF | ✅ Palette | ✅ | ✅ |
| WebP | ✅ Alpha | ✅ | ✅ |
| MP4 | ✅ Video DCT, Video Motion | ✅ | ✅ |
| WebM | ✅ Video DCT | ✅ | ✅ |
| WAV | ✅ LSB, Phase, Spectrogram | ✅ | ✅ |
| FLAC | ✅ LSB, Phase | ✅ | ✅ |
| MP3 | ✅ LSB, Phase, Spectrogram | ✅ | ✅ |
| OGG | ✅ LSB, Phase, Spectrogram | ✅ | ✅ |
| PDF | ✅ Stream injection | ✅ | ✅ |
| DOCX | ✅ XML streams | ✅ | ✅ |
| XLSX | ✅ XML streams | ✅ | ✅ |
| TXT | ✅ Unicode whitespace | ✅ | ✅ |
| ELF | ✅ CLI only | ✅ | ✅ |
| PE/EXE | ✅ CLI only | ✅ | ✅ |

Social survivability targets: twitter/x, instagram, telegram, discord, whatsapp, facebook, tiktok, linkedin, reddit, signal.

---

## Contributing

Pull requests are welcome. For major changes, open an issue first.

- Follow the existing module structure — each carrier type lives in its own file
- All new methods must implement the `BaseEncoder` interface (`encode`, `decode`, `capacity`)
- Add tests under `tests/` for any new carrier or detection method
- Detection methods must also implement a confidence score (0.0–1.0)

---

## Disclaimer

> StegoForge is developed for **educational purposes**, **CTF competitions**, **digital forensics research**, and **legitimate security testing** only.
>
> Steganography itself is a neutral technology. Its use to conceal illegal content, exfiltrate data without authorization, or evade lawful monitoring is **illegal in most jurisdictions** and is entirely the responsibility of the person doing it.
>
> The author of this tool accepts no liability for any illegal, unethical, or harmful use. By using StegoForge, you agree that you are solely responsible for how you use it and that you will comply with all applicable laws in your jurisdiction.
>
> This tool does not exploit any vulnerability or cause any damage to systems. It operates entirely on files you own or have authorization to process.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Made by nour833 for the community. Use it responsibly.

**[Report a Bug](../../issues)** · **[Request a Feature](../../issues)** · **[CTF Writeups using StegoForge](../../discussions)**

</div>
