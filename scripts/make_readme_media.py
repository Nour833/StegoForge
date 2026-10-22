#!/usr/bin/env python3
"""scripts/make_readme_media.py — regenerate the README's screenshots and demo GIFs from the real program.

    uvx --with playwright --with pillow --with numpy --with rich python scripts/make_readme_media.py \\
        [--out docs/media] [--server-python venv/bin/python] [--chrome /usr/bin/google-chrome-stable]

Nothing here is mocked: the web demo is a screen recording of the actual UI in Chrome, and the
terminal demo replays the *captured output* of the actual CLI (typing is simulated, output is not).
Re-run it whenever the UI or the CLI output changes.
"""
from __future__ import annotations

import argparse
import io
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
SECRET_TEXT = "Meet at the old pier, 21:40. Bring the second key."
ACCENT, OK, BAD, MUTED = "#d6a243", "#7db38a", "#d9705f", "#8d8676"


# ── a believable cover photo, generated (no stock image licence to worry about) ──────────────
def make_photo(path: Path, w: int = 800, h: int = 520) -> None:
    import numpy as np
    from PIL import Image, ImageFilter

    rng = np.random.default_rng(11)
    y = np.linspace(0, 1, h)[:, None]
    x = np.linspace(0, 1, w)[None, :]

    def lerp(a, b, t):
        return np.array(a, float)[None, None, :] * (1 - t[..., None]) + np.array(b, float)[None, None, :] * t[..., None]

    horizon = 0.64
    t_sky = np.clip(y / horizon, 0, 1) ** 0.85 * np.ones_like(x)
    img = lerp((22, 30, 70), (242, 168, 92), t_sky)
    sun = np.exp(-(((x - 0.68) / 0.20) ** 2 + ((y - 0.60) / 0.16) ** 2))
    img += sun[..., None] * np.array([120, 70, 20])[None, None, :]
    for i, (base, amp, col) in enumerate([(0.60, 0.05, (58, 48, 70)), (0.66, 0.06, (36, 30, 48)), (0.73, 0.05, (18, 15, 26))]):
        ridge = base + amp * (np.sin(x * (6 + 3 * i) + i) * 0.6 + np.sin(x * (17 + 5 * i) + 2 * i) * 0.25)
        mask = (y > ridge)[..., None]
        img = np.where(mask, np.array(col, float)[None, None, :] + (y - ridge)[..., None] * 25, img)
    water = (y > 0.80)[..., None]
    ripples = np.sin(y * 260 + np.sin(x * 14) * 3) * 6
    img = np.where(water, img * 0.55 + np.array([40, 26, 12])[None, None, :] + ripples[..., None], img)
    img += rng.normal(0, 2.4, img.shape)
    Image.fromarray(np.clip(img, 0, 255).astype("uint8")).filter(ImageFilter.GaussianBlur(0.4)).save(path)


# ── terminal replay ────────────────────────────────────────────────────────────────────────
TERM_PAGE = """<!doctype html><meta charset="utf-8"><style>
@font-face{font-family:"Geist Mono";src:url("%(font)s") format("woff2");font-weight:100 900}
html,body{margin:0;background:transparent}
#term{width:%(width)dpx;box-sizing:border-box;background:#181714;border:1px solid #2e2b25;border-radius:12px;overflow:hidden;
  box-shadow:0 18px 48px rgba(0,0,0,.45);font-family:"Geist Mono",ui-monospace,monospace}
#bar{height:34px;background:#1f1d19;border-bottom:1px solid #2e2b25;display:flex;align-items:center;padding:0 14px;gap:8px;color:#8d8676;font-size:12px}
#bar i{width:11px;height:11px;border-radius:50%%;background:#34312b;display:block}
#bar span{margin-left:10px;letter-spacing:.02em}
pre{margin:0;padding:18px 22px 22px;color:#ece7dc;font:13.5px/1.55 "Geist Mono",ui-monospace,monospace;white-space:pre;%(pre_style)s}
.cur{background:#d6a243;color:#12110f}
</style><div id="term"><div id="bar"><i></i><i></i><i></i><span>stegoforge</span></div><pre id="out">%(body)s</pre></div>"""


