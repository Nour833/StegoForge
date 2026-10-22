"""scripts/eval_detectors.py — detector triage eval + ROC corpus over tests/fixtures.

Usage:
  python scripts/eval_detectors.py [--json]                 # verdicts on stock fixtures
  python scripts/eval_detectors.py --build-corpus [--json]  # embed payloads → tmp corpus
  python scripts/eval_detectors.py --roc [--json]           # TPR/FPR per detector + thresholds

The ROC mode embeds a known payload into image fixtures (depths 1-4, keyed +
keyless), runs op_detect defaults, and reports per-detector true/false
positive rates. Results feed docs/DETECTOR-EVAL.md.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stegoforge import op_detect

FIXTURES = Path(__file__).parent.parent / "tests" / "fixtures"
IMAGE_EXTS = {".png", ".bmp", ".jpg", ".jpeg", ".webp", ".tiff"}


def _stock_rows() -> list[dict]:
    rows = []
    for f in sorted(FIXTURES.glob("*")):
        if not f.is_file():
            continue
        try:
            r = op_detect(str(f), False, False, False, False, False, False, False, False, False)
            rows.append({
                "file": f.name,
                "detectors_run": r["detectors_run"],
                "methods": [x["method"] for x in r["results"]],
                "verdicts": {x["method"]: x["detected"] for x in r["results"]},
                "confidence": {x["method"]: x["confidence"] for x in r["results"]},
            })
        except Exception as exc:  # noqa: BLE001 — eval must not stop on one file
            rows.append({"file": f.name, "error": str(exc)})
    return rows


def _build_corpus(tmp: Path) -> list[dict]:
    """Embed known payloads into image fixtures; return manifest rows."""
    from stegoforge import op_encode

    payload = tmp / "payload.bin"
    payload.write_bytes(b"EVAL-CORPUS-PAYLOAD-0123456789")
    manifest: list[dict] = []
    for f in sorted(FIXTURES.glob("*")):
        if f.suffix.lower() not in IMAGE_EXTS:
            continue
        for depth in (1, 2):
            for key in ("", "eval-key-123"):
                out = tmp / f"{f.stem}_d{depth}_{'key' if key else 'plain'}{f.suffix}"
                try:
                    r = op_encode(
                        str(f), str(payload), key or None, str(out), None, depth,
                        None, None, False, None, False, False, None, None, None,
                        True, allow_plaintext=(not key),
                    )
                    manifest.append({
                        "file": out.name, "path": str(out), "source": f.name,
                        "depth": depth, "keyed": bool(key), "method": r["method"],
                        "label": "stego",
                    })
                except Exception as exc:
                    manifest.append({
                        "file": out.name, "source": f.name, "depth": depth,
                        "keyed": bool(key), "label": "stego", "error": str(exc)[:120],
                    })
        manifest.append({"file": f.name, "path": str(f), "label": "clean"})
    return manifest


def _roc(manifest: list[dict]) -> dict:
    """Compute per-detector TPR (stego flagged) / FPR (clean flagged)."""
    stats: dict[str, dict] = {}
    for row in manifest:
        if "error" in row or "path" not in row:
            continue
        try:
            r = op_detect(row["path"], False, False, False, False, False, False, False, False, False)
        except Exception:
            continue
        for x in r["results"]:
            m = x["method"]
            s = stats.setdefault(m, {"tp": 0, "fp": 0, "stego_n": 0, "clean_n": 0})
            if row["label"] == "stego":
                s["stego_n"] += 1
                s["tp"] += 1 if x["detected"] else 0
            else:
                s["clean_n"] += 1
                s["fp"] += 1 if x["detected"] else 0
    out = {}
    for m, s in sorted(stats.items()):
        tpr = (s["tp"] / s["stego_n"]) if s["stego_n"] else 0.0
        fpr = (s["fp"] / s["clean_n"]) if s["clean_n"] else 0.0
        out[m] = {
            "tpr": round(tpr, 3), "fpr": round(fpr, 3),
            "stego_n": s["stego_n"], "clean_n": s["clean_n"],
            "guidance": (
                "high-precision" if fpr == 0 and tpr > 0.5
                else ("noisy-confirm" if fpr > 0.3 else "triage-only")
            ),
        }
    return out


def main() -> int:
    as_json = "--json" in sys.argv
    if "--roc" in sys.argv or "--build-corpus" in sys.argv:
        with tempfile.TemporaryDirectory(prefix="stegoforge_eval_") as td:
            manifest = _build_corpus(Path(td))
            if "--roc" in sys.argv:
                result = {"roc": _roc(manifest),
                          "manifest_n": len(manifest),
                          "errors": sum(1 for m in manifest if "error" in m)}
            else:
                result = {"manifest": [{k: v for k, v in m.items() if k != "path"} for m in manifest]}
            if as_json:
                print(json.dumps(result, indent=2))
            else:
                print(json.dumps(result, indent=2)[:4000])
        return 0
    rows = _stock_rows()
    if as_json:
        print(json.dumps(rows, indent=2))
    else:
        for row in rows:
            print(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
