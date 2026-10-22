"""tests/test_video_methods.py — video embedding: exact round trips, honest failures.

The embeds are written losslessly, so a decode must return the payload
bit-for-bit; the encoder verifies this itself and refuses to return a stego
video it cannot read back.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

av = pytest.importorskip("av")
np = pytest.importorskip("numpy")

from core.errors import CorruptedCarrierError  # noqa: E402
from core.video.dct import VideoDCTEncoder  # noqa: E402
from core.video.motion import VideoMotionEncoder  # noqa: E402
from core.video.scan import scan_video  # noqa: E402


def _make_mp4(path: Path, frames: int = 48, w: int = 128, h: int = 96, audio: bool = False) -> bytes:
    container = av.open(str(path), mode="w")
    video = container.add_stream("libx264", rate=24)
    video.width, video.height, video.pix_fmt = w, h, "yuv420p"
    video.options = {"g": "12", "crf": "18"}
    sound = None
    if audio:
        sound = container.add_stream("aac", rate=44100)
        sound.layout = "mono"
    base = np.random.default_rng(3).integers(0, 255, (h, w, 3), dtype=np.uint8)
    for i in range(frames):
        frame = av.VideoFrame.from_ndarray(np.roll(base, i * 2, axis=1), format="rgb24")
        for packet in video.encode(frame):
            container.mux(packet)
    if sound is not None:
        pcm = (np.sin(np.arange(44100 * 2) * 0.05) * 8000).astype(np.int16)[None, :]
        samples = av.AudioFrame.from_ndarray(pcm, format="s16", layout="mono")
        samples.sample_rate = 44100
        for packet in sound.encode(samples):
            container.mux(packet)
        for packet in sound.encode(None):
            container.mux(packet)
    for packet in video.encode(None):
        container.mux(packet)
    container.close()
    return path.read_bytes()


@pytest.fixture(scope="module")
def clip(tmp_path_factory) -> bytes:
    return _make_mp4(tmp_path_factory.mktemp("vid") / "clip.mp4", audio=True)


def test_video_encoders_instantiation():
    assert VideoDCTEncoder().name == "video-dct"
    assert VideoMotionEncoder().name == "video-motion"


@pytest.mark.parametrize("cls", [VideoDCTEncoder, VideoMotionEncoder])
@pytest.mark.parametrize("key", [None, "k3y"])
def test_roundtrip_is_bit_exact(clip, cls, key):
    enc = cls()
    payload = bytes(range(40))
    stego = enc.encode(clip, payload, key=key)
    assert enc.decode(stego, key=key) == payload


@pytest.mark.parametrize("cls", [VideoDCTEncoder, VideoMotionEncoder])
def test_payload_may_fill_the_capacity_exactly(clip, cls):
    enc = cls()
    payload = bytes(i % 251 for i in range(enc.capacity(clip)))
    assert enc.decode(enc.encode(clip, payload)) == payload


@pytest.mark.parametrize("cls", [VideoDCTEncoder, VideoMotionEncoder])
def test_oversize_and_empty_payloads_are_refused(clip, cls):
    enc = cls()
    with pytest.raises(ValueError, match="too large"):
        enc.encode(clip, bytes(enc.capacity(clip) + 1))
    with pytest.raises(ValueError):
        enc.encode(clip, b"")


def test_methods_use_disjoint_frames(clip):
    """A dct payload is invisible to the motion decoder and vice versa."""
    stego = VideoDCTEncoder().encode(clip, b"anchor-only")
    with pytest.raises(ValueError):
        VideoMotionEncoder().decode(stego)


def test_stego_keeps_frame_count_duration_and_audio(clip):
    stego = VideoDCTEncoder().encode(clip, b"keep-av")
    before, after = scan_video(clip), scan_video(stego)
    assert after.frames == before.frames
    assert (after.width, after.height) == (before.width, before.height)
    assert abs(after.duration_sec - before.duration_sec) < 0.05
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        tmp.write(stego)
        tmp.flush()
        container = av.open(tmp.name)
        try:
            assert len(container.streams.audio) == 1
        finally:
            container.close()


def test_clean_video_has_no_payload(clip):
    for cls in (VideoDCTEncoder, VideoMotionEncoder):
        with pytest.raises(ValueError):
            cls().decode(clip)


def test_output_suffix_is_always_mp4():
    assert VideoDCTEncoder().output_suffix(".webm") == ".mp4"


def test_garbage_input_is_a_clean_value_error_without_path_leak():
    for call in (VideoDCTEncoder().capacity, VideoDCTEncoder().decode, scan_video):
        with pytest.raises(ValueError) as info:
            call(b"definitely not a video")
        assert "/tmp" not in str(info.value) and "sf_video" not in str(info.value)


def test_odd_dimensions_are_refused_clearly():
    # libx264/yuv420p cannot produce an odd-sized file to feed through, so the guard is called directly
    from core.video._luma import _check_even

    with pytest.raises(ValueError, match="even"):
        _check_even(127, 95)
    _check_even(126, 94)


def test_scan_cache_key_covers_the_whole_file(clip):
    """Two files with identical head and tail but different middles must not share a scan."""
    from core.video.scan import _cache_key

    padded = clip + b"\x00" * 200_000
    flipped = bytearray(padded)
    flipped[len(clip) + 100_000] ^= 0xFF
    assert _cache_key(padded) != _cache_key(bytes(flipped))
    assert scan_video(clip) is scan_video(clip)


def test_anomaly_detector_extracts_and_does_not_cry_wolf(clip):
    from detect.video_anomaly import VideoAnomalyDetector

    clean = VideoAnomalyDetector().analyze(clip, "clean.mp4")
    assert not clean.detected and clean.confidence == 0.0

    stego = VideoMotionEncoder().encode(clip, b"found-me")
    hit = VideoAnomalyDetector().analyze(stego, "stego.mp4")
    assert hit.detected and hit.confidence == 1.0 and hit.extracted_payload == b"found-me"
    assert hit.details["extracted_by"] == "video-motion"


def test_anomaly_detector_garbage_is_skipped_gracefully():
    from detect.video_anomaly import VideoAnomalyDetector

    r = VideoAnomalyDetector().analyze(b"not-a-video", "bad.mp4")
    assert r.method == "video-anomaly" and not r.detected and 0.0 <= r.confidence <= 1.0


def test_self_check_rejects_a_reencode_that_loses_bits(clip, monkeypatch):
    """If the codec path ever stops being lossless the encoder must fail, not return a dud."""
    import core.video._luma as luma

    real = luma.transcode_lossless

    def lossy(data, edit):
        def damaging(idx, plane):
            edit(idx, plane)
            plane[::2, ::2] ^= 1  # flip LSBs after the edit, as a lossy codec would

        return real(data, damaging)

    monkeypatch.setattr(luma, "transcode_lossless", lossy)
    with pytest.raises(CorruptedCarrierError, match="self-check"):
        VideoDCTEncoder().encode(clip, bytes(range(60)))
