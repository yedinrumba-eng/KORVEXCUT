"""The page of the graphics that is ready a little late, or never (spec 001.51 point 7 row 32;
001.52 point 2 row 37).

`page.wait_for_function` retries its predicate with an `eval`, which the CSP of the page of kcut
(no `unsafe-eval`) refuses: a page that is not ready at the first look died with `EvalError`, and
the build went on without a contact sheet. A poll with `page.evaluate` has no limit of its own: a
page that blocks its thread kept the capture, and the lock `build-vN`, for ever. The capture waits
for `<html data-kcut-ready>` with `page.wait_for_selector`, whose limit Playwright keeps. The pages
here carry the same CSP as the ones `build_page` makes (`kcut.gfx.page.CSP`).
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

from kcut.errors import ToolError
from kcut.gfx import capture
from kcut.gfx.capture import capture_stills
from kcut.gfx.page import CSP
from tests.integration.capture_helpers import READY_MARK

pytestmark = [pytest.mark.chromium, pytest.mark.slow]
SIZE = (100, 100)
HANG = 'window.addEventListener("load", () => setTimeout(() => { for (;;) {} }, 50));'


def _page(script: str) -> str:
    """A page with the CSP of kcut whose `kcutReady` is decided by `script`."""
    return (
        f'<!doctype html><html><head><meta charset="utf-8">{CSP}</head><body style="margin:0">'
        f"<script>window.kcutReady = false; window.seek = () => true; {script}</script>"
        "</body></html>"
    )


def _chromium_pids() -> set[str]:
    """The pids of the Chromium of Playwright that are alive now (the ones that run from its
    `ms-playwright` folder: the browser of the person who runs the tests is not counted)."""
    if sys.platform == "win32":
        query = (
            "Get-CimInstance Win32_Process | Where-Object "
            "{ $_.ExecutablePath -like '*ms-playwright*' } | ForEach-Object { $_.ProcessId }"
        )
        command = ["powershell", "-NoProfile", "-Command", query]
        shown = subprocess.run(command, capture_output=True, text=True, check=True).stdout
        return set(shown.split())
    command = ["ps", "-A", "-o", "pid=,args="]
    shown = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    return {line.split()[0] for line in shown.splitlines() if "ms-playwright" in line}


def test_capture_ready_late_a_page_that_is_ready_at_300_ms_starts_the_session(
    tmp_path: Path,
) -> None:
    page = _page(f"setTimeout(() => {{ window.kcutReady = true; {READY_MARK} }}, 300);")
    shots = capture_stills(page, tmp_path / "work", [0], 30, SIZE, tmp_path / "out", None)
    assert list(shots) == [0] and shots[0].startswith(b"\x89PNG")


def test_capture_ready_late_a_page_that_is_never_ready_is_the_error_of_today(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(capture, "READY_TIMEOUT_MS", 700)
    with pytest.raises(ToolError) as info:
        capture_stills(_page(""), tmp_path / "work", [0], 30, SIZE, tmp_path / "out", None)
    assert info.value.exit_code == 4
    assert "la página de gráficos no quedó lista" in info.value.message_es
    assert "la página no quedó lista en 700 ms" in info.value.message_es  # 001.52


def test_capture_ready_late_a_page_that_blocks_its_thread_is_exit_4_with_no_chromium_left(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The page blocks its thread (`for (;;) {}`) shortly after the `load`, before it is ready. The
    limit is Playwright's, not the page's: exit 4 at the limit and the Chromium is closed."""
    monkeypatch.setattr(capture, "READY_TIMEOUT_MS", 1500)
    before = _chromium_pids()
    started = time.monotonic()
    with pytest.raises(ToolError) as info:
        capture_stills(_page(HANG), tmp_path / "work", [0], 30, SIZE, tmp_path / "out", None)
    assert time.monotonic() - started < 15  # 001.52
    assert info.value.exit_code == 4
    assert "la página no quedó lista en 1500 ms" in info.value.message_es
    deadline = time.monotonic() + 10  # the browser needs a moment to go away
    while _chromium_pids() - before and time.monotonic() < deadline:
        time.sleep(0.25)
    assert _chromium_pids() - before == set()
