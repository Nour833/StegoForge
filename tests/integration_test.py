"""
tests/integration_test.py — End-to-end integration tests.

Encodes with every method → decodes → asserts identical bytes.
Also runs all detection engines on stego files.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"


def separator(title):
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print('═' * 60)


def check(label: str, success: bool, msg: str = ""):
    icon = "✓" if success else "✗"
    status = "PASS" if success else "FAIL"
    line = f"  [{status}] {icon} {label}"
    if msg:
        line += f"  — {msg}"
    print(line)
    return success


def run_all():
    results = []

    # ── Generate fixtures ─────────────────────────────────────────────────────
    separator("Generating test fixtures")
    from tests.generate_fixtures import (
        ensure_dir, gen_png, gen_jpg, gen_rgba_png, gen_gif,
        gen_wav, gen_pdf, gen_docx, gen_xlsx, gen_txt
    )
    ensure_dir()
    gen_png(); gen_jpg(); gen_rgba_png(); gen_gif()
    gen_wav(); gen_pdf(); gen_docx(); gen_xlsx(); gen_txt()
    results.append(check("Fixtures generated", True))

    # ── Crypto ────────────────────────────────────────────────────────────────
    separator("Crypto Layer")
    from core.crypto.aes import encrypt, decrypt
    from core.crypto.decoy import encode_dual, decode_dual

    plaintext = b"StegoForge AES-256-GCM test payload!"
    enc = encrypt(plaintext, "integration_key")
    dec = decrypt(enc, "integration_key")
    results.append(check("AES-256-GCM round-trip", dec == plaintext))

    try:
        decrypt(enc, "wrongkey")
        results.append(check("Wrong-key raises ValueError", False, "Should have raised"))
    except ValueError:
        results.append(check("Wrong-key raises ValueError", True))

    decoy_combined = encode_dual(b"decoy content", "decoykey", b"real secret", "realkey")
    r1 = decode_dual(decoy_combined, "realkey")
    r2 = decode_dual(decoy_combined, "decoykey")
    results.append(check("Decoy dual-payload real key", r1 == b"real secret"))
    results.append(check("Decoy dual-payload decoy key", r2 == b"decoy content"))

    # ── Image LSB ─────────────────────────────────────────────────────────────
    separator("Image: LSB")
    from core.image.lsb import LSBEncoder
    _enc = LSBEncoder()
    carrier = (FIXTURES / "sample.png").read_bytes()
    payload = b"LSB integration test payload 1234567890"
    enc_payload = encrypt(payload, "integrationkey")
    stego = _enc.encode(carrier, enc_payload)
    raw = _enc.decode(stego)
    dec_payload = decrypt(raw, "integrationkey")
    results.append(check("Image LSB round-trip", dec_payload == payload))
    cap = _enc.capacity(carrier)
    results.append(check("Image LSB capacity > 0", cap > 0, f"{cap:,} bytes"))

    # ── Image DCT ─────────────────────────────────────────────────────────────
    separator("Image: DCT")
    from core.image.dct import DCTEncoder
    enc_dct = DCTEncoder()
    carrier_jpg = (FIXTURES / "sample.jpg").read_bytes()
    payload_dct = b"DCT integration test"
    enc_payload_dct = encrypt(payload_dct, "dctkey")
    stego_dct = enc_dct.encode(carrier_jpg, enc_payload_dct)
    raw_dct = enc_dct.decode(stego_dct)
    dec_dct = decrypt(raw_dct, "dctkey")
    results.append(check("Image DCT round-trip", dec_dct == payload_dct))

    # ── Image Alpha ───────────────────────────────────────────────────────────
    separator("Image: Alpha Channel")
    from core.image.alpha import AlphaEncoder
    enc_alpha = AlphaEncoder()
    carrier_rgba = (FIXTURES / "sample_rgba.png").read_bytes()
    payload_alpha = b"Alpha channel integration"
    enc_payload_alpha = encrypt(payload_alpha, "alphakey")
    stego_alpha = enc_alpha.encode(carrier_rgba, enc_payload_alpha)
    raw_alpha = enc_alpha.decode(stego_alpha)
    dec_alpha = decrypt(raw_alpha, "alphakey")
    results.append(check("Image Alpha round-trip", dec_alpha == payload_alpha))

    # ── Image Palette ─────────────────────────────────────────────────────────
    separator("Image: Palette Reorder")
    from core.image.palette import PaletteEncoder
    enc_palette = PaletteEncoder()
    carrier_gif = (FIXTURES / "sample_indexed.gif").read_bytes()
    cap_palette = enc_palette.capacity(carrier_gif)
    if cap_palette >= 2:
        payload_palette = b"HI"  # tiny payload for palette
        stego_palette = enc_palette.encode(carrier_gif, payload_palette)
        dec_palette = enc_palette.decode(stego_palette)
        results.append(check("Image Palette round-trip", dec_palette == payload_palette))
    else:
        results.append(check("Image Palette (capacity too small, skip)", True, f"cap={cap_palette}"))

    # ── Audio LSB ─────────────────────────────────────────────────────────────
    separator("Audio: LSB")
    from core.audio.lsb import AudioLSBEncoder
    enc_alb = AudioLSBEncoder()
    carrier_wav = (FIXTURES / "sample.wav").read_bytes()
    payload_wav = b"Audio LSB integration test payload"
    enc_wav = encrypt(payload_wav, "wavkey")
    stego_wav = enc_alb.encode(carrier_wav, enc_wav, ext=".wav")
    raw_wav = enc_alb.decode(stego_wav, ext=".wav")
    dec_wav = decrypt(raw_wav, "wavkey")
    results.append(check("Audio LSB round-trip", dec_wav == payload_wav))

    # ── Audio Phase ───────────────────────────────────────────────────────────
    separator("Audio: Phase Coding")
    from core.audio.phase import PhaseEncoder
    enc_phase = PhaseEncoder()
    cap_phase = enc_phase.capacity(carrier_wav, ext=".wav")
    # Use short payload that fits within phase capacity
    payload_phase_raw = b"Phase!"[:max(1, cap_phase - 1)]
    stego_phase = enc_phase.encode(carrier_wav, payload_phase_raw, ext=".wav")
    raw_phase = enc_phase.decode(stego_phase, ext=".wav")
    results.append(check("Audio Phase round-trip", raw_phase == payload_phase_raw,
                         f"capacity={cap_phase}, payload={len(payload_phase_raw)}"))

    # ── Audio Spectrogram ─────────────────────────────────────────────────────
    separator("Audio: Spectrogram")
    from core.audio.spectrogram import SpectrogramEncoder
    enc_spec = SpectrogramEncoder()
    stego_spec = enc_spec.encode(carrier_wav, b"STEGOFORGE", ext=".wav")
    spec_img = enc_spec.decode(stego_spec, ext=".wav")
    results.append(check("Audio Spectrogram encode", len(stego_spec) > 0))
    results.append(check("Audio Spectrogram decode (PNG)", spec_img[:4] == b"\x89PNG"))

    # ── Document Unicode ──────────────────────────────────────────────────────
    separator("Document: Unicode Zero-Width")
    from core.document.unicode_ws import UnicodeWSEncoder
    enc_uni = UnicodeWSEncoder()
    carrier_txt = (FIXTURES / "sample.txt").read_bytes()
    payload_txt = b"Unicode steganography!"
    stego_txt = enc_uni.encode(carrier_txt, payload_txt)
    dec_txt = enc_uni.decode(stego_txt)
    results.append(check("Document Unicode round-trip", dec_txt == payload_txt))

    # ── Document PDF ──────────────────────────────────────────────────────────
    separator("Document: PDF Injection")
    from core.document.pdf import PDFEncoder
    enc_pdf = PDFEncoder()
    carrier_pdf = (FIXTURES / "sample.pdf").read_bytes()
    payload_pdf = b"PDF injection integration test"
    stego_pdf = enc_pdf.encode(carrier_pdf, payload_pdf)
    dec_pdf = enc_pdf.decode(stego_pdf)
    results.append(check("Document PDF round-trip", dec_pdf == payload_pdf))

    # ── Document DOCX ─────────────────────────────────────────────────────────
    separator("Document: DOCX XML Stream")
    from core.document.office import OfficeEncoder
    enc_office = OfficeEncoder()
    carrier_docx = (FIXTURES / "sample.docx").read_bytes()
    payload_docx = b"DOCX XML integration test"
    stego_docx = enc_office.encode(carrier_docx, payload_docx, filename="sample.docx")
    dec_docx = enc_office.decode(stego_docx, filename="sample.docx")
    results.append(check("Document DOCX round-trip", dec_docx == payload_docx))

    # ── Document XLSX ─────────────────────────────────────────────────────────
    separator("Document: XLSX XML Stream")
    carrier_xlsx = (FIXTURES / "sample.xlsx").read_bytes()
    payload_xlsx = b"XLSX XML integration test"
    stego_xlsx = enc_office.encode(carrier_xlsx, payload_xlsx, filename="sample.xlsx")
    dec_xlsx = enc_office.decode(stego_xlsx, filename="sample.xlsx")
    results.append(check("Document XLSX round-trip", dec_xlsx == payload_xlsx))

    # ── Detection ─────────────────────────────────────────────────────────────
    separator("Detection Engines")
    from detect.chi2 import Chi2Detector
    from detect.rs import RSDetector
    from detect.exif import EXIFDetector
    from detect.blind import BlindExtractor

    stego_for_detect = (FIXTURES / "sample.png").read_bytes()

    r_chi2 = Chi2Detector().analyze(stego_for_detect, "sample.png")
    results.append(check("Chi2 analyzer returns result", r_chi2.method == "chi2"))

    r_rs = RSDetector().analyze(stego_for_detect, "sample.png")
    results.append(check("RS analyzer returns result", r_rs.method == "rs"))

    r_exif = EXIFDetector().analyze((FIXTURES / "sample.pdf").read_bytes(), "sample.pdf")
    results.append(check("EXIF analyzer on PDF", r_exif.method == "exif"))

    r_blind = BlindExtractor().analyze(stego_for_detect, "sample.png")
    results.append(check("Blind extractor returns result", r_blind.method == "blind",
                         f"{r_blind.details.get('candidates_found',0)} candidates"))

    # EXIF on stego PDF should detect
    r_exif_stego = EXIFDetector().analyze(stego_pdf, "stego.pdf")
    results.append(check("EXIF detects stego PDF", r_exif_stego.detected is True))

    # ── Summary ───────────────────────────────────────────────────────────────
    separator("INTEGRATION TEST SUMMARY")
    passed = sum(1 for r in results if r)
    failed = len(results) - passed
    total = len(results)
    print(f"\n  Total : {total}")
    print(f"  [PASS] : {passed}")
    print(f"  [FAIL] : {failed}")
    print()
    if failed == 0:
        print("  ✓ ALL TESTS PASSED — StegoForge is ready to go!")
    else:
        print(f"  ✗ {failed} test(s) failed. Check output above.")
    print()
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
