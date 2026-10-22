"""
core/video/_luma.py — shared engine for the video embedding methods.

Why this exists
===============
Both video methods used to flip the LSB of an *RGB* sample and then hand the
frames to a lossy libx264 encode. Lossy compression rewrites exactly those
low-order bits, and the encoder also decides for itself which frames become
keyframes, so the decoder could neither find the frames nor the bits again:
every round trip failed.

The embedding now works the way a video actually stores pixels:

* frames are decoded to ``yuv420p`` and the bit is written into the **luma
  (Y) plane**, the plane the codec stores;
* the result is re-encoded **losslessly** (libx264 ``crf=0``), so the decoder
  reads back exactly the bytes the encoder wrote;
* frames are selected by *index* (every ``ANCHOR_STRIDE``-th frame is an
  "anchor"), never by the encoder-assigned keyframe flag;
* the embedding order is computed from the luma with its LSBs masked off,
  using integer arithmetic and NumPy's frozen ``RandomState`` stream, so the
  decoder derives the identical order on any machine or NumPy release;
* after encoding, the stego video is decoded again and compared with the
  payload. A carrier that cannot hold the payload bit-exactly is an error, not
  a silently corrupted file.

The key (``--key``) only breaks ties between equally active blocks, so it is
traversal obfuscation and not a confidentiality control; payload secrecy comes
from the AES envelope the CLI applies before embedding.

Limits (inherent to LSB embedding, documented in docs/METHODS.md)
=================================================================
* The output is lossless H.264 and therefore **much larger** than the input.
* Re-encoding the stego video with *any* lossy codec (YouTube, chat apps,
  ``ffmpeg -crf 23``) destroys the payload.
* Lossless H.264 uses the High 4:4:4 Predictive profile: ffmpeg-based players
  (VLC, mpv, ffplay) play it, most hardware decoders and browsers do not.
* Input that is not ``yuv420p`` (10-bit, 4:4:4, full-range) is converted to it.
* Audio streams are copied unchanged; subtitle and data streams are dropped.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import struct
import tempfile
from pathlib import Path
from collections.abc import Callable, Iterator

import numpy as np

from core.base import BaseEncoder
from core.bits import bits_to_bytes_np, bytes_to_bits_np, validate_payload_not_empty
from core.crypto.polymorphic import keyed_permutation
from core.errors import CorruptedCarrierError

BLOCK = 8
ANCHOR_STRIDE = 12
HEADER_FMT = ">4sI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MOTION_WEIGHT_NUM = 6  # texture weight 5, motion weight 6 -> motion counts 1.2x


def require_av():
    try:
        import av  # type: ignore
    except Exception as exc:  # noqa: BLE001 - any import failure means "unusable"
        raise ValueError("video methods require PyAV. Install with: pip install av") from exc
    return av


def require_x264(av) -> None:
    if "libx264" not in av.codecs_available:
        raise ValueError(
            "this PyAV build has no libx264 encoder; install a PyAV wheel that bundles it (pip install av)"
        )


@contextlib.contextmanager
def temp_file(data: bytes, suffix: str = ".mp4") -> Iterator[Path]:
    fd, name = tempfile.mkstemp(suffix=suffix, prefix="sf_video_")
    path = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        yield path
    finally:
        path.unlink(missing_ok=True)


def _first_video_stream(container):
    streams = container.streams.video
    if not streams:
        raise ValueError("No video stream found in this file")
    return streams[0]


def _check_even(width: int, height: int) -> None:
    if width % 2 or height % 2:
        raise ValueError(f"video dimensions must be even for yuv420p ({width}x{height})")


def iter_luma(data: bytes) -> Iterator[tuple[int, np.ndarray]]:
    """Yield ``(frame_index, luma)`` for every decoded frame (luma is a writable copy)."""
    av = require_av()
    with temp_file(data) as path:
        container = av.open(str(path))
        try:
            stream = _first_video_stream(container)
            for idx, frame in enumerate(container.decode(stream)):
                frame = frame.reformat(format="yuv420p")
                plane = frame.planes[0]
                view = np.frombuffer(plane, dtype=np.uint8).reshape(plane.height, plane.line_size)
                yield idx, view[:, :plane.width].copy()
        finally:
            container.close()


def transcode_lossless(data: bytes, edit: Callable[[int, np.ndarray], None]) -> bytes:
    """Decode ``data`` to yuv420p, let ``edit(index, luma)`` mutate each luma plane, re-encode losslessly.

    Audio streams are passed through untouched. Frame timestamps are preserved.
    """
    av = require_av()
    require_x264(av)
    out_fd, out_name = tempfile.mkstemp(suffix=".mp4", prefix="sf_video_out_")
    os.close(out_fd)
    out_path = Path(out_name)
    try:
        with temp_file(data) as src:
            source = av.open(str(src))
            try:
                vin = _first_video_stream(source)
                _check_even(vin.width, vin.height)
                audio_in = list(source.streams.audio)
                sink = av.open(out_name, mode="w", format="mp4")
                try:
                    vout = sink.add_stream("libx264", rate=vin.average_rate or 24)
                    vout.width, vout.height = vin.width, vin.height
                    vout.pix_fmt = "yuv420p"
                    vout.options = {"crf": "0", "preset": "veryfast"}
                    audio_out = {s.index: sink.add_stream_from_template(s) for s in audio_in}

                    idx = 0
                    for packet in source.demux(vin, *audio_in):
                        if packet.stream.type == "video":
                            for frame in packet.decode():
                                planes = frame.reformat(format="yuv420p").to_ndarray()
                                edit(idx, planes[:frame.height])
                                fresh = av.VideoFrame.from_ndarray(planes, format="yuv420p")
                                fresh.pts, fresh.time_base = frame.pts, frame.time_base
                                for out_packet in vout.encode(fresh):
                                    sink.mux(out_packet)
                                idx += 1
                        elif packet.dts is not None:
                            packet.stream = audio_out[packet.stream.index]
                            sink.mux(packet)
                    for out_packet in vout.encode(None):
                        sink.mux(out_packet)
                finally:
                    sink.close()
            finally:
                source.close()
        return out_path.read_bytes()
    finally:
        out_path.unlink(missing_ok=True)


# ── embedding order ───────────────────────────────────────────────────────────

def _block_scores(base: np.ndarray, prev_base: np.ndarray | None) -> np.ndarray:
    """Integer per-block activity (texture, plus temporal change for motion frames)."""
    h, w = base.shape
    bh, bw = h // BLOCK, w // BLOCK
    gx = np.abs(np.diff(base, axis=1, prepend=base[:, :1]))
    gy = np.abs(np.diff(base, axis=0, prepend=base[:1, :]))
    score = (gx + gy).astype(np.int64)
    if prev_base is not None and prev_base.shape == base.shape:
        score = score * 5 + MOTION_WEIGHT_NUM * np.abs(base - prev_base)
    cropped = score[:bh * BLOCK, :bw * BLOCK]
    return cropped.reshape(bh, BLOCK, bw, BLOCK).sum(axis=(1, 3)).reshape(-1)


def rank_blocks(base: np.ndarray, key: str | None, frame_idx: int, salt: str,
                prev_base: np.ndarray | None = None) -> np.ndarray:
    """Block ids (row-major) ordered busiest-first, ties broken by a keyed permutation.

    ``base`` must be the luma with its LSB cleared (``luma >> 1``), so the order
    is identical before and after embedding.
    """
    scores = _block_scores(base, prev_base)
    if scores.size == 0:
        return np.empty(0, dtype=np.int64)
    if key:
        digest = hashlib.sha256(f"{salt}:{frame_idx}:{key}".encode()).digest()
        seed = int.from_bytes(digest[:8], "big")
    else:
        seed = frame_idx
    return np.lexsort((keyed_permutation(scores.size, seed), -scores))


def _sites(shape: tuple[int, int], ids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    bw = shape[1] // BLOCK
    return (ids // bw) * BLOCK + BLOCK // 2, (ids % bw) * BLOCK + BLOCK // 2


def write_bits(luma: np.ndarray, ids: np.ndarray, bits: np.ndarray) -> None:
    rows, cols = _sites(luma.shape, ids)
    luma[rows, cols] = (luma[rows, cols] & 0xFE) | bits


def read_bits(luma: np.ndarray, ids: np.ndarray) -> np.ndarray:
    rows, cols = _sites(luma.shape, ids)
    return luma[rows, cols] & 1


# ── encoder ───────────────────────────────────────────────────────────────────

class LumaVideoEncoder(BaseEncoder):
    """One bit per 8x8 luma block on the selected frames. Subclasses pick the frames."""

    magic: bytes = b"SFVD"
    salt: str = "video-dct"
    uses_motion = False
    supported_extensions = [".mp4", ".webm"]

    def eligible(self, frame_idx: int) -> bool:
        raise NotImplementedError

    def eligible_frames(self, frames: int) -> int:
        raise NotImplementedError

    def output_suffix(self, carrier_suffix: str) -> str:
        return ".mp4"  # the lossless re-encode is always written as MP4

    def capacity(self, carrier_bytes: bytes, **kwargs) -> int:
        from core.video.scan import scan_video

        scan = scan_video(carrier_bytes)
        blocks = (scan.width // BLOCK) * (scan.height // BLOCK)
        bits = self.eligible_frames(scan.frames) * blocks
        return max(0, bits // 8 - HEADER_SIZE)

    def encode(self, carrier_bytes: bytes, payload_bytes: bytes, key: str | None = None, **kwargs) -> bytes:
        validate_payload_not_empty(payload_bytes)
        cap = self.capacity(carrier_bytes)
        if len(payload_bytes) > cap:
            raise ValueError(f"Payload too large: {len(payload_bytes)} bytes, {self.name} capacity: {cap} bytes")

        bits = bytes_to_bits_np(struct.pack(HEADER_FMT, self.magic, len(payload_bytes)) + bytes(payload_bytes))
        state: dict = {"pos": 0, "prev": None}

        def edit(idx: int, luma: np.ndarray) -> None:
            base = (luma >> 1).astype(np.int32)
            prev, state["prev"] = state["prev"], base
            if state["pos"] >= len(bits) or not self.eligible(idx):
                return
            ids = rank_blocks(base, key, idx, self.salt, prev if self.uses_motion else None)
            chunk = bits[state["pos"]:state["pos"] + len(ids)]
            write_bits(luma, ids[:len(chunk)], chunk)
            state["pos"] += len(chunk)

        stego = transcode_lossless(carrier_bytes, edit)
        if state["pos"] < len(bits):
            raise ValueError(f"{self.name}: the video has too few usable frames for this payload")
        try:
            recovered = self.decode(stego, key=key)
        except ValueError as exc:
            raise CorruptedCarrierError(f"{self.name}: self-check failed, embedding did not survive re-encode ({exc})") from None
        if recovered != bytes(payload_bytes):
            raise CorruptedCarrierError(f"{self.name}: self-check failed, recovered payload differs from input")
        return stego

    def decode(self, stego_bytes: bytes, key: str | None = None, **kwargs) -> bytes:
        header_bits = HEADER_SIZE * 8
        chunks: list[np.ndarray] = []
        have = 0
        need = header_bits
        length: int | None = None
        prev = None
        for idx, luma in iter_luma(stego_bytes):
            base = (luma >> 1).astype(np.int32)
            prev_base, prev = prev, base
            if not self.eligible(idx):
                continue
            ids = rank_blocks(base, key, idx, self.salt, prev_base if self.uses_motion else None)
            chunks.append(read_bits(luma, ids))
            have += len(ids)
            if length is None and have >= header_bits:
                magic, length = struct.unpack(HEADER_FMT, bits_to_bytes_np(np.concatenate(chunks)[:header_bits]))
                if magic != self.magic or length <= 0 or length > self.capacity(stego_bytes):
                    raise ValueError(f"No StegoForge {self.name} payload found")
                need = (HEADER_SIZE + length) * 8
            if have >= need:
                break
        if length is None:
            raise ValueError(f"No {self.name} payload header found")
        if have < need:
            raise ValueError(f"Incomplete {self.name} payload")
        return bits_to_bytes_np(np.concatenate(chunks)[header_bits:need])
