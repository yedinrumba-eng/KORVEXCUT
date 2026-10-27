"""A frame of the graphics that does not end is cut (spec S1.6b round 1, 001.31 point 4; row 22):
`FRAME_TIMEOUT_S` is the most that the `seek` of a frame may take (what the JavaScript of the page
runs). When it passes, the capture stops with a ToolError that says so, Chromium is closed and the
lock `build-vN` is let go. The cut is in the call itself (`Runtime.evaluate` over CDP with `timeout`
and `awaitPromise`, and a race with `setTimeout` on the side of the page for a promise that never
resolves): no thread calls Playwright, whose synchronous API is for one thread only.

The tests use a page whose `seek` is `while (true) {}` and one whose `seek` returns a promise that
never resolves, with `FRAME_TIMEOUT_S` set to 2 s: both end in a few seconds, not in 30.
"""

import time
from pathlib import Path
from types import SimpleNamespace

import playwright.sync_api as sync_api
import pytest

from kcut.errors import ToolError
from kcut.gfx import capture as gfx_capture
from kcut.gfx import seek as gfx_seek
from kcut.gfx.capture import Shooter, capture_stills
from tests.integration.capture_helpers import decode_png, with_runtime
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.chromium, pytest.mark.slow]
__all__ = ["small", "small_base"]
SIZE = (100, 100)
MESSAGE = "un cuadro de los gráficos tardó más de 2 s en dibujarse; kcut paró la captura"
STUBS = "window.KC = { register() {} }; window.kcutReady = true;"
LOOP = STUBS + " window.seek = () => { while (true) {} };"
PROMISE = STUBS + " window.seek = () => new Promise(() => {});"
HANGS = pytest.mark.parametrize("seek", [LOOP, PROMISE], ids=["loop", "promise"])


def _page(script: str) -> str:
    return f"<!doctype html><html><body><script>{script}</script></body></html>"


@pytest.fixture
def two_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gfx_capture, "FRAME_TIMEOUT_S", 2.0)


def test_frame_timeout_the_number_is_the_one_of_the_spec() -> None:
    assert gfx_capture.FRAME_TIMEOUT_S == 30.0


@HANGS
def test_frame_timeout_a_frame_that_does_not_end_is_a_tool_error_in_seconds_and_chromium_closes(
    tmp_path: Path, two_seconds: None, seek: str
) -> None:
    shooter = Shooter(_page(seek), tmp_path, 30, SIZE)
    started = time.monotonic()
    with pytest.raises(ToolError) as info, shooter:
        shooter.shoot(0)
    elapsed = time.monotonic() - started
    assert info.value.exit_code == 4 and info.value.message_es == MESSAGE
    assert 1.5 < elapsed < 30  # it waited for the limit, and not for the 30 s of the real one
    assert shooter._browser is None and shooter._playwright is None  # Chromium was closed


@HANGS
def test_frame_timeout_through_capture_stills_it_is_the_same_error_and_writes_nothing(
    tmp_path: Path, two_seconds: None, seek: str
) -> None:
    with pytest.raises(ToolError) as info:
        capture_stills(_page(seek), tmp_path, [0, 1], 30, SIZE, tmp_path / "out", None)
    assert info.value.message_es == MESSAGE
    assert not list((tmp_path / "out").glob("*.png"))


def test_frame_timeout_the_message_names_the_limit_that_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gfx_capture, "FRAME_TIMEOUT_S", 1.5)
    with pytest.raises(ToolError) as info:
        capture_stills(_page(PROMISE), tmp_path, [0], 30, SIZE, tmp_path / "out", None)
    assert "tardó más de 1.5 s" in info.value.message_es


@pytest.mark.parametrize(
    "seek",
    [
        "() => { const end = Date.now() + 400; while (Date.now() < end) {} return true; }",
        "() => new Promise((resolve) => setTimeout(() => resolve(true), 300))",
    ],
    ids=["busy-for-a-while", "async-for-a-while"],
)
def test_frame_timeout_a_frame_that_takes_a_while_but_ends_is_not_cut(
    tmp_path: Path, two_seconds: None, seek: str
) -> None:
    script = f"window.kcutReady = true; window.seek = {seek};"
    found = capture_stills(_page(script), tmp_path, [0, 1], 30, SIZE, tmp_path / "out", None)
    assert sorted(found) == [0, 1] and decode_png(found[0]).shape == (100, 100, 4)


def test_frame_timeout_a_seek_that_throws_still_says_what_it_said(tmp_path: Path) -> None:
    script = 'window.kcutReady = true; window.seek = () => { throw new Error("tarde"); };'
    with pytest.raises(ToolError) as info:
        capture_stills(_page(script), tmp_path, [0], 30, SIZE, tmp_path / "out", None)
    assert "tarde" in info.value.message_es and "tardó más de" not in info.value.message_es