def ansi_to_html(ansi: str, width: int) -> list[str]:
    """One HTML string per output line, colours preserved."""
    from rich.console import Console
    from rich.text import Text

    lines = []
    for line in Text.from_ansi(ansi.rstrip("\n")).split("\n"):
        con = Console(record=True, width=width + 40, file=io.StringIO(), force_terminal=True, color_system="truecolor", legacy_windows=False)
        con.print(line, end="", soft_wrap=True)
        html = con.export_html(inline_styles=True, code_format="{code}")
        lines.append(html.rstrip("\n"))
    return lines


def prompt_html(cmd: str, cursor: bool) -> str:
    import html as h

    cur = '<span class="cur"> </span>' if cursor else ""
    return f'<span style="color:{ACCENT}">$</span> <span style="font-weight:600">{h.escape(cmd)}</span>{cur}'


def capture_boot(py: str, cwd: Path) -> dict:
    """The real boot banner, split into the pieces the real code animates (see stegoforge.print_banner)."""
    from rich.text import Text

    code = ("import stegoforge as s\nfrom rich.align import Align\n"
            "s.print_banner()\nprint('@@HL@@')\ns.console.print(Align.center(f'[dim]{s.TAGLINES[0]}[/dim]'), highlight=False)\n"
            "print('@@TAG@@' + s.PRIMARY_TAGLINE)")
    env = {**os.environ, "COLUMNS": "100", "FORCE_COLOR": "1", "COLORTERM": "truecolor", "TERM": "xterm-256color", "STEGOFORGE_FAST_UI": "1"}
    env.pop("NO_COLOR", None)
    raw = subprocess.run([py, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True).stdout
    banner, rest = raw.split("@@HL@@\n")
    highlight, tagline = rest.split("@@TAG@@")
    lines = ansi_to_html(banner, 100)
    plain = [ln.plain for ln in Text.from_ansi(banner.rstrip("\n")).split("\n")]
    art = lines[:6]
    start = next(i for i, ln in enumerate(plain) if "╭" in ln)
    panel = [lines[i] for i in range(start, len(lines)) if plain[i].strip()]
    return {"art": art, "panel": panel, "highlight": ansi_to_html(highlight, 100)[0], "tagline": tagline.strip()}


def boot_frames(page, boot: dict, width_px: int, workdir: Path, font_uri: str, height_px: int, snapshot):
    """Replay the boot with the real code's cadence: art lines (80 ms each), typed tagline, highlight line, panel."""
    import html as h

    frames: list[tuple[bytes, int]] = []
    head = prompt_html("stegoforge", False)
    art, tag = boot["art"], boot["tagline"]
    pad = " " * max(0, (100 - len(tag)) // 2)

    def shot(lines: list[str], hold: int) -> None:
        frames.append((snapshot(page, workdir, font_uri, width_px, height_px, "\n".join([head, *lines])), hold))

    for k in range(1, len(art) + 1):
        shot(art[:k], 90)
    shot([*art, ""], 300)
    for i in range(0, len(tag), 3):
        shot([*art, "", f'{pad}<span style="font-weight:700;color:#fff">{h.escape(tag[:i + 3])}</span>'], 38)
    typed = f'{pad}<span style="font-weight:700;color:#fff">{h.escape(tag)}</span>'
    shot([*art, "", typed, "", boot["highlight"]], 420)
    shot([*art, "", typed, "", boot["highlight"], "", *boot["panel"]], 3200)
    return frames


def snapshot(page, workdir: Path, font_uri: str, width_px: int, height_px: int, body: str) -> bytes:
    f = workdir / "term.html"
    f.write_text(TERM_PAGE % {"font": font_uri, "width": width_px, "pre_style": f"height:{height_px}px;overflow:hidden", "body": body}, encoding="utf-8")
    page.goto(f.as_uri())
    page.wait_for_load_state("load")
    page.evaluate("document.fonts.ready")
    return page.locator("#term").screenshot()


def render_terminal_frames(page, steps, width_px: int, workdir: Path, font_uri: str, height_px: int):
    """steps: [(command, output_lines_html, clear_first)] -> list of (png_bytes, hold_ms).

    The window has a fixed height, like a real terminal; ``clear_first`` starts a fresh screen.
    """
    frames: list[tuple[bytes, int]] = []

    def shot(history: list[str], hold: int) -> None:
        body = "\n".join(history)
        html = TERM_PAGE % {"font": font_uri, "width": width_px, "pre_style": f"height:{height_px}px;overflow:hidden", "body": body}
        f = workdir / "term.html"
        f.write_text(html, encoding="utf-8")
        page.goto(f.as_uri())
        page.wait_for_load_state("load")
        page.evaluate("document.fonts.ready")
        frames.append((page.locator("#term").screenshot(), hold))

    history: list[str] = []
    for cmd, out, clear_first in steps:
        if clear_first:
            history = []
        typed = ""
        chunks = [cmd[i:i + 3] for i in range(0, len(cmd), 3)]
        for chunk in chunks:
            typed += chunk
            shot(history + [prompt_html(typed, True)], 70)
        shot(history + [prompt_html(cmd, True)], 380)
        done = history + [prompt_html(cmd, False)]
        for k in range(1, len(out) + 1, max(1, len(out) // 3)):
            shot(done + out[:k], 120)
        shot(done + out, 2600)
        history = done + out + [""]
    return frames


def frames_to_gif(frames, path: Path, colors: int = 160) -> None:
    from PIL import Image

    imgs, durs = [], []
    target = Image.open(io.BytesIO(frames[-1][0])).size
    for png, hold in frames:
        im = Image.open(io.BytesIO(png)).convert("RGB")
        canvas = Image.new("RGB", target, (18, 17, 15))
        canvas.paste(im, (0, 0))
        if imgs and canvas.tobytes() == imgs[-1].tobytes():
            durs[-1] += hold
            continue
        imgs.append(canvas)
        durs.append(hold)
    # one palette from frames across the whole recording: a banner's amber must not be lost to the last scene's greys
    sample = imgs[:: max(1, len(imgs) // 24)] + [imgs[-1]]
    montage = Image.new("RGB", (target[0], sum(i.height for i in sample)))
    y = 0
    for im in sample:
        montage.paste(im, (0, y))
        y += im.height
    pal = montage.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    quant = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in imgs]
    quant[0].save(path, save_all=True, append_images=quant[1:], duration=durs, loop=0, optimize=True, disposal=1)


# ── helpers ────────────────────────────────────────────────────────────────────────────────
def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def find_chrome(explicit: str | None) -> str:
    for c in [explicit, *(shutil.which(n) for n in ("google-chrome-stable", "google-chrome", "chromium", "chromium-browser"))]:
        if c and os.access(c, os.X_OK):
            return c
    raise SystemExit("no Chrome/Chromium found: pass --chrome")


def cli(py: str, cwd: Path, args: list[str], env_extra: dict[str, str] | None = None) -> str:
    env = {**os.environ, "COLUMNS": "100", "FORCE_COLOR": "1", "COLORTERM": "truecolor", "TERM": "xterm-256color",
           "STEGOFORGE_FAST_UI": "1", "NO_COLOR": ""}
    env.pop("NO_COLOR", None)
    env.update(env_extra or {})
    done = subprocess.run([py, str(ROOT / "stegoforge.py"), *args], cwd=cwd, env=env, capture_output=True, text=True)
    return done.stdout + (done.stderr if done.returncode else "")


class Screencast:
    """Chrome DevTools screencast: timestamped frames, no extra binaries needed."""

    def __init__(self, ctx, page, width: int, height: int):
        import base64

        self._b64 = base64
        self.frames: list[tuple[float, bytes]] = []
        self.cdp = ctx.new_cdp_session(page)
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.size = (width, height)

    def _on_frame(self, params) -> None:
        self.frames.append((params["metadata"]["timestamp"], self._b64.b64decode(params["data"])))
        self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

    def start(self) -> None:
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 82, "maxWidth": self.size[0],
                                               "maxHeight": self.size[1], "everyNthFrame": 1})

    def stop(self) -> None:
        self.cdp.send("Page.stopScreencast")


def screencast_to_gif(frames: list[tuple[float, bytes]], path: Path, width: int = 900, fps: int = 9, colors: int = 128) -> None:
    from PIL import Image

    frames = sorted(frames)
    t0, t1 = frames[0][0], frames[-1][0]
    step = 1.0 / fps
    picked, durs, idx, t = [], [], 0, t0
    while t <= t1:
        while idx + 1 < len(frames) and frames[idx + 1][0] <= t:
            idx += 1
        if picked and picked[-1] == idx:
            durs[-1] += int(step * 1000)
        else:
            picked.append(idx)
            durs.append(int(step * 1000))
        t += step
    images = []
    for i in picked:
        im = Image.open(io.BytesIO(frames[i][1])).convert("RGB")
        images.append(im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS))
    sample = images[:: max(1, len(images) // 30)]
    montage = Image.new("RGB", (width, sum(i.height for i in sample)))
    y = 0
    for im in sample:
        montage.paste(im, (0, y))
        y += im.height
    pal = montage.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    quant = [im.quantize(palette=pal, dither=Image.Dither.NONE) for im in images]
    durs[-1] += 1800  # linger on the final frame
    quant[0].save(path, save_all=True, append_images=quant[1:], duration=durs, loop=0, optimize=True, disposal=1)


CURSOR_JS = """
(() => {
  const dot = document.createElement('div');
  dot.style.cssText = 'position:fixed;z-index:99999;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;' +
    'border:2px solid #d6a243;background:rgba(214,162,67,.18);pointer-events:none;transition:transform .12s;left:-50px;top:-50px';
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(dot));
  document.addEventListener('mousemove', e => { dot.style.left = e.clientX + 'px'; dot.style.top = e.clientY + 'px'; }, true);
  document.addEventListener('mousedown', () => { dot.style.transform = 'scale(.7)'; }, true);
  document.addEventListener('mouseup', () => { dot.style.transform = 'scale(1)'; }, true);
})();
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "media")
    ap.add_argument("--chrome")
    ap.add_argument("--server-python", default=str(ROOT / "venv" / "bin" / "python") if (ROOT / "venv" / "bin" / "python").exists() else sys.executable)
    ap.add_argument("--skip-web", action="store_true")
    ap.add_argument("--skip-cli", action="store_true")
    args = ap.parse_args()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="sf_media_"))
    font_uri = (ROOT / "web" / "static" / "fonts" / "GeistMono.woff2").as_uri()
    py = args.server_python

    from playwright.sync_api import sync_playwright

    photo = work / "sunset.png"
    make_photo(photo)
    (work / "secret.txt").write_text(SECRET_TEXT)
    chrome = find_chrome(args.chrome)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox"])

        # ── terminal demo + PNG shots ────────────────────────────────────────────────────
        if not args.skip_cli:
            cwd = work / "cli"
            cwd.mkdir()
            shutil.copy(photo, cwd / "sunset.png")
            shutil.copy(work / "secret.txt", cwd / "secret.txt")
            envk = {"STEGOFORGE_KEY": PASSPHRASE}
            # a second, *unencrypted* embed for the CTF scene
            shutil.copy(photo, cwd / "challenge.png")
            cli(py, cwd, ["encode", "-c", "challenge.png", "-p", "secret.txt", "--allow-plaintext", "-o", "challenge_stego.png", "--json"])
            scenes = [
                ("STEGOFORGE_KEY=\"…\" stegoforge encode -c sunset.png -p secret.txt", ["encode", "-c", "sunset.png", "-p", "secret.txt"], envk),
                ("STEGOFORGE_KEY=\"…\" stegoforge decode -f sunset_stego.png", ["decode", "-f", "sunset_stego.png", "-o", "recovered.txt"], envk),
                ("stegoforge ctf -f challenge_stego.png", ["ctf", "-f", "challenge_stego.png"], None),
                ("stegoforge doctor", ["doctor"], None),
            ]
            steps = []
            clears = [False, False, True, True]  # encode+decode share a screen; ctf and doctor each get a fresh one
            for shown, argv, env in scenes:
                text = cli(py, cwd, argv, env)
                # a spinner redraws one line in place on a real terminal; a pipe records every redraw
                text = "\n".join(ln for ln in text.splitlines() if "Running all detectors" not in ln)
                steps.append((shown, ansi_to_html(text, 100)))
            ctx = browser.new_context(viewport={"width": 1100, "height": 900}, device_scale_factor=1)
            page = ctx.new_page()
            boot = capture_boot(py, cwd)
            frames = boot_frames(page, boot, 940, work, font_uri, 660, snapshot)
            frames += render_terminal_frames(page, [(c, o, clears[i]) for i, (c, o) in enumerate(steps)], 940, work, font_uri, 660)
            frames_to_gif(frames, out / "cli-demo.gif")
            # crisp PNGs of individual scenes at 2x
            ctx2 = browser.new_context(viewport={"width": 1100, "height": 900}, device_scale_factor=2)
            page2 = ctx2.new_page()
            for name, idx in (("cli-encode", 0), ("cli-ctf", 2), ("cli-doctor", 3)):
                shown, lines = steps[idx]
                body = prompt_html(shown, False) + "\n" + "\n".join(lines)
                (work / "t.html").write_text(TERM_PAGE % {"font": font_uri, "width": 940, "pre_style": "", "body": body}, encoding="utf-8")
                page2.goto((work / "t.html").as_uri())
                page2.evaluate("document.fonts.ready")
                (out / f"{name}.png").write_bytes(page2.locator("#term").screenshot())
            ctx.close()
            ctx2.close()

        # ── web demo: record the real UI ─────────────────────────────────────────────────
        if not args.skip_web:
            port = free_port()
            server = subprocess.Popen([py, str(ROOT / "stegoforge.py"), "web", "--port", str(port), "--skip-banner"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT)
            try:
                for _ in range(80):
                    try:
                        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                        break
                    except OSError:
                        time.sleep(0.25)
                base = f"http://127.0.0.1:{port}/"
                ctx = browser.new_context(viewport={"width": 1280, "height": 760}, accept_downloads=True)
                ctx.add_init_script(CURSOR_JS)
                page = ctx.new_page()
                page.goto(base + "#encode")
                page.wait_for_load_state("networkidle")
                cast = Screencast(ctx, page, 1280, 760)
                cast.start()

                def hover(sel: str, pause: int = 350) -> None:
                    box = page.locator(sel).first.bounding_box()
                    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=18)
                    page.wait_for_timeout(pause)

                page.wait_for_timeout(900)
                hover("#enc-carrier-drop")
                page.set_input_files("#enc-carrier", str(photo))
                page.wait_for_selector("#enc-capacity-matrix .capacity-row")
                page.wait_for_timeout(700)
                hover("#enc-payload-drop")
                page.set_input_files("#enc-payload", str(work / "secret.txt"))
                page.wait_for_timeout(500)
                hover("#enc-key")
                page.click("#enc-key")
                page.keyboard.type(PASSPHRASE, delay=55)
                page.wait_for_timeout(600)
                hover('.method-pill[data-method="adaptive-lsb"]')
                page.click('.method-pill[data-method="adaptive-lsb"]')
                page.wait_for_timeout(900)
                (out / "web-encode.png").write_bytes(page.screenshot(full_page=False))
                hover("#enc-submit", 500)
                page.click("#enc-submit")
                page.wait_for_selector("#encode-result .btn-primary", timeout=60000)
                page.mouse.wheel(0, 700)
                page.wait_for_timeout(1500)
                with page.expect_download() as dl:
                    page.click("#encode-result .btn-primary")
                stego = work / dl.value.suggested_filename
                dl.value.save_as(stego)
                page.mouse.wheel(0, -1200)
                hover("#nav-decode")
                page.click("#nav-decode")
                page.wait_for_timeout(500)
                hover("#dec-file-drop")
                page.set_input_files("#dec-file", str(stego))
                hover("#dec-key")
                page.click("#dec-key")
                page.keyboard.type(PASSPHRASE, delay=45)
                hover("#dec-submit", 400)
                page.click("#dec-submit")
                page.wait_for_selector("#decode-result .result-card.success")
                page.wait_for_timeout(1800)
                hover("#nav-detect")
                page.click("#nav-detect")
                page.wait_for_timeout(500)
                hover("#det-file-drop")
                page.set_input_files("#det-file", str(stego))
                hover("#det-submit", 400)
                page.click("#det-submit")
                page.wait_for_selector("#detect-result .result-card")
                page.mouse.wheel(0, 360)
                page.wait_for_timeout(900)
                (out / "web-detect.png").write_bytes(page.screenshot(full_page=False))
                page.wait_for_timeout(2200)
                cast.stop()
                screencast_to_gif(cast.frames, out / "web-demo.gif")
                ctx.close()

                # mobile screenshot
                mctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
                mp = mctx.new_page()
                mp.goto(base + "#encode")
                mp.wait_for_load_state("networkidle")
                mp.set_input_files("#enc-carrier", str(photo))
                mp.set_input_files("#enc-payload", str(work / "secret.txt"))
                mp.wait_for_timeout(700)
                (out / "web-mobile.png").write_bytes(mp.screenshot())
                mctx.close()

            finally:
                server.terminate()
        browser.close()

    shutil.rmtree(work, ignore_errors=True)
    from PIL import Image

    for png in out.glob("*.png"):  # flat UI colours: a 192-colour palette is visually lossless and several times smaller
        im = Image.open(png).convert("RGB")
        im.quantize(colors=192, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(png, optimize=True)
    for p in sorted(out.iterdir()):
        print(f"{p.stat().st_size / 1024:8.0f} KB  {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
