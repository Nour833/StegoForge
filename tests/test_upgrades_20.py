"""tests/test_upgrades_20.py — v2.0 track coverage: video, network guards, fuzz, perf."""
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def _make_mp4(path: Path, size: int = 128, frames: int = 48) -> bytes:
    import numpy as np

    av = pytest.importorskip("av")
    c = av.open(str(path), mode="w")
    s = c.add_stream("libx264", rate=24)
    s.width, s.height, s.pix_fmt = size, size, "yuv420p"
    rng = np.random.default_rng(7)
    for _ in range(frames):
        arr = rng.integers(0, 255, (size, size, 3), dtype=np.uint8)
        f = av.VideoFrame.from_ndarray(arr, format="rgb24")
        for pkt in s.encode(f):
            c.mux(pkt)
    for pkt in s.encode(None):
        c.mux(pkt)
    c.close()
    return path.read_bytes()


def test_video_dct_roundtrip_is_exact(tmp_path):
    data = _make_mp4(tmp_path / "t.mp4")
    from core.video.dct import VideoDCTEncoder

    assert VideoDCTEncoder().capacity(data) > 0
    stego = VideoDCTEncoder().encode(data, b"vid!")
    assert VideoDCTEncoder().decode(stego) == b"vid!"
    from core.video.scan import scan_video

    assert scan_video(stego).frames == scan_video(data).frames


def test_video_scan_cache_shared(tmp_path):
    data = _make_mp4(tmp_path / "t.mp4")
    from core.video.scan import scan_video

    a = scan_video(data)
    b = scan_video(data)
    assert a is b  # single-scan cache
    assert a.frames >= 1 and a.keyframes >= 1


def test_network_privilege_gate():
    from core.network.tcp import TCPCovertEncoder
    from core.network.timing import TimingCovertEncoder
    import os

    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("running as root — privilege gate does not trigger")
    with pytest.raises(ValueError):
        TCPCovertEncoder().encode(b"", b"hi")
    with pytest.raises(ValueError):
        TimingCovertEncoder().encode(b"", b"hi")


def test_network_guard_validation():
    from core.network.guard import bpf_filter, validate_listen_target

    with pytest.raises(ValueError):
        validate_listen_target("not-an-ip", 8080)
    with pytest.raises(ValueError):
        validate_listen_target("127.0.0.1", 99999)
    with pytest.raises(ValueError):
        validate_listen_target(None, None)
    ip, port = validate_listen_target("127.0.0.1", 8080)
    assert bpf_filter(ip, port) == "tcp and dst host 127.0.0.1 and dst port 8080"


def test_fuzz_decoders_no_traceback():
    """Mutated carriers must raise ValueError/IOError only — never raw errors."""
    import random

    from core.binary.elf import ELFEncoder
    from core.document.pdf import PDFEncoder
    from core.image.lsb import LSBEncoder

    rng = random.Random(1234)
    carriers = [
        ("lsb", LSBEncoder(), (FIXTURES / "sample.png").read_bytes()),
        ("pdf", PDFEncoder(), (FIXTURES / "sample.pdf").read_bytes()),
    ]
    elf = FIXTURES / "sample.elf"
    if elf.exists():
        carriers.append(("elf", ELFEncoder(), elf.read_bytes()))
    for name, enc, base in carriers:
        for _ in range(15):
            blob = bytearray(base)
            for _ in range(rng.randint(1, 8)):
                blob[rng.randrange(len(blob))] = rng.randrange(256)
            try:
                enc.decode(bytes(blob), depth=1)
            except (OSError, ValueError):
                pass


def test_perf_dct_vectorized():
    from PIL import Image

    from core.image.dct import DCTEncoder

    img = Image.new("RGB", (256, 256), (128, 130, 140))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    start = time.time()
    stego = DCTEncoder().encode(buf.getvalue(), b"perf-probe-payload")
    elapsed = time.time() - start
    assert DCTEncoder().decode(stego) == b"perf-probe-payload"
    assert elapsed < 5.0, f"DCT encode too slow: {elapsed:.2f}s"


def test_report_canonical_chain():
    from stegoforge_ops.report import canonical_json, chain_hash, report_hash, GENESIS_HASH

    r = {"b": 1, "a": [3, 2]}
    assert canonical_json(r) == '{"a":[3,2],"b":1}'
    h = report_hash(r)
    c1 = chain_hash(GENESIS_HASH, r)
    assert chain_hash(GENESIS_HASH, r) == c1 and h != c1
