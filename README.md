
<div align="center">

```text
███████╗████████╗███████╗ ██████╗  ██████╗ ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔════╝╚══██╔══╝██╔════╝██╔════╝ ██╔═══██╗██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
███████╗   ██║   █████╗  ██║  ███╗██║   ██║█████╗  ██║   ██║██████╔╝██║  ███╗█████╗  
╚════██║   ██║   ██╔══╝  ██║   ██║██║   ██║██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝  
███████║   ██║   ███████╗╚██████╔╝╚██████╔╝██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚══════╝   ╚═╝   ╚══════╝ ╚═════╝  ╚═════╝ ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝

  ✨ Chi-Square  ·  RS Analysis  ·  EXIF Forensics  ·  Blind Extraction

  🚀 v1.0.0  ·  🛡️ 12 encoding methods  ·  🔍 4 detection engines  ·  🔐 AES-256-GCM

╭────────┬────────────────┬───────────────────────────────────────────────╮
│  1     │  Encode        │  Embed a secret payload in any carrier        │
│  2     │  Decode        │  Extract & decrypt a hidden payload           │
│  3     │  Detect        │  Analyze a file for hidden content            │
│  4     │  CTF Mode      │  Run all detectors, get full forensic report  │
│  5     │  Capacity      │  Check how much data a carrier can hold       │
│  6     │  Web UI        │  Launch the local web interface               │
│  q     │  Quit          │  Exit StegoForge                              │
╰────────┴────────────────┴───────────────────────────────────────────────╯
```

**The most complete open-source steganography toolkit.**  
Hide in images. Hide in audio. Hide in documents. Detect what others hide. Survive forensics.

---

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)
![CTF](https://img.shields.io/badge/CTF-Ready-red?style=flat-square)

</div>

---

## What is StegoForge?

StegoForge is a **modular, extensible steganography toolkit** that covers the full spectrum — from embedding payloads into pixels, audio samples, and Office documents, to detecting and extracting hidden data from suspicious files. Built for security researchers, CTF players, and digital forensics practitioners.

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
│   ├── LSB encoding        1–4 bit depth, any channel, any order
│   ├── DCT injection       JPEG frequency domain, F5-style
│   ├── Alpha channel       Transparency plane exploitation
│   └── Palette reorder     Indexed-color GIF/PNG covert channel
│
├── Audio Carriers          WAV · FLAC · MP3
│   ├── Sample LSB          PCM least-significant bits
│   ├── Phase coding        Segment-phase encoding, MP3-tolerant
│   └── Spectrogram art     Embed visible images/text into audio spectrum
│
├── Document Carriers       TXT · PDF · DOCX · XLSX
│   ├── Unicode whitespace  ZWSP/ZWNJ/ZWJ zero-width encoding
│   ├── PDF streams         Object/stream/metadata injection
│   └── Office XML          Custom XML parts, relationship streams
│
├── Crypto Layer            Always-on, transparent
│   ├── AES-256-GCM         Encrypt before embed, Argon2 key derivation
│   ├── Decoy mode          Two payloads, two keys, plausible deniability
│   └── Polymorphic embed   Key-seeded pattern variation, defeats signatures
│
├── Detection Engine        Find what others hide
│   ├── Chi-square attack   LSB frequency anomaly detection
│   ├── RS analysis         Capacity estimation without the key
│   ├── EXIF scanner        Metadata, thumbnail, and comment analysis
│   └── Blind extractor     Brute-force common patterns across Images & Audio file types
│
└── Interfaces
    ├── CLI                 Pipe-friendly, JSON output, scriptable
    ├── Web UI (Flask)      Local drag-and-drop, visual diff view, graceful interrupt
    └── CTF mode            One command, every detector, ranked report, smart skipping
```

---

## Installation

```bash
git clone https://github.com/youruser/stegoforge
cd stegoforge
pip install -r requirements.txt
pip install -e .
```

**Optional — web UI:**
```bash
pip install -r requirements-web.txt
stegoforge web  # opens at http://localhost:5000
```

**Requirements:** Python 3.10+, pip. No root needed.

---

## Interactive Menu (Recommended for Beginners!) 🎨

Don't want to memorize terminal commands? Just run the tool on its own to access the interactive CLI!

```bash
stegoforge
```

The menu will seamlessly guide you step-by-step through encoding, decrypting payloads, running CTF forensics, or spinning up the Drag-and-Drop Web UI. Nothing boring, incredibly intuitive.


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
stegoforge encode -c report.docx -p payload.txt -k "key" --method docx-xml

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
| Phase check | Audio | Phase discontinuities at segment boundaries |
| EXIF scanner | All | Metadata, hidden thumbnails, XMP, comments |
| Blind extractor | Images & Audio | Auto-tries all common encoding patterns & decodes AES encrypted magic |

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
│   │   ├── dct.py          DCT coefficient injection for JPEG
│   │   ├── alpha.py        Alpha channel covert channel
│   │   └── palette.py      Indexed-color palette reordering
│   ├── audio/
│   │   ├── lsb.py          PCM sample bit manipulation
│   │   ├── phase.py        Phase coding across audio segments
│   │   └── spectrogram.py  Spectrogram image embedding
│   ├── document/
│   │   ├── unicode.py      Zero-width character encoding
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
│   └── blind.py            Brute-force extractor
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
| WAV | ✅ LSB, Phase, Spectrogram | ✅ | ✅ |
| FLAC | ✅ LSB, Phase | ✅ | ✅ |
| MP3 | ✅ LSB, Phase, Spectrogram | ✅ | ✅ |
| OGG | ✅ LSB, Phase, Spectrogram | ✅ | ✅ |
| PDF | ✅ Stream injection | ✅ | ✅ |
| DOCX | ✅ XML streams | ✅ | ✅ |
| XLSX | ✅ XML streams | ✅ | ✅ |
| TXT | ✅ Unicode whitespace | ✅ | ✅ |

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

Made for the community. Use it responsibly.

**[Report a Bug](../../issues)** · **[Request a Feature](../../issues)** · **[CTF Writeups using StegoForge](../../discussions)**

</div>
