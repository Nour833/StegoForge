"""tests/test_web_assets.py — the web UI's static contract.

The script, template and stylesheet are edited by hand and nothing else ties them
together, so a renamed ID or a missing icon fails silently in the browser. These
tests make those mistakes loud, and pin the privacy promise that the page loads
nothing from a third party.
"""
import io
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from web.app import create_app

WEB = Path(__file__).parent.parent / "web"
HTML = (WEB / "templates" / "index.html").read_text()
JS = (WEB / "static" / "app.js").read_text()
CSS = (WEB / "static" / "style.css").read_text()
FIXTURES = Path(__file__).parent / "fixtures"


class _Ids(HTMLParser):
    VOID = {"meta", "link", "input", "br", "img", "hr", "use", "path", "circle", "rect"}

    def __init__(self):
        super().__init__()
        self.ids: list[str] = []
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "id" and value:
                self.ids.append(value)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> at {self.getpos()}")
        else:
            self.stack.pop()


@pytest.fixture(scope="module")
def parsed() -> _Ids:
    parser = _Ids()
    parser.feed(HTML)
    return parser


def test_template_is_well_formed_with_unique_ids(parsed):
    assert not parsed.errors and not parsed.stack
    dupes = sorted({i for i in parsed.ids if parsed.ids.count(i) > 1})
    assert not dupes, f"duplicate ids: {dupes}"


def test_every_id_the_script_looks_up_exists_in_the_template(parsed):
    wanted = set(re.findall(r"\$\('([^']+)'\)", JS)) | set(re.findall(r"getElementById\('([^']+)'\)", JS))
    wanted |= {a for pair in re.findall(r"\['([a-z-]+-drop)', '([a-z-]+)', '([a-z-]+-info)'\]", JS) for a in pair}
    wanted -= {"tab-${tabId}"}  # built at run time from data-tab
    missing = sorted(w for w in wanted if w not in parsed.ids and "$" not in w)
    assert not missing, f"app.js looks up ids that index.html does not define: {missing}"


def test_tabs_and_panels_line_up(parsed):
    tabs = re.findall(r'data-tab="([a-z]+)"', HTML)
    assert len(tabs) == len(set(tabs)) >= 8
    for tab in tabs:
        assert f"tab-{tab}" in parsed.ids, f"no panel for tab {tab!r}"
        assert f"nav-{tab}" in parsed.ids
    assert re.search(rf'aria-controls="tab-({"|".join(tabs)})"', HTML)


def test_every_icon_in_use_is_defined_in_the_sprite():
    defined = set(re.findall(r'<symbol id="(i-[a-z-]+)"', HTML))
    used = set(re.findall(r'href="#(i-[a-z-]+)"', HTML)) | {f"i-{n}" for n in re.findall(r"ico\('([a-z-]+)'\)", JS)}
    used |= {f"i-{n}" for n in re.findall(r"ico\(show \? '([a-z-]+)' : '([a-z-]+)'\)", JS)[0]} if "ico(show ?" in JS else set()
    used |= {f"i-{n}" for n in re.findall(r"ico\(ok \? '([a-z-]+)' : '([a-z-]+)'\)", JS)[0]} if "ico(ok ?" in JS else set()
    missing = sorted(used - defined)
    assert not missing, f"icons used but not in the sprite: {missing}"


def test_page_requests_nothing_from_a_third_party():
    for name, text in (("index.html", HTML), ("style.css", CSS), ("app.js", JS)):
        urls = re.findall(r"https?://[^\s\"')>]+", text)
        urls = [u for u in urls if "www.w3.org/2000/svg" not in u  # an XML namespace, not a request
                and not re.match(r"https?://(localhost|127\.0\.0\.1)\b", u)]
        assert not urls, f"{name} references external URLs: {urls}"


def test_fonts_are_self_hosted_with_their_license():
    fonts = WEB / "static" / "fonts"
    for name in ("Geist.woff2", "GeistMono.woff2"):
        assert (fonts / name).read_bytes()[:4] == b"wOF2", name
        assert f"/static/fonts/{name}" in CSS
    assert "SIL OPEN FONT LICENSE" in (fonts / "OFL.txt").read_text().upper()


def test_static_files_are_served_with_sane_types():
    client = create_app().test_client()
    assert client.get("/static/fonts/Geist.woff2").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    page = client.get("/").get_data(as_text=True)
    assert "fonts.googleapis.com" not in page and "gstatic" not in page


def test_no_emoji_icons_remain_in_the_ui():
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⚡]")
    for name, text in (("index.html", HTML), ("app.js", JS)):
        # the server still prefixes a few notes with ✔ ℹ ⚠; the script strips them, so allow only those
        found = {m for m in emoji.findall(text) if m not in "✔ℹ⚠"}
        assert not found, f"{name} uses emoji as icons: {sorted(found)}"


def test_every_request_from_the_script_goes_through_apifetch():
    bare = [ln.strip() for ln in JS.splitlines() if re.search(r"(?<![A-Za-z])fetch\(", ln) and "return fetch(url" not in ln]
    assert not bare, f"direct fetch() calls skip the token header: {bare}"


def test_all_user_visible_alerts_are_inline():
    assert "alert(" not in JS.replace("no alert()", "")


# ── capacity matrix reports what will really be embedded ─────────────────────

def test_capacity_matrix_uses_the_encrypted_payload_size():
    from core.crypto import aes

    client = create_app().test_client()
    payload = b"x" * 100
    r = client.post(
        "/api/capacity-matrix",
        data={"file": (io.BytesIO((FIXTURES / "sample.png").read_bytes()), "s.png"),
              "payload": (io.BytesIO(payload), "p.bin"), "depth": "1"},
        content_type="multipart/form-data",
    )
    data = r.get_json()
    assert data["payload_size"] == 100
    assert data["encrypted_size"] == 100 + aes.HEADER_LEN_V3 + aes.TAG_LEN
    lsb = next(row for row in data["rows"] if row["method"] == "lsb")
    assert lsb["utilization_pct"] == pytest.approx(round(data["encrypted_size"] / lsb["capacity_bytes"] * 100, 2))
