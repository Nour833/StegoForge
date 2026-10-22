#!/usr/bin/env python3
"""scripts/ui_smoke.py — drive the real web UI in a browser: encode, download, decode, detect.

    uvx --with playwright --with pillow --with numpy python scripts/ui_smoke.py \
        [--chrome /usr/bin/google-chrome-stable] [--server-python PATH] [--shots DIR]

Starts the app on a free port, runs the main journeys through the DOM exactly as a
person would (file inputs, buttons, keyboard), and fails on any console error, any
failed request or any broken journey. Uses an installed Chrome/Chromium (no browser
download). Not part of ``pytest`` because it needs a browser.
"""
from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PASSPHRASE = "correct-horse-battery-29!"
SECRET = b"ui smoke payload: the quick brown fox"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_chrome(explicit: str | None) -> str:
    for candidate in [explicit, *(shutil.which(n) for n in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser"))]:
        if candidate and os.access(candidate, os.X_OK):
            return candidate
    raise SystemExit("no Chrome/Chromium found: pass --chrome /path/to/chrome")


def make_png(path: Path) -> None:
    from PIL import Image
    import numpy as np

    Image.fromarray(np.random.default_rng(7).integers(0, 256, (128, 128, 3), dtype=np.uint8)).save(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chrome")
    parser.add_argument("--server-python", default=str(ROOT / "venv" / "bin" / "python") if (ROOT / "venv" / "bin" / "python").exists() else sys.executable,
                        help="interpreter that has StegoForge's dependencies installed (default: ./venv, else this one)")
    parser.add_argument("--shots", type=Path, help="directory to save screenshots into")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    port = free_port()
    work = Path(tempfile.mkdtemp(prefix="sf_ui_"))
    make_png(work / "carrier.png")
    (work / "secret.txt").write_bytes(SECRET)
    if args.shots:
        args.shots.mkdir(parents=True, exist_ok=True)

    server = subprocess.Popen([args.server_python, str(ROOT / "stegoforge.py"), "web", "--port", str(port), "--skip-banner"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT)
    problems: list[str] = []
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.25)
        else:
            raise SystemExit("the web server did not start")
        base = f"http://127.0.0.1:{port}/"

        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=find_chrome(args.chrome), args=["--no-sandbox"])
            page = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True).new_page()
            # Chrome logs "Failed to load resource" for every non-2xx fetch. The journey below makes exactly one
            # on purpose (a wrong passphrase -> HTTP 400), so one such line is expected and any other is a problem.
            expected_400s = [1]

            def on_console(msg) -> None:
                if msg.type not in ("error", "warning"):
                    return
                if "status of 400" in msg.text and expected_400s[0] > 0:
                    expected_400s[0] -= 1
                    return
                problems.append(f"console {msg.type}: {msg.text}")

            def on_request_failed(req) -> None:
                # Chrome reports a *finished* streaming (text/event-stream) fetch as ERR_ABORTED; the stream itself is
                # checked for clean termination by the journey, so only non-SSE failures count.
                if "-stream" in req.url and "ERR_ABORTED" in str(req.failure):
                    return
                problems.append(f"request failed: {req.url} {req.failure}")

            page.on("console", on_console)
            page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
            page.on("requestfailed", on_request_failed)
            external = []
            page.on("request", lambda r: external.append(r.url) if not r.url.startswith(("http://127.0.0.1", "data:", "blob:")) else None)

            def shot(name: str) -> None:
                if args.shots:
                    page.screenshot(path=str(args.shots / f"{name}.png"), full_page=True)

            def step(label: str, ok: bool, detail: str = "") -> None:
                print(f"{'ok  ' if ok else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
                if not ok:
                    problems.append(f"{label} {detail}".strip())

            page.goto(base)
            page.wait_for_load_state("networkidle")
            step("fonts are served locally", page.evaluate("document.fonts.check('16px Geist')"))
            step("no third-party requests", not external, ", ".join(external))
            step("skip link is the first tab stop", (page.keyboard.press("Tab") or True) and page.evaluate("document.activeElement.className") == "skip-link")
            shot("01_encode_empty")

            # ── tabs by keyboard (WAI-ARIA tabs pattern) ──────────────────────────────
            page.focus("#nav-encode")
            page.keyboard.press("ArrowRight")
            step("ArrowRight activates the next tab", page.get_attribute("#nav-decode", "aria-selected") == "true"
                 and page.is_visible("#tab-decode") and not page.is_visible("#tab-encode"))
            step("URL hash follows the tab", page.evaluate("location.hash") == "#decode")
            page.keyboard.press("End")
            step("End jumps to the last tab", page.get_attribute("#nav-help", "aria-selected") == "true")
            page.click("#nav-encode")

            # ── oversize or missing input is refused inline (no alert) ─────────────────
            dialogs = []
            page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
            page.click("#enc-submit")
            step("required fields block submit without an alert()", not dialogs and not page.is_visible("#encode-result"))

            # ── encode ───────────────────────────────────────────────────────────────
            page.set_input_files("#enc-carrier", str(work / "carrier.png"))
            page.set_input_files("#enc-payload", str(work / "secret.txt"))
            page.fill("#enc-key", PASSPHRASE)
            page.wait_for_selector("#enc-capacity-matrix .capacity-row")
            step("capacity table fills in", page.locator("#enc-capacity-matrix .capacity-row").count() > 3)
            step("file name shown in the drop zone", "carrier.png" in page.inner_text("#enc-carrier-drop"))
            step("passphrase strength shown", page.locator("#enc-key-strength .strength-label").inner_text() in ("Strong", "Fair"))
            page.click("#enc-key-toggle")
            step("passphrase toggle reveals and labels itself", page.get_attribute("#enc-key", "type") == "text"
                 and page.get_attribute("#enc-key-toggle", "aria-label") == "Hide passphrase")
            page.click("#enc-key-toggle")
            page.click('.method-pill[data-method="lsb"]')
            step("choosing a method updates its description", "Least-significant bits" in page.inner_text("#method-desc"))
            shot("02_encode_filled")
            page.click("#enc-submit")
            page.wait_for_selector("#encode-result .btn-primary", timeout=60000)
            step("encode result shows a summary", "Payload embedded" in page.inner_text("#encode-result")
                 and "lsb" in page.inner_text("#encode-result"))
            step("progress bar is gone afterwards", not page.is_visible("#loading-overlay"))
            shot("03_encode_result")
            with page.expect_download() as info:
                page.click("#encode-result .btn-primary")
            stego = work / info.value.suggested_filename
            info.value.save_as(stego)
            step("download is named after the produced file", info.value.suggested_filename == "carrier_stego.png", info.value.suggested_filename)

            # ── decode ───────────────────────────────────────────────────────────────
            page.click("#nav-decode")
            page.set_input_files("#dec-file", str(stego))
            page.fill("#dec-key", "wrong-passphrase-wrong-1!")
            page.click("#dec-submit")
            page.wait_for_selector("#decode-result .result-card.error")
            step("wrong passphrase shows an inline error", "Failed to decode" in page.inner_text("#decode-result"))
            shot("04_decode_error")
            page.fill("#dec-key", PASSPHRASE)
            page.click("#dec-submit")
            page.wait_for_selector("#decode-result .result-card.success")
            step("decode recovers the payload", SECRET.decode() in page.input_value("#decode-result textarea"))
            shot("05_decode_result")

            # ── detect ───────────────────────────────────────────────────────────────
            page.click("#nav-detect")
            page.set_input_files("#det-file", str(stego))
            page.click("#det-submit")
            page.wait_for_selector("#detect-result .result-card")
            step("detector cards render with status chips", page.locator("#detect-result .status-chip").count() >= 3)
            shot("06_detect_result")

            # ── hostile file names and metadata cannot inject markup ─────────────────
            evil = work / "x<img src=x onerror=window.__pwned=1>.png"
            shutil.copy(work / "carrier.png", evil)
            page.click("#nav-capacity")
            page.set_input_files("#cap-file", str(evil))
            step("a markup-laden file name is rendered as text", page.evaluate("window.__pwned") is None
                 and "<img" in page.inner_text("#cap-file-drop"))

            # ── other tabs render and the help copy is present ───────────────────────
            for tab in ("ctf", "capacity", "diff", "survive", "help"):
                page.click(f"#nav-{tab}")
                step(f"{tab} tab renders", page.is_visible(f"#tab-{tab}"))
            shot("07_help")

            # ── mobile ───────────────────────────────────────────────────────────────
            page.set_viewport_size({"width": 390, "height": 844})
            page.click("#nav-encode")
            overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            step("no horizontal page scroll on a phone", overflow <= 0, f"overflow {overflow}px")
            shot("08_mobile")
            browser.close()
    finally:
        server.terminate()
        shutil.rmtree(work, ignore_errors=True)

    if problems:
        print("\nPROBLEMS:", *problems, sep="\n  - ")
        return 1
    print("\nUI smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
