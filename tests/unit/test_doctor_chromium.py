"""The `chromium` check of `kcut doctor` launches with the options of the capture (spec S1.6b
row 9):
`launch_options()` is the one place that says how Chromium is started, so the doctor proves that
the browser starts the way the capture will start it: headless, and with its sandbox (001.1).
"""

from types import TracebackType
from typing import Any, Self

import playwright.sync_api as sync_api
import pytest

from kcut.doctor import checks
from kcut.gfx.capture import launch_options


class _Page:
    def set_content(self, html: str, **kwargs: Any) -> None:
        self.html = html


class _Browser:
    def new_page(self) -> _Page:
        return _Page()

    def close(self) -> None:
        self.closed = True


class _Chromium:
    def __init__(self, launched: list[dict[str, Any]]) -> None:
        self._launched = launched

    def launch(self, **kwargs: Any) -> _Browser:
        self._launched.append(kwargs)
        return _Browser()


class _Playwright:
    """A stand-in for `sync_playwright()` that records the keyword arguments of `launch`."""

    def __init__(self, launched: list[dict[str, Any]]) -> None:
        self.chromium = _Chromium(launched)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: _Playwright(seen))
    return seen


def test_doctor_chromium_the_options_are_headless_and_with_the_sandbox() -> None:
    # 001.32: it was `== {"headless": True, "chromium_sandbox": True}`; the options carry the
    # WebRTC policy too (row 36), and headless and the sandbox are asserted as they were
    options = launch_options()
    assert options["headless"] is True and options["chromium_sandbox"] is True
    assert options == {
        "headless": True,
        "chromium_sandbox": True,
        "args": ["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
    }


def test_doctor_chromium_launches_with_launch_options_and_sandbox_true(
    launched: list[dict[str, Any]],
) -> None:
    result = checks.check_chromium()
    assert result.ok is True and result.id == "chromium", result
    assert len(launched) == 1
    assert launched[0]["chromium_sandbox"] is True and launched[0]["headless"] is True
    assert {k: v for k, v in launched[0].items() if k != "timeout"} == launch_options()
    assert isinstance(launched[0]["timeout"], int | float) and launched[0]["timeout"] > 0


def test_doctor_chromium_gfx_popup_webrtc_launches_with_the_webrtc_policy(
    launched: list[dict[str, Any]],
) -> None:
    """001.32 point 5: `kcut doctor` starts Chromium with the same arguments as the capture."""
    assert checks.check_chromium().ok is True
    assert launched[0]["args"] == ["--force-webrtc-ip-handling-policy=disable_non_proxied_udp"]


def test_doctor_chromium_follows_launch_options_if_they_change(
    launched: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The doctor has no copy of the options of its own: change the one place and it follows."""
    import kcut.gfx.capture as capture

    monkeypatch.setattr(capture, "launch_options", lambda: {"headless": True, "args": ["--x"]})
    assert checks.check_chromium().ok is True
    assert launched[0]["args"] == ["--x"] and "chromium_sandbox" not in launched[0]
