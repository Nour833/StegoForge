"""
tests/generate_fixtures.py — Generate all test fixtures programmatically.

Run: python tests/generate_fixtures.py

Creates in tests/fixtures/:
  - sample.png         512×512 RGB noise PNG
  - sample.bmp         256×256 RGB BMP
  - sample.jpg         512×512 JPEG quality 95
  - sample_rgba.png    512×512 RGBA PNG (for alpha tests)
  - sample_indexed.gif small indexed GIF with palette
  - sample.wav         3s noise+silence 44100Hz 16-bit stereo WAV
  - sample.pdf         minimal valid PDF
  - sample.docx        minimal valid DOCX
  - sample.xlsx        minimal valid XLSX
  - sample.txt         lorem ipsum text file
"""
import os
import sys
import io
import struct
import zipfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"


def ensure_dir():
    FIXTURES.mkdir(parents=True, exist_ok=True)


def gen_png():
    from PIL import Image
    import numpy as np
    arr = np.random.randint(0, 256, (512, 512, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    img.save(FIXTURES / "sample.png", format="PNG")
    print("  ✓ sample.png")


def gen_bmp():
    from PIL import Image
    import numpy as np
    arr = np.random.randint(0, 256, (256, 256, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    img.save(FIXTURES / "sample.bmp", format="BMP")
    print("  ✓ sample.bmp")


def gen_jpg():
    from PIL import Image
    import numpy as np
    arr = np.random.randint(0, 256, (512, 512, 3), dtype=np.uint8)
    img = Image.fromarray(arr, "RGB")
    img.save(FIXTURES / "sample.jpg", format="JPEG", quality=95, subsampling=0)
    print("  ✓ sample.jpg")


def gen_rgba_png():
    from PIL import Image
    import numpy as np
    arr = np.random.randint(0, 256, (256, 256, 4), dtype=np.uint8)
    arr[:, :, 3] = np.random.randint(128, 256, (256, 256), dtype=np.uint8)  # semi-opaque
    img = Image.fromarray(arr, "RGBA")
    img.save(FIXTURES / "sample_rgba.png", format="PNG")
    print("  ✓ sample_rgba.png")


def gen_gif():
    from PIL import Image
    img = Image.new("P", (64, 64))
    # Create a simple palette
    palette = []
    for i in range(256):
        palette.extend([i, 255 - i, (i * 3) % 256])
    img.putpalette(palette)
    # Draw some pixels
    for x in range(64):
        for y in range(64):
            img.putpixel((x, y), (x + y) % 256)
    img.save(FIXTURES / "sample_indexed.gif", format="GIF")
    print("  ✓ sample_indexed.gif")


def gen_wav():
    import numpy as np
    import wave
    sample_rate = 44100
    duration = 3
    channels = 2
    n_samples = sample_rate * duration

    # Mix of silence and white noise
    noise = (np.random.random((n_samples, channels)) * 2 - 1) * 0.1
    samples = (noise * 32767).astype(np.int16)

    with wave.open(str(FIXTURES / "sample.wav"), 'w') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples.tobytes())
    print("  ✓ sample.wav")


def gen_pdf():
    content = b"""\
%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]
   /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 14 Tf 100 700 Td (Hello, StegoForge!) Tj ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000360 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
441
%%EOF
"""
    (FIXTURES / "sample.pdf").write_bytes(content)
    print("  ✓ sample.pdf")


def gen_docx():
    """Create a minimal valid DOCX file (ZIP archive)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""")

        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="word/document.xml"/>
</Relationships>""")

        zf.writestr("word/document.xml", """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Hello, StegoForge!</w:t></w:r></w:p>
  </w:body>
</w:document>""")

        zf.writestr("word/_rels/document.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
</Relationships>""")

    (FIXTURES / "sample.docx").write_bytes(buf.getvalue())
    print("  ✓ sample.docx")


def gen_xlsx():
    """Create a minimal valid XLSX file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""")

        zf.writestr("_rels/.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="xl/workbook.xml"/>
</Relationships>""")

        zf.writestr("xl/workbook.xml", """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""")

        zf.writestr("xl/_rels/workbook.xml.rels", """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
    Target="worksheets/sheet1.xml"/>
</Relationships>""")

        zf.writestr("xl/worksheets/sheet1.xml", """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Hello, StegoForge!</t></is></c>
    </row>
  </sheetData>
</worksheet>""")

    (FIXTURES / "sample.xlsx").write_bytes(buf.getvalue())
    print("  ✓ sample.xlsx")


def gen_txt():
    text = (
        "The quick brown fox jumps over the lazy dog.\n"
        "StegoForge is the most complete steganography toolkit.\n"
        "This text file is used as a carrier for zero-width Unicode encoding.\n"
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.\n"
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.\n" * 10
    )
    (FIXTURES / "sample.txt").write_text(text, encoding="utf-8")
    print("  ✓ sample.txt")


if __name__ == "__main__":
    print("Generating StegoForge test fixtures…\n")
    ensure_dir()
    gen_png()
    gen_bmp()
    gen_jpg()
    gen_rgba_png()
    gen_gif()
    gen_wav()
    gen_pdf()
    gen_docx()
    gen_xlsx()
    gen_txt()
    print(f"\n✓ All fixtures written to {FIXTURES}/")
