"""The route of the capture compares the URL that is asked for with the URL of the page without
telling capitals from small letters (spec S1.6b row 33, 001.32 point 2): on Windows a path does not
tell them apart, and Chromium writes the letter of the drive in capitals and the host of a UNC path
in small letters, whatever way the project root was written. Any other `file://` is still aborted.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from kcut.gfx.capture import _only_local


class _Route:
    """What the handler uses of a Playwright `Route`: the URL, `continue_` and `abort`."""

    def __init__(self, url: str) -> None:
        self.request = SimpleNamespace(url=url)
        self.outcome: str | None = None

    def continue_(self) -> None:
        self.outcome = "continue"

    def abort(self) -> None:
        self.outcome = "abort"


def _outcome(page_uri: str, asked: str) -> str | None:
    route: Any = _Route(asked)
    _only_local(page_uri)(route)
    return route.outcome


@pytest.mark.parametrize(
    ("page_uri", "asked"),
    [
        ("file:///c:/x/page.html", "file:///C:/x/page.html"),
        ("file:///C:/x/page.html", "file:///c:/x/page.html"),
        ("file://DESKTOP-ABC/videos/p/page.html", "file://desktop-abc/videos/p/page.html"),
        ("file:///C:/x/page.html", "file:///C:/x/page.html"),
        ("file:///C:/x/page.html", "data:image/png;base64,AAAA"),
    ],
)
def test_gfx_page_uri_case_the_page_itself_goes_through(page_uri: str, asked: str) -> None:
    assert _outcome(page_uri, asked) == "continue"


@pytest.mark.parametrize(
    "asked",
    [
        "file:///C:/x/otra.html",
        "file:///C:/x/page.html.x",
        "file:///C:/x/page.htm",
        "file:///C:/y/page.html",
        "file://otro-host/videos/p/page.html",
        "http://127.0.0.1:1/page.html",
        "https://example.com/",
    ],
)
def test_gfx_page_uri_case_anything_else_is_aborted(asked: str) -> None:
    assert _outcome("file:///c:/x/page.html", asked) == "abort"
    assert _outcome("file://DESKTOP-ABC/videos/p/page.html", asked) == "abort"