def test_frame_timeout_the_cut_is_in_the_call_and_no_thread_calls_playwright() -> None:
    """The cut is `Runtime.evaluate` with `timeout` and `awaitPromise`, and a race with
    `setTimeout` on the side of the page (`gfx/seek.py`); `capture.py` passes `FRAME_TIMEOUT_S`."""
    seek = Path(gfx_seek.__file__).read_text(encoding="utf-8")
    assert "Runtime.evaluate" in seek and "awaitPromise" in seek and '"timeout"' in seek
    assert "setTimeout" in seek  # the race of the side of the page
    capture = Path(gfx_capture.__file__).read_text(encoding="utf-8")
    assert "evaluate_seek(" in capture and "FRAME_TIMEOUT_S" in capture
    for source in (seek, capture):
        assert "threading" not in source and "Thread" not in source and "signal" not in source


@pytest.mark.ffmpeg
@pytest.mark.parametrize("seek", [LOOP, PROMISE], ids=["loop", "promise"])
def test_frame_timeout_graphics_capture_stops_lets_go_of_the_lock_and_the_next_one_works(
    small: Path, kcut_json: Run, seek: str
) -> None:
    import json

    cue = {"id": "x", "component": "label", "start": 3, "end": 8, "params": {"text": "x"}}
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}
    (small / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")
    started = time.monotonic()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(gfx_capture, "FRAME_TIMEOUT_S", 2.0)
        with_runtime(patch, seek)
        code, doc, _ = kcut_json("graphics", "capture", *project_args(small))
    assert code == 4 and doc["error"]["kind"] == "ToolError", doc
    assert doc["error"]["message"] == MESSAGE and time.monotonic() - started < 30
    code, doc, err = kcut_json("graphics", "capture", *project_args(small))  # the real runtime
    assert code == 0 and doc["captured"] is True, (doc, err)  # the lock was let go


# 001.32, point 6 (row 37): the `seek` of the page resolves with no value, so what it gives back
# does not travel over CDP and `returnByValue` has no error to give. The rule of 90 % (R3 of 001.31)
# only sees what is left: the protocol error of an end of the script or of a Chromium that died.


class _Cdp:
    """A CDP session that fails in `send` with an error of Playwright, as Chromium would."""

    def __init__(self, text: str) -> None:
        self.text = text

    def send(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        raise sync_api.Error(self.text)


def _shooter_with(cdp: object) -> Shooter:
    shooter = Shooter(_page(""), Path("unused"), 30, SIZE)
    shooter._page, shooter._cdp = object(), cdp  # type: ignore[assignment]
    return shooter


@pytest.mark.parametrize(
    "returned",
    [
        "window",
        "document",
        "Promise.resolve(window)",
        "(() => { const a = {}; a.a = a; return a; })()",
    ],
    ids=["window", "document", "promise-of-window", "circular"],
)
def test_frame_timeout_label_a_seek_that_returns_something_big_is_captured(
    tmp_path: Path, returned: str
) -> None:
    script = f"window.kcutReady = true; window.seek = () => {returned};"
    found = capture_stills(_page(script), tmp_path, [0, 1], 30, SIZE, tmp_path / "out", None)
    assert sorted(found) == [0, 1] and decode_png(found[1]).shape == (100, 100, 4)


def test_frame_timeout_label_the_script_resolves_with_no_value() -> None:
    """The promise of `seek.py` calls `resolve()` with nothing: what `seek` returns is not read."""
    seek = Path(gfx_seek.__file__).read_text(encoding="utf-8")
    assert "resolve();" in seek and "resolve(v)" not in seek


@pytest.mark.ffmpeg
def test_frame_timeout_label_graphics_capture_with_a_seek_that_returns_window_is_exit_0(
    small: Path, kcut_json: Run
) -> None:
    import json

    cue = {"id": "x", "component": "label", "start": 3, "end": 8, "params": {"text": "x"}}
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}
    (small / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")
    with pytest.MonkeyPatch.context() as patch:
        with_runtime(patch, STUBS + " window.seek = () => window;")
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
    assert code == 0 and doc["ok"] is True and doc["captured"] is True, (doc, err)


def test_frame_timeout_label_an_early_protocol_error_is_a_chromium_failure_not_a_timeout() -> None:
    """An error of the protocol that comes at once, long before 90 % of the limit, is not the end
    of the script: it is `Chromium falló en el frame N`, and it does not say that it was slow."""
    shooter = _shooter_with(_Cdp("Protocol error (Runtime.evaluate): Target closed"))
    with pytest.raises(ToolError) as info:
        shooter.shoot(7)
    assert info.value.exit_code == 4
    assert info.value.message_es.startswith("Chromium falló en el frame 7: ")
    assert "Target closed" in info.value.message_es and "tardó más de" not in info.value.message_es


def test_frame_timeout_label_a_protocol_error_after_90_percent_of_the_limit_is_the_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other side of the rule: V8 ended the script near the limit, and that is the timeout."""
    clock = iter([0.0, 28.0])  # the call began at 0 s and failed at 28 s of a 30 s limit
    fake_time = SimpleNamespace(monotonic=lambda: next(clock))  # not the `time` of everybody
    monkeypatch.setattr(gfx_seek, "time", fake_time)
    shooter = _shooter_with(_Cdp("Protocol error (Runtime.evaluate): Execution was terminated"))
    with pytest.raises(ToolError) as info:
        shooter.shoot(7)
    assert info.value.message_es == (
        "un cuadro de los gráficos tardó más de 30 s en dibujarse; kcut paró la captura"
    )
