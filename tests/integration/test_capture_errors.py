"""What the page says about itself (spec S1.6b): any `pageerror` or `console.error` is a
ToolError (exit 4) with the list of what it said. The list is short (5 at most), each line is cut
and its numbers are masked, because it is text of a page that draws a transcript. A page that is
not ready in time, or that fails after the first frame, is told as a ToolError too.
"""

from pathlib import Path

import pytest

from kcut.errors import ToolError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.capture import Shooter, capture_stills
from tests.integration.capture_helpers import page_with

pytestmark = [pytest.mark.chromium, pytest.mark.slow]
SIZE = (100, 100)


def _stills(page: str, tmp_path: Path, frames: list[int] | None = None) -> None:
    capture_stills(page, tmp_path, frames or [0], 30, SIZE, tmp_path / "out", None)


def test_capture_errors_a_console_error_is_a_tool_error_with_what_it_said(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as info:
        _stills(page_with('<script>console.error("algo falló aquí");</script>'), tmp_path)
    assert info.value.exit_code == 4
    assert info.value.message_es == "la página de gráficos dio errores: algo falló aquí"


def test_capture_errors_a_page_error_is_a_tool_error_with_what_it_said(tmp_path: Path) -> None:
    with pytest.raises(ToolError) as info:
        _stills(page_with('<script>throw new Error("kaboom");</script>'), tmp_path)
    assert "kaboom" in info.value.message_es


def test_capture_errors_a_console_log_or_warning_is_not_an_error(tmp_path: Path) -> None:
    body = '<script>console.log("hola"); console.warn("ojo"); console.info("x");</script>'
    _stills(page_with(body), tmp_path)  # does not raise
    assert (tmp_path / "out" / "000000.png").is_file()


def test_capture_errors_the_list_is_cut_at_5_and_says_how_many_more(tmp_path: Path) -> None:
    body = '<script>for (let i = 0; i < 8; i++) console.error("fallo" + i);</script>'
    with pytest.raises(ToolError) as info:
        _stills(page_with(body), tmp_path)
    message = info.value.message_es
    assert all(f"fallo{i}" in message for i in range(5))
    assert "fallo5" not in message and message.endswith("(y 3 más)")


def test_capture_errors_the_numbers_in_what_the_page_says_are_masked(tmp_path: Path) -> None:
    body = '<script>console.error("llama al 8095551234 ya");</script>'
    with pytest.raises(ToolError) as info:
        _stills(page_with(body), tmp_path)
    assert "8095551234" not in info.value.message_es and "34" in info.value.message_es


def test_capture_errors_a_long_line_is_cut(tmp_path: Path) -> None:
    body = '<script>console.error("x".repeat(5000));</script>'
    with pytest.raises(ToolError) as info:
        _stills(page_with(body), tmp_path)
    assert info.value.message_es.count("x") == 200


def test_capture_errors_a_page_that_is_never_ready_is_a_tool_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gfx_capture, "READY_TIMEOUT_MS", 400)  # 20 s is the real wait
    page = "<!doctype html><html><body><script>window.seek = () => true;</script></body></html>"
    with pytest.raises(ToolError) as info:
        _stills(page, tmp_path)
    assert info.value.exit_code == 4 and "no quedó lista" in info.value.message_es


def test_capture_errors_a_page_that_fails_after_the_first_frame_stops_there(
    tmp_path: Path,
) -> None:
    page = (
        "<!doctype html><html><body><script>window.kcutReady = true; window.seek = (t) => { "
        'if (t >= 1) throw new Error("tarde"); return true; };</script></body></html>'
    )
    with pytest.raises(ToolError) as info:
        _stills(page, tmp_path, [0, 40, 41])  # frame 40 is second 1.33
    assert "tarde" in info.value.message_es
    assert (tmp_path / "out" / "000000.png").is_file()  # what came before is kept
    assert not (tmp_path / "out" / "000041.png").exists()  # and nothing is made after the failure


def test_capture_errors_a_shooter_that_is_not_in_a_with_is_a_tool_error(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="dentro de un with"):
        Shooter(page_with(""), tmp_path, 30, SIZE).shoot(0)


def test_capture_errors_the_page_is_written_where_it_was_asked(tmp_path: Path) -> None:
    work = tmp_path / "work"
    _stills(page_with("<p>hola</p>"), work)
    assert "<p>hola</p>" in (work / "page.html").read_text(encoding="utf-8")
