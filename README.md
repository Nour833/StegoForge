<div align="center">
  <img src="https://raw.githubusercontent.com/Nour833/StegoForge/main/interface.gif" alt="StegoForge Dashboard" width="850">

  # 🛡️ StegoForge
  **The ultimate hybrid of steganography, digital forensics, and covert communications.**

  [![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
  [![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)
  [![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=for-the-badge)](https://github.com/Nour833/StegoForge/releases)
  [![GitHub Stars](https://img.shields.io/github/stars/Nour833/StegoForge?style=for-the-badge&logo=github&color=gold)](https://github.com/Nour833/StegoForge/stargazers)
  [![GitHub Downloads](https://img.shields.io/github/downloads/Nour833/StegoForge/total?style=for-the-badge&logo=github&color=brightgreen)](https://github.com/Nour833/StegoForge/releases)
  [![CTF](https://img.shields.io/badge/CTF-Ready-red?style=for-the-badge)](#-3-blind-forensics--ctf-mode-zero-knowledge)
</div>

---

## ⚡ Quick Launch (Standalone Binaries)

StegoForge is a complex Python framework, but you shouldn't have to deal with broken environments when doing active forensics. We have compiled **zero-dependency, native executables** that automatically resolve their own AI and Media requirements.

Head over to the **[Releases Page](https://github.com/Nour833/StegoForge/releases)** and download the binary for your OS.
* No `pip install` required.
* No `PATH` configurations.
* **Just execute it.**

---

## 🚀 Quick Start in 30 Seconds

```bash
# 1. Hide a file inside an image (AES-256-GCM encrypted, auto-method)
stegoforge encode -c photo.png -p secret.pdf -k "my-pass"

# 2. Retrieve the hidden file
stegoforge decode -f photo_stego.png -k "my-pass"

# 3. CTF one-click forensic dump on any suspicious file
stegoforge ctf -f suspicious.mp3

# 4. Compare original vs stego — pixel heatmap
stegoforge diff -c photo.png -s photo_stego.png

# 5. Batch embed a secret into every carrier in a folder
stegoforge batch -d ./carriers/ -p secret.txt -k "my-pass"

# 6. Check capacity and stealth score of a carrier
stegoforge capacity -c photo.png --depth 2

# 7. Simulate Twitter recompression and test payload survives
stegoforge encode -c photo.png -p secret.txt -k "my-pass" --target twitter --test-survival

# 8. Launch the local web UI (no data ever leaves your machine)
stegoforge web

# Install tab-completion (bash)
eval "$(stegoforge completion bash)"

# Use env var to avoid key in shell history
export STEGOFORGE_KEY="my-pass"
stegoforge decode -f stego.png   # key read from env
```

---

## 🧠 What is StegoForge?

> **The Concept in Plain English:** *Steganography is the art of hiding secrets in plain sight. StegoForge takes your secret message or file and mathematically weaves it into the pixels of a normal photo, the soundwaves of a song, or the frames of a video. To the rest of the world, it just looks like a regular meme or MP3 track. To you, it's an invisible vault.*

StegoForge is a **modular, enterprise-grade steganography toolkit** engineered for the full lifecycle of covert data: from embedding payloads into images, audio, video, and active network protocols, to deploying machine-learning steganalysis to forcibly extract anomalies from suspicious carrier files. 

Built for security researchers, CTF players, and digital forensics practitioners, it doesn't try to be one thing. It executes the entire forensic spectrum seamlessly.

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

## 💻 Developer Installation

If you wish to build StegoForge from source or utilize the Python APIs natively:

```bash
git clone https://github.com/Nour833/StegoForge.git
cd StegoForge
pip install -r requirements.txt
pip install -r requirements-web.txt
pip install -e .
```

Fire up the Glassmorphism Web App instantly:
```bash
stegoforge web  # Automatically deploys at http://localhost:5000
```

> **Note on ML Architecture**: StegoForge implements true Machine Learning steganalysis. The very first time you boot the engine, it will silently interface with HuggingFace to download the ONNX CNN weights directly into your `~/.stegoforge/models` cache.

---

## 🎨 Interactive Menu (Recommended for Beginners)

Don't want to memorize terminal commands? Just run the tool on its own to access the interactive CLI!

```bash
stegoforge
```

> The menu features a cinematic startup sequence, grouped method selection, and guided transitions between Encoding, Decoding, and Forensics.

**Pro-Tips for Automation:**
- `STEGOFORGE_FAST_UI=1 stegoforge` skips animations for rapid, zero-delay bootups.
- `STEGOFORGE_UI_STAGE_DELAY=0.45 stegoforge` fine-tunes the pacing of the visual display.

---

## 💻 Advanced Command Line Interface

If you prefer raw terminal throughput, the CLI supports hyper-specific routing for all modules.

### 🥷 1. Payload Encoding
```bash
# Basic LSB into PNG
stegoforge encode -c photo.png -p message.txt -k "passphrase"

# Stealth JPEG DCT with custom bit depth
stegoforge encode -c photo.jpg -p secret.bin -k "key" --method dct

# Spectrogram Art — Hide a visual image inside playable audio
stegoforge encode -c music.wav -p logo.png --method spectrogram

# Decoy mode — Generates two keys, hiding two payloads in one file for plausible deniability
stegoforge encode -c photo.png -p real_secret.txt -k "realkey" \
                  --decoy decoy_message.txt --decoy-key "duresskey"
```

### 🔓 2. Payload Decoding
```bash
stegoforge decode -f photo_stego.png -k "passphrase"
stegoforge decode -f music_stego.wav -k "key" --method phase
```

### 🕵️ 3. Blind Forensics & CTF Mode (Zero-Knowledge)
```bash
# Run the complete heuristic gauntlet natively (Highly Recommended)
stegoforge ctf -f suspicious.png

# Targeted ML / Statistical Detection
stegoforge detect --chi2 -f image.png
stegoforge detect --rs -f image.png
```

### 🛰️ 4. Covert Protocols (Dead Drops)
```bash
# Embed a payload and securely POST it as a disguised HTTP packet
stegoforge deadrop post -c cover.png -p msg.txt -k "shared_key"

# Monitor a remote image URL for an incoming payload change
stegoforge deadrop monitor --url "https://example.com/image.png" -k "shared_key" --interval 20
```

---

## 🔬 Detection Methods Overview

<details>
<summary><b>Click to expand full list of Forensic Capabilities</b></summary>

| Method | Target File | What It Automatically Detects |
|---|---|---|
| **Chi-square** | Images | LSB frequency distribution anomalies |
| **RS Analysis** | Images | Payload capacity estimation without a key |
| **ML Steganalysis** | Images | Learned stego likelihood from HuggingFace ONNX CNN models |
| **Fingerprint** | Images | PRNU inconsistency + in-browser tamper heatmaps |
| **Video anomaly** | MP4/WebM | Keyframe DCT-distribution anomalies |
| **Audio anomaly** | WAV/FLAC/MP3 | Sample bit-plane and statistical irregularities |
| **PDF anomaly** | PDF | Suspicious `/EmbeddedFile`, JS, or tail entropy |
| **Blind extractor** | Multimedia | Auto-tries common bit-patterns and AES-magic headers |

</details>

---

## 📂 System Architecture

<details>
<summary><b>Click to explore StegoForge's Module Tree</b></summary>

```text
stegoforge/
├── core/
│   ├── image/          # LSB, Adaptive WOW, DCT, PRNU Fingerprinting, Palette
│   ├── audio/          # PCM LSB, Phase-Coding, Spectrogram visual embedding
│   ├── video/          # Keyframe block-cost, motion temporal masks
│   ├── document/       # PDF Streams, Office XML, Unicode Zero-Width
│   ├── network/        # Timing channels, TCP field covert channels
│   ├── crypto/         # AES-256-GCM, Decoy Deniability, Argon2 KDF
│   └── binary/         # ELF / PE Slack space embedding
├── detect/             # Statistical analysis, HuggingFace ONNX CNNs, Brute-forcing
├── protocol/           # HTTP Dead Drops, X25519 Stego Key Exchange
└── web/                # High-performance Flask dashboard & Server-Sent Events
```
</details>

---

## 🚀 Supported Capabilities Matrix

| Carrier Format | Injection Method | Extraction Status | Forensic Blind Detection |
|:---:|:---:|:---:|:---:|
| **PNG** | ✅ LSB, Alpha, Palette | ✅ Supported | ✅ Supported |
| **JPEG** | ✅ DCT | ✅ Supported | ✅ Supported |
| **MP4** | ✅ Video DCT, Motion | ✅ Supported | ✅ Supported |
| **WAV / MP3** | ✅ Sample, Phase, Spectro | ✅ Supported | ✅ Supported |
| **PDF** | ✅ Object/Stream | ✅ Supported | ✅ Supported |
| **Office XML** | ✅ XML Streams | ✅ Supported | ✅ Supported |
| **ELF / PE** | ✅ Slack Space / Header | ✅ Supported | ✅ Supported |

Social survivability targets currently supported via Reed-Solomon wrapping: `twitter`, `instagram`, `telegram`, `discord`, `whatsapp`, `signal`.

---

## ⚖️ Legal Disclaimer & Contributing

> **Strictly Educational Disclaimer:**
> StegoForge was engineered strictly for digital forensics research, Capture The Flag (CTF) competitions, and lawful offensive security testing. 
> Concealing illegal content, orchestrating unauthorized data exfiltration, or attempting to evade lawful surveillance is universally illegal. The author accepts zero liability for any misuse of this technology.

**Contributing:**
Pull requests are heavily welcomed. Please ensure new encoding methods implement the `BaseEncoder` interface and contain robust PyTest coverage.

<div align="center">
  <b>Built by Nour833. Coded for the community.</b><br>
  <i>If you find StegoForge useful, educational, or just plain cool, consider leaving a ⭐!</i><br><br>
  <a href="../../issues">Report a Bug</a> • <a href="../../issues">Request a Feature</a>
</div>
