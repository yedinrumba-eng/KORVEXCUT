"""The HTML page the graphics are drawn in (spec S1.6a). Nothing is read from the network: the
fonts, the images, the data and every script go inside the page, because Chromium loads it from a
file with the network blocked (S1.6b).

The page has a Content-Security-Policy (`CSP`, right after the charset), `base.css`, the three
weights of Inter as data URIs, `runtime.js`, the scripts of the components it uses (each one's
`js_files`, in that order) and the data as JSON. The runtime starts when the page has loaded, after
every component has registered itself.
"""

import base64
import json
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from kcut.errors import InternalError
from kcut.gfx.components import page_component

WEB = Path(__file__).resolve().parent / "web"
FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
WEIGHTS = (600, 800, 900)
# What the page may load (001.31, point 10): nothing, but the images and fonts that are inside it
# as `data:`, and its own style and scripts. The block of the network is `context.route` (only the
# page itself and `data:` go through), and it does not see a WebSocket: this policy does. Neither
# one sees WebRTC: `capture.py` removes it with an init script (001.33, point 4).
CSP = (
    '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; '
    "font-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'\">"
)


@cache
def web_text(rel: str) -> str:
    """A file of `gfx/web/` (`runtime.js`, `base.css`, `components/title.js`) as text."""
    return (WEB / rel).read_text(encoding="utf-8")


@cache
def font_css() -> str:
    """`@font-face` for Inter 600, 800 and 900, each font as a woff2 data URI."""
    faces = []
    for weight in WEIGHTS:
        raw = (FONTS / f"inter-latin-{weight}-normal.woff2").read_bytes()
        uri = "data:font/woff2;base64," + base64.b64encode(raw).decode("ascii")
        faces.append(
            f'@font-face{{font-family:Inter;font-weight:{weight};src:url("{uri}") format("woff2")}}'
        )
    return "\n".join(faces)


def json_for_script(data: Mapping[str, object]) -> str:
    """`data` as JSON that is safe inside `<script type="application/json">`: `</` is written
    `<\\/` (so a `</script>` in a text cannot close the tag) and `<!--` is written `<\\u0021--`.
    Both are escapes that JSON reads as the same characters."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return text.replace("</", "<\\/").replace("<!--", "<\\u0021--")


def build_page(data: Mapping[str, object], component_ids: list[str]) -> str:
    """The page for `data` (what `resolve.data_json` gives) with the components `component_ids`.

    `body` is `W x H` with a transparent background. A component id that is not registered is an
    InternalError: `resolve` only lists ones it checked."""
    scripts = [web_text("runtime.js")]
    for component_id in dict.fromkeys(component_ids):
        component = page_component(component_id)
        if component is None:
            raise InternalError(f"build_page: no hay un componente {component_id!r}")
        scripts += [web_text(f"components/{name}") for name in component.js_files]
    w, h = data.get("w"), data.get("h")
    if not isinstance(w, int) or not isinstance(h, int):
        raise InternalError("build_page: los datos no traen w y h")
    size = f"html,body{{width:{w}px;height:{h}px}}"
    parts = [
        '<!doctype html>\n<html>\n<head>\n<meta charset="utf-8">',
        CSP,
        f"<style>\n{font_css()}\n</style>",
        f"<style>\n{web_text('base.css')}\n{size}\n</style>",
        '</head>\n<body>\n<div id="kc-root"></div>',
        f'<script type="application/json" id="kc-data">{json_for_script(data)}</script>',
        *(f"<script>\n{script}\n</script>" for script in scripts),
        "</body>\n</html>\n",
    ]
    return "\n".join(parts)
