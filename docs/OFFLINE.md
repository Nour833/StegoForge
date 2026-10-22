# StegoForge Offline Guide

StegoForge never downloads an executable or a model, on first run or later.

- **`--offline` / `STEGOFORGE_OFFLINE=1`** switches network access off: dead drops, the update check and the HTTP client refuse to run. Everything else works the same.
- **ML model:** shipped inside the package (`models/model_quantized.onnx`, with a `.sha256` sidecar). `stegoforge init` copies it to `~/.stegoforge/models`; `STEGOFORGE_MODEL_SHA256` pins its hash.
- **FFmpeg** is needed only to convert MP3, FLAC and OGG audio. Install it with your package manager (`sudo apt install ffmpeg`), set `STEGOFORGE_FFMPEG=/path/to/ffmpeg`, or rely on the `imageio-ffmpeg` dependency. Video methods use PyAV's own libraries and need no ffmpeg binary.
- **Web UI:** fully self-contained. Fonts are served from the package (`web/static/fonts`, SIL OFL) and the page makes no request to any third party.
- **`stegoforge doctor`** reports what this installation can and cannot do, without touching the network.
