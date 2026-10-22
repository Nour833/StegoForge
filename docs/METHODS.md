# StegoForge Methods, Capacity, Stealth

| Carrier | Method | Capacity note | Reversible? | Survival |
|---|---|---|---|---|
| PNG/BMP/TIFF/WebP | `lsb` depth 1-4 | `(pixels*depth/8)-4`, floored 0 | yes | JPEG recompress destroys |
| PNG/JPG | `adaptive-lsb`, `dct` | DCT `(blocks/8)-4`; `jnd_safe_capacity` vectorized conservative | PNG yes; JPEG survives viewer round-trip, not recompression | wet-paper + `--target` helps |
| PNG | `fingerprint-lsb` | reduced effective | yes | fragile, camera-specific |
| PNG/WebP | `alpha` | opaque pixels only | yes | compositing destroys |
| GIF/indexed PNG | `palette` | ~`(pairs/8)-2` (tiny, ~6-14 B). The encrypted envelope is at least 50 B, so **palette cannot carry an encrypted payload**; encoding stops with a capacity error | yes | palette rewrite destroys |
| MP4/WebM → MP4 | `video-dct` (every 12th frame), `video-motion` (the other frames) | 1 bit per 8x8 luma block: `eligible_frames*blocks/8 - 8` | yes — written losslessly (libx264 `crf=0`) and self-verified | **none**: any lossy re-encode destroys it; the output is large, plays in ffmpeg-based players but not most browsers, audio tracks are kept |
| WAV/FLAC/MP3/OGG | `audio-lsb` depth 1-4 | `(samples*depth/8)-4` | WAV only (MP3/OGG transcode is lossy) | transcoding destroys |
| WAV | `phase` | segment-phase | yes | fragile |
| WAV | `spectrogram` | watermark-only `120` B; decode returns PNG visualization, not bytes | **no** | audible, artistic |
| TXT | `unicode` | insertion-point ranked ZWSP/ZWNJ/ZWJ | yes | stripped by platforms |
| TXT | `linguistic` | synonym channel; needs cover/topic/llm | yes | fragile |
| PDF | `pdf` | carrier-size floor 512KB; preserves metadata; `/StegoData` detectable | yes | survives viewer round-trip |
| DOCX/XLSX | `office` | carrier-size floor; adds `Content_Types` override + rel | yes | survives Office round-trip |
| ELF/PE | `elf`/`pe` | zero-filled padding first, then NOTE sections; clamped; invalidates Authenticode signatures; a filled `/usr/bin/true` still runs | yes | survives copy |
| Network | `tcp-covert`/`timing-covert` | artifact 2MB cap; live needs root + explicit IPs (this module was not reviewed in the 2026-10-22 pass) | artifact yes | N/A |

## Measured survival (`stegoforge survive`, 2026-10-22)

A generated 1200x780 natural-looking photo, a 50-byte payload, each profile's simulated recompression (`detect/survival.py`). The simulation is approximate; real platforms change their pipelines.

| Profile | Method chosen | Wet paper | Payload recovered |
|---|---|---|---|
| twitter (q85) | dct | yes | yes |
| instagram (q82) | dct | yes | yes |
| linkedin (q84) | dct | yes | yes |
| discord (q92), reddit (q90) | dct | no | yes |
| telegram, signal | lsb | no | yes (these do not recompress) |
| whatsapp (q78, 1600 px) | dct | yes | **no** |
| facebook (q80) | dct | yes | **no** |
| tiktok (q76) | dct | yes | **no** |

So `dct` plus wet paper holds down to about JPEG quality 82 here and fails at 80 and below, and a plain re-save of a `dct` file at q90 or lower also loses the payload. Treat qualities under about 82 as unsupported until the method is reworked.

Stealth scores (`STEALTH_SCORES`) are relative, not invisibility guarantees. Keyless LSB is forensically naked; always use a strong key (`kdf.py:password_strength`).

## What `--key` does to the embedding

The passphrase also selects the order in which carrier samples are visited. That is traversal obfuscation, not a second layer of encryption: confidentiality comes only from the AES-256-GCM envelope. For `adaptive-lsb` and the video methods the order is dominated by a content-derived ranking, so the key only breaks ties between equally active blocks.

## Decoy containers

A decoy container is embedded with an **unkeyed** traversal, so that either of its two keys can find it. Each key opens only its own slot; both slots are the same size and header-less.

## Wet paper

The wet-paper wrapper still begins with a fixed `WETP` header, so `--no-magic` does not hide it. Reed-Solomon redundancy corrects scattered bit errors; it does not make pixel-LSB payloads survive lossy re-compression.
