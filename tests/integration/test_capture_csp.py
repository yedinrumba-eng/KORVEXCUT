"""What the page may ask for, in depth (spec S1.6b round 1, 001.31 point 10; row 28): the route lets
through only the exact URI of the page (`page_file.as_uri()`) and `data:`, so any other `file://`
(UNC included) is aborted, and the page carries a Content-Security-Policy that `page.route` does not
need to see: it stops a WebSocket, which the route never sees.

The route is looked at with a page written by hand (no CSP): a file that exists, asked for as an
image, is not continued. The CSP is looked at with the page that `build_page` makes and a test
runtime that opens a WebSocket against a local server: the server gets nothing. The pages that
kcut makes (rows 3 and 5) keep working: their fonts and images are `data:`.
"""

from pathlib import Path

import cv2
import numpy as np
import playwright.sync_api as sync_api
import pytest

from kcut.errors import ToolError
from kcut.gfx.capture import capture_stills
from kcut.gfx.page import build_page
from tests.integration.capture_helpers import (
    H,
    W,
    counting_server,
    decode_png,
    page_with,
    sample_data,
    with_runtime,
)

pytestmark = [pytest.mark.chromium, pytest.mark.slow]
SIZE = (100, 100)
STUBS = "window.KC = { register() {} }; window.kcutReady = true; window.seek = () => true;"


def _plant_png(folder: Path) -> Path:
    """A PNG that exists, of 40 x 40 opaque red pixels, in `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    pixels = np.zeros((40, 40, 4), np.uint8)
    pixels[:, :] = (0, 0, 255, 255)
    done, data = cv2.imencode(".png", pixels)
    assert done
    path = folder / "x.png"
    path.write_bytes(data.tobytes())
    return path


@pytest.fixture
def continued(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The URL of every request that the route lets go on (`Route.continue_`), as it happens."""
    urls: list[str] = []
    real = sync_api.Route.continue_

    def spy(self: sync_api.Route, *args: object, **kwargs: object) -> None:
        urls.append(self.request.url)
        real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sync_api.Route, "continue_", spy)
    return urls


def test_gfx_csp_a_file_that_exists_and_is_not_the_page_is_not_let_through(
    tmp_path: Path, continued: list[str]
) -> None:
    picture = _plant_png(tmp_path / "otra carpeta")
    page = page_with(f'<img src="{picture.as_uri()}" width="40" height="40">')
    work = tmp_path / "work"
    with pytest.raises(ToolError) as info:  # the request that is stopped is an error of the page
        capture_stills(page, work, [0], 30, SIZE, tmp_path / "out", None)
    assert info.value.exit_code == 4 and "la página de gráficos" in info.value.message_es
    assert (work / "page.html").as_uri() in continued  # the page itself went through
    assert picture.as_uri() not in continued
    assert [url for url in continued if url.startswith("file:")] == [(work / "page.html").as_uri()]


def test_gfx_csp_the_page_in_a_folder_with_spaces_and_accents_is_let_through(
    tmp_path: Path, continued: list[str]
) -> None:
    """The URI that Chromium asks for is the one `as_uri()` gives, `%20` and `%C3%B1` included."""
    work = tmp_path / "proyecto ñandú" / ".kcut" / "gfx"
    found = capture_stills(page_with("<p>hola</p>"), work, [0], 30, SIZE, work / "out", None)
    assert decode_png(found[0]).shape == (100, 100, 4)
    assert (work / "page.html").as_uri() in continued


def test_gfx_csp_a_data_image_is_still_painted(tmp_path: Path) -> None:
    import base64

    pixels = np.zeros((40, 40, 4), np.uint8)
    pixels[:, :] = (0, 0, 255, 255)
    done, data = cv2.imencode(".png", pixels)
    assert done
    uri = "data:image/png;base64," + base64.b64encode(data.tobytes()).decode("ascii")
    page = page_with(f'<img src="{uri}" style="display:block">')
    found = capture_stills(page, tmp_path, [0], 30, SIZE, tmp_path / "out", None)
    assert tuple(decode_png(found[0])[10, 10]) == (0, 0, 255, 255)


def test_gfx_csp_a_websocket_opened_by_the_page_never_reaches_the_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`page.route` does not see WebSockets: what stops this one is the CSP of the page."""
    with counting_server() as (port, hits):
        opening = f'try {{ new WebSocket("ws://127.0.0.1:{port}"); }} catch (e) {{ /* blocked */ }}'
        with_runtime(monkeypatch, STUBS + " " + opening)
        page = build_page(sample_data(), [])
        with pytest.raises(ToolError) as info:  # the refusal is an error of the page (D6)
            capture_stills(page, tmp_path, [0], 30, (W, H), tmp_path / "out", None)
        assert hits == []  # no connection, not even the handshake
    assert info.value.exit_code == 4 and "la página de gráficos" in info.value.message_es


def test_gfx_csp_the_page_of_kcut_is_ready_and_paints_with_the_policy_on(
    tmp_path: Path, continued: list[str]
) -> None:
    """The policy does not stop what the page needs: its script, its style and its fonts."""
    page = build_page(sample_data(), ["kinetic", "title", "label", "captions"])
    found = capture_stills(page, tmp_path, [50, 100], 30, (W, H), tmp_path / "out", None)
    assert sorted(found) == [50, 100]
    assert int(decode_png(found[100])[:, :, 3].max()) > 0  # something is drawn at frame 100
    assert [url for url in continued if url.startswith("http")] == []  # nothing else asked


def test_gfx_page_uri_case_a_capture_with_the_drive_letter_in_small_letters_works(
    tmp_path: Path, continued: list[str]
) -> None:
    """001.32 point 2: the work folder is written with the letter of the drive in small letters
    (`c:`), so `as_uri()` gives `file:///c:/...`, and Chromium asks for `file:///C:/...`. The
    capture is not aborted for that: the page is the same one."""
    drive = tmp_path.drive
    assert len(drive) == 2 and drive[1] == ":", "this test is for a path with a drive letter"
    work = Path(drive.lower() + str(tmp_path)[len(drive) :]) / "work"
    assert str(work)[0].islower()
    found = capture_stills(page_with("<p>hola</p>"), work, [0], 30, SIZE, tmp_path / "out", None)
    assert decode_png(found[0]).shape == (100, 100, 4)
    assert [url.casefold() for url in continued if url.startswith("file:")] == [
        (work / "page.html").as_uri().casefold()
    ]
