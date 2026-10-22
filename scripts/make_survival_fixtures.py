"""scripts/make_survival_fixtures.py — recompress corpus + manifest for survival eval.

Generates JPEG recompress variants (qualities 95/85/75) of stock fixtures and
a manifest.json recording sha256 + dimensions. Used to measure wet-paper
correction and detector drift under real recompression.

Usage: python scripts/make_survival_fixtures.py [--out DIR] [--json]
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
QUALITIES = (95, 85, 75)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    as_json = "--json" in sys.argv
    out = Path("survival_fixtures")
    for i, a in enumerate(sys.argv):
        if a == "--out" and i + 1 < len(sys.argv):
            out = Path(sys.argv[i + 1])
    out.mkdir(parents=True, exist_ok=True)
    from PIL import Image

    manifest: list[dict] = []
    for f in sorted(FIXTURES.glob("*")):
        if f.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}:
            continue
        try:
            img = Image.open(f).convert("RGB")
        except Exception:
            continue
        raw = f.read_bytes()
        manifest.append({
            "file": f.name, "variant": "original", "sha256": _sha(raw),
            "size": list(img.size), "quality": None,
        })
        for q in QUALITIES:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=q, subsampling=0)
            data = buf.getvalue()
            name = f"{f.stem}_q{q}.jpg"
            (out / name).write_bytes(data)
            manifest.append({
                "file": name, "variant": "recompress", "sha256": _sha(data),
                "size": list(img.size), "quality": q, "source": f.name,
            })
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if as_json:
        print(json.dumps({"out": str(out), "n": len(manifest)}))
    else:
        print(f"wrote {len(manifest)} entries to {out}/manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
