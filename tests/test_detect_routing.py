"""tests/test_detect_routing.py - Detection routing coverage for non-image formats."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cli import op_detect

FIXTURES = Path(__file__).parent / "fixtures"


def test_audio_detect_includes_audio_specific_detector_by_default():
    wav = FIXTURES / "sample.wav"
    r = op_detect(str(wav), False, False, False, False, False, False, False, False, False)
    methods = [x["method"] for x in r["results"]]
    assert "exif" in methods
    assert "blind" in methods
    assert "audio-anomaly" in methods
    assert r["detectors_run"] >= 3


def test_pdf_detect_includes_pdf_specific_detector_by_default():
    pdf = FIXTURES / "sample.pdf"
    r = op_detect(str(pdf), False, False, False, False, False, False, False, False, False)
    methods = [x["method"] for x in r["results"]]
    assert "exif" in methods
    assert "blind" in methods
    assert "pdf-anomaly" in methods
    assert r["detectors_run"] >= 3


def test_docx_detect_includes_document_specific_detector_by_default():
    docx = FIXTURES / "sample.docx"
    r = op_detect(str(docx), False, False, False, False, False, False, False, False, False)
    methods = [x["method"] for x in r["results"]]
    assert "exif" in methods
    assert "blind" in methods
    assert "document-anomaly" in methods
    assert r["detectors_run"] >= 3


def test_txt_detect_includes_document_specific_detector_by_default():
    txt = FIXTURES / "sample.txt"
    r = op_detect(str(txt), False, False, False, False, False, False, False, False, False)
    methods = [x["method"] for x in r["results"]]
    assert "exif" in methods
    assert "blind" in methods
    assert "document-anomaly" in methods
    assert r["detectors_run"] >= 3


def test_video_detect_includes_video_specific_detector(tmp_path):
    fake_video = tmp_path / "sample.mp4"
    fake_video.write_bytes(b"not-a-real-video")

    r = op_detect(str(fake_video), False, False, True, True, False, False, False, False, False)
    methods = [x["method"] for x in r["results"]]
    assert "exif" in methods
    assert "blind-audio" in methods
    assert "video-anomaly" in methods
    assert r["detectors_run"] >= 3
