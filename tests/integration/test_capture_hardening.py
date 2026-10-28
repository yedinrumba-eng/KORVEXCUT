"""The hardening of Chromium (spec S1.6b row 5, 001.1): it is launched with its sandbox, and the
page cannot ask for anything on the network. A page that tries is stopped by the route before the
request leaves; the local HTTP server of the test counts what reaches it, and it has to be nothing.
A `data:` image, which is inside the page, is painted.
"""

import base64
import contextlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import cv2
import numpy as np
import playwright.sync_api as sync_api
import pytest

from kcut.errors import MissingDependency, ToolError
from kcut.gfx import capture as gfx_capture
from kcut.gfx import capture_net
from kcut.gfx.capture import capture_stills, launch_options
from tests.integration.capture_helpers import counting_server, decode_png, page_with

SIZE = (100, 100)


def _red_square() -> str:
    """A `data:` URI of a PNG of 40 x 40 pixels, opaque red."""
    pixels = np.zeros((40, 40, 4), np.uint8)
    pixels[:, :] = (0, 0, 255, 255)  # BGRA
    done, data = cv2.imencode(".png", pixels)
    assert done
    return "data:image/png;base64," + base64.b64encode(data.tobytes()).decode("ascii")


def test_capture_hardening_launch_receives_the_sandbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A double records the keyword arguments of `launch`: they are `launch_options()`, and that
    has `chromium_sandbox=True`. The double fails to launch, so that nothing else runs."""
    seen: list[dict[str, Any]] = []

    def launch(**kwargs: Any) -> Any:
        seen.append(kwargs)
        raise sync_api.Error("a Chromium that does not start")

    started = SimpleNamespace(chromium=SimpleNamespace(launch=launch), stop=lambda: None)
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: SimpleNamespace(start=lambda: started))
    with pytest.raises(MissingDependency, match="kcut doctor"):
        capture_stills(page_with(""), tmp_path, [0], 30, SIZE, tmp_path / "out", None)
    assert seen == [launch_options()]
    assert seen[0]["chromium_sandbox"] is True and seen[0]["headless"] is True


def test_capture_hardening_playwright_start_that_fails_is_missing_dependency_exit_7(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """001.31 point 11: `sync_playwright().start()` is in the same `try` as `launch`, so a driver
    that does not start is the same MissingDependency (exit 7, `kcut doctor`), not an exit 10."""

    def start() -> Any:
        raise sync_api.Error("the driver of Playwright did not start")

    monkeypatch.setattr(sync_api, "sync_playwright", lambda: SimpleNamespace(start=start))
    with pytest.raises(MissingDependency, match="kcut doctor") as info:
        capture_stills(page_with(""), tmp_path, [0], 30, SIZE, tmp_path / "out", None)
    assert info.value.exit_code == 7
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").glob("*.png"))


@pytest.mark.chromium
@pytest.mark.slow
def test_capture_hardening_chromium_starts_for_real_with_the_sandbox(tmp_path: Path) -> None:
    """On this machine Chromium starts with the sandbox on (it would be a BLOQUEADO if it did not)
    and gives a transparent picture of the size asked for."""
    found = capture_stills(page_with(""), tmp_path, [0], 30, SIZE, tmp_path / "out", None)
    picture = decode_png(found[0])
    assert picture.shape == (100, 100, 4) and int(picture[:, :, 3].max()) == 0


@pytest.mark.chromium
@pytest.mark.slow
def test_capture_hardening_an_image_from_the_network_is_never_asked_for(tmp_path: Path) -> None:
    with counting_server() as (port, hits):
        page = page_with(f'<img src="http://127.0.0.1:{port}/x.png" width="40" height="40">')
        with pytest.raises(ToolError) as info:  # the blocked request is an error of the page
            capture_stills(page, tmp_path, [0], 30, SIZE, tmp_path / "out", None)
        assert hits == []  # and it never reached the server
    assert info.value.exit_code == 4 and "la página de gráficos" in info.value.message_es


@pytest.mark.chromium
@pytest.mark.slow
@pytest.mark.parametrize(
    "body",
    [
        '<link rel="stylesheet" href="http://127.0.0.1:{port}/a.css">',
        '<script src="http://127.0.0.1:{port}/a.js"></script>',
        '<iframe src="http://127.0.0.1:{port}/a.html"></iframe>',
        '<style>@import url("http://127.0.0.1:{port}/a.css");</style>',
        '<div style="width:9px;height:9px;background:url(http://127.0.0.1:{port}/a.png)"></div>',
        '<script>fetch("http://127.0.0.1:{port}/a").catch(() => {});</script>',
        '<script>new Image().src = "http://127.0.0.1:{port}/a.png";</script>',
        '<script>const r = new XMLHttpRequest(); r.open("GET", "http://127.0.0.1:{port}/a"); '
        "r.send();</script>",
        '<img src="https://127.0.0.1:{port}/x.png">',
        '<img src="//127.0.0.1:{port}/x.png">',
    ],
    ids=[
        "css-link", "script-src", "iframe", "css-import", "css-background", "fetch", "image-js",
        "xhr", "https", "protocol-relative",
    ],
)  # fmt: skip
def test_capture_hardening_nothing_else_reaches_the_network_either(
    tmp_path: Path, body: str
) -> None:
    with counting_server() as (port, hits):
        page = page_with(body.replace("{port}", str(port)))  # not `format`: the JS has braces
        with contextlib.suppress(ToolError):  # most make the page say that a resource failed
            capture_stills(page, tmp_path, [0], 30, SIZE, tmp_path / "out", None)
        assert hits == []


@pytest.mark.chromium
@pytest.mark.slow
def test_capture_hardening_an_image_inside_the_page_is_painted(tmp_path: Path) -> None:
    page = page_with(f'<img src="{_red_square()}" style="display:block">')
    found = capture_stills(page, tmp_path, [0], 30, SIZE, tmp_path / "out", None)
    picture = decode_png(found[0])
    assert tuple(picture[10, 10]) == (0, 0, 255, 255)  # opaque red where the data image is
    assert int(picture[80, 80, 3]) == 0  # and transparent where it is not


@pytest.mark.chromium
@pytest.mark.slow
def test_capture_hardening_a_data_image_and_a_network_one_together(tmp_path: Path) -> None:
    """The one that is inside the page is painted even when another one is refused: the route
    lets `data:` through and stops the rest, and what stops is told as a ToolError."""
    with counting_server() as (port, hits):
        body = f'<img src="{_red_square()}"><img src="http://127.0.0.1:{port}/x.png">'
        with pytest.raises(ToolError):
            capture_stills(page_with(body), tmp_path, [0], 30, SIZE, tmp_path / "out", None)
        assert hits == []


def test_capture_hardening_the_module_blocks_with_a_route_made_before_goto() -> None:
    """The way the block is made, which is what the spec says: `context.route("**/*", handler)`
    before `goto`, a handler that continues `file://` and `data:` and aborts the rest."""
    source = Path(gfx_capture.__file__).read_text(encoding="utf-8")
    # 001.32: it was `page.route("**/*"`; the route is on the context now (row 36), so it covers
    # the windows that the page opens, and it still comes before `goto`
    assert source.index('context.route("**/*"') < source.index("page.goto(")
    assert 'page.route("' not in source
    net = Path(capture_net.__file__).read_text(encoding="utf-8")  # 001.33: the handler lives here
    assert "route.abort()" in net and "route.continue_()" in net  # 001.33
    # 001.31: it was `'("file://", "data:")' in source` (any `file://`); now it is the exact URI
    # of the page and `data:`, and the tuple of schemes is gone
    assert '("file://", "data:")' not in source
    assert "page_file.as_uri()" in source and 'startswith("data:")' in net  # 001.33
