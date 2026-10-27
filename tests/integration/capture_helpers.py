"""Helpers of the Chromium tests of the graphics (spec S1.6b): a page with cues of the four base
components and the subtitles, written by hand (no project, no ffmpeg), the PNG of a capture as an
array, and a local HTTP server that counts what is asked of it.
"""

import http.server
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.config.load import parse_config
from kcut.gfx import page as gfx_page
from kcut.gfx.components import COMPONENTS, validate_params
from kcut.gfx.page import build_page

W, H, FPS = 1080, 1920, 30
Bgra = NDArray[np.uint8]


def decode_png(source: Path | bytes) -> Bgra:
    """A PNG (a file or its bytes) as `(H, W, 4)` BGRA, with `cv2.imdecode` (never `imread`)."""
    raw = source if isinstance(source, bytes) else source.read_bytes()
    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert image is not None
    return np.asarray(image)


def _cue(
    cue_id: str, component: str, start: int, end: int, params: dict[str, Any]
) -> dict[str, Any]:
    brand = parse_config("", default_name="x").brand
    checked, issues = validate_params(COMPONENTS[component], params, "params", brand)
    assert issues == [], issues
    return {"id": cue_id, "component": component, "start_f": start, "end_f": end, "params": checked}


def sample_data() -> dict[str, Any]:
    """The `kc-data` of a page with four cues and the subtitles, 345 frames of 1080 x 1920."""
    cfg = parse_config("", default_name="x")
    brand = {
        "accent": cfg.brand.accent,
        "accent2": cfg.brand.accent2,
        "dark": cfg.brand.dark,
        "light": cfg.brand.light,
    }
    style = {
        "y": cfg.captions.y,
        "font_px": cfg.captions.font_px,
        "color": cfg.captions.color,
        "active_color": cfg.captions.active_color or brand["accent2"],
        "stroke_color": cfg.captions.stroke_color or brand["dark"],
    }
    chunks = [
        {
            "s_f": 150,
            "e_f": 185,
            "words": [{"text": "HELLO", "s_f": 150}, {"text": "WORLD", "s_f": 162}],
        },
        {"s_f": 190, "e_f": 230, "words": [{"text": "AGAIN", "s_f": 190}]},
    ]
    kinetic = {"lines": [{"text": "Hola", "at_f": 2, "size": 72, "color": "light"}], "y": 0.45}
    cues = [
        _cue("gancho", "kinetic", 0, 120, kinetic),
        _cue("titulo", "title", 40, 260, {"text": "Higgsfield", "size": 96, "y": 0.6}),
        _cue("pill", "label", 90, 300, {"text": "hecho con kcut", "y": 0.58}),
        {
            "id": "__captions__",
            "component": "captions",
            "start_f": 0,
            "end_f": 345,
            "params": {"style": style, "chunks": chunks},
        },
    ]
    return {
        "fps": FPS, "w": W, "h": H, "frames": 345, "brand": brand, "images": {}, "cues": cues,
    }  # fmt: skip


def sample_page() -> str:
    """The HTML page of `sample_data()`, with the components it uses."""
    data = sample_data()
    return build_page(data, ["kinetic", "title", "label", "captions"])


def with_runtime(monkeypatch: pytest.MonkeyPatch, runtime_js: str) -> None:
    """Make every page that `build_page` builds from now on use `runtime_js` where `runtime.js`
    goes: the "runtime de prueba" of the tests of a frame that does not end and of the CSP
    (001.31, rows 22 and 28). The scripts of the components are the real ones, so a test runtime
    has to give them a `window.KC` with `register`."""
    real = gfx_page.web_text

    def web_text(rel: str) -> str:
        return runtime_js if rel == "runtime.js" else real(rel)

    monkeypatch.setattr(gfx_page, "web_text", web_text)


def page_with(body: str) -> str:
    """A minimal page that is ready at once and has nothing to seek: for what is not the
    graphics themselves (what the page is allowed to ask for)."""
    return (
        '<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">'
        f"{body}<script>window.kcutReady = true; window.seek = () => true;</script></body></html>"
    )


class _Counter(http.server.BaseHTTPRequestHandler):
    hits: list[str]

    def do_GET(self) -> None:
        self.hits.append(self.path)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.end_headers()
        self.wfile.write(b"x")

    def log_message(self, format: str, *args: Any) -> None:  # the name of the base class
        return None


@contextmanager
def counting_server() -> Iterator[tuple[int, list[str]]]:
    """A local HTTP server that answers any GET and records the path of each one: `(port, hits)`."""
    hits: list[str] = []
    handler = type("Handler", (_Counter,), {"hits": hits})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1], hits
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
