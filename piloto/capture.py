"""Pilot (throwaway): render the graphics layer to a transparent PNG sequence via headless Chromium.

usage: capture.py build_dir frames [logo_path|-] [only_frame]
"""
import base64
import json
import mimetypes
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

build = Path(sys.argv[1]).resolve()
frames = int(sys.argv[2])
logo = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "-" else None
only = [int(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else None
gfx = build / "gfx"
html = (gfx / "overlay.html").read_text(encoding="utf-8")
logo_uri = "null"
if logo:
    mime = mimetypes.guess_type(logo)[0] or "image/png"
    logo_uri = json.dumps(f"data:{mime};base64," + base64.b64encode(Path(logo).read_bytes()).decode())
html = (html.replace("/*@CUES@*/null", (build / "cues.json").read_text(encoding="utf-8"))
            .replace("/*@CAPS@*/null", (build / "captions.json").read_text(encoding="utf-8"))
            .replace("/*@PALM@*/null", (build / "palm.json").read_text(encoding="utf-8"))
            .replace("/*@LOGO@*/null", logo_uri))
built = gfx / "overlay_built.html"
built.write_text(html, encoding="utf-8")
out = build / ("gfx_still" if only is not None else "gfx_frames")
out.mkdir(exist_ok=True)
t0 = time.perf_counter()
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(built.as_uri())
    page.wait_for_function("window.ready === true", timeout=20000)
    cdp = page.context.new_cdp_session(page)
    cdp.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
    ks = only if only is not None else range(frames)
    for k in ks:
        page.evaluate(f"window.seek({k / 30})")
        shot = cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
        (out / f"{k:05d}.png").write_bytes(base64.b64decode(shot["data"]))
    b.close()
    if errors:
        print("PAGE ERRORS:", errors)
        sys.exit(1)
print(f"captured {len(ks)} frames in {time.perf_counter() - t0:.1f}s -> {out}")
