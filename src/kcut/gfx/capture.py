"""Capture the graphics page with headless Chromium, one transparent PNG per frame (spec S1.6b;
technique of `piloto/capture.py`).

`Shooter` is one Chromium with the page open: `shoot(f)` puts the page at frame `f` (`window.seek`,
a pure function of the time, with a limit of time: `FRAME_TIMEOUT_S`) and takes the photo
(`Page.captureScreenshot` over CDP, 001.34 point 1), with a transparent background. `capture` keeps
the frames that have something drawn on them; `capture_stills` keeps all, in memory.

The page cannot ask for anything on the network: the route lets through only the page itself and
`data:`, everything else is aborted before it leaves (spec 001.1, 001.31 point 10), the page has a
Content-Security-Policy for what a route does not see, an init script takes WebRTC out of it
(`capture_net`, 001.33 point 4) and Chromium runs with its sandbox (`launch_options`). What the page
says about itself (`pageerror`, `console.error`) is an error of the capture. The caller has already
checked that `work_dir` and `out_dir` are inside `.kcut/`, and `guard` (when it is given) is called
again before each thing that is written in them (001.31 point 2).
"""

import base64
import contextlib
import gc
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self, cast

from kcut.console import Progress
from kcut.errors import MissingDependency, ToolError
from kcut.gfx.capture_index import png_name
from kcut.gfx.capture_net import NO_WEBRTC
from kcut.gfx.capture_net import only_local as _only_local
from kcut.gfx.capture_png import max_alpha, write_png
from kcut.gfx.capture_pw import clean, playwright_error, short
from kcut.gfx.resolve import ResolvedGraphics
from kcut.gfx.seek import FrameTimeout, SeekError, evaluate_seek
from kcut.jsonio import write_text_atomic

if TYPE_CHECKING:  # Playwright is imported where it is used: `kcut doctor` has to start without it
    from playwright.sync_api import Page, Playwright

READY_TIMEOUT_MS = 20_000  # what the page has to load its fonts and its images
FRAME_TIMEOUT_S = 30.0  # the most that the `seek` of one frame may take (001.31, point 4)
MAX_REPORTED = 5  # page errors that a ToolError lists
WEBRTC_POLICY = "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"
Guard = Callable[[], None]  # looks at the folders again; raises a ProjectError if they changed


def launch_options() -> dict[str, object]:
    """The options Chromium is launched with, here and in `kcut doctor` (001.1): headless, with
    its sandbox and with WebRTC that sends no UDP by itself (001.32, point 5), which the CSP of the
    page does not cover. If it does not start with the sandbox, the sandbox is not taken off."""
    return {"headless": True, "chromium_sandbox": True, "args": [WEBRTC_POLICY]}


def active_frames(resolved: ResolvedGraphics) -> list[int]:
    """The frames that may have something drawn: the union of `[start_f, end_f)` of the cues and
    of `[s_f, e_f)` of the subtitle chunks, inside the video, in order."""
    live: set[int] = set()
    for cue in resolved.cues:
        live.update(range(cue.start_f, cue.end_f))
    for chunk in resolved.chunks:
        live.update(range(max(0, chunk.s_f), min(chunk.e_f, resolved.frames)))
    return sorted(live)


def capture(
    page_html: str,
    work_dir: Path,
    frames: Sequence[int],
    fps: int,
    size: tuple[int, int],
    out_dir: Path,
    progress: Progress | None,
    *,
    guard: Guard | None = None,
) -> list[int]:
    """Capture `frames` of `page_html` to `out_dir/{f:06d}.png`, and give back the frames that
    kept their PNG. One whose alpha is 0 everywhere has nothing drawn: it is not written and it is
    not in the list. `page_html` is written to `work_dir/page.html`; `size` is `(W, H)`."""
    kept: list[int] = []
    _check(guard)
    out_dir.mkdir(parents=True, exist_ok=True)
    with Shooter(page_html, work_dir, fps, size, guard=guard) as shooter:
        for done, f in enumerate(frames, start=1):
            png = shooter.shoot(f)
            if max_alpha(png, size) > 0:
                _check(guard)
                write_png(out_dir / png_name(f), png)
                kept.append(f)
            if progress is not None:
                progress.update(done)
        shooter.finish()
    return kept


def capture_stills(
    page_html: str,
    work_dir: Path,
    frames: Sequence[int],
    fps: int,
    size: tuple[int, int],
    out_dir: Path,
    progress: Progress | None,
    *,
    guard: Guard | None = None,
) -> dict[int, bytes]:
    """As `capture`, but every frame is kept, empty ones too, and in memory: `{frame: its PNG}`.
    Nothing that Chromium makes is written (001.33, point 2): `work_dir` gets only the page, and
    the caller makes the stills from the bytes. The caller keeps the count small (`graphics still`
    makes at most 60 frames). `out_dir` is not used any more: it stays so that the call is the one
    it was."""
    found: dict[int, bytes] = {}
    _check(guard)
    with Shooter(page_html, work_dir, fps, size, guard=guard) as shooter:
        for done, f in enumerate(frames, start=1):
            found[f] = shooter.shoot(f)
            if progress is not None:
                progress.update(done)
        shooter.finish()
    return found


def _check(guard: Guard | None) -> None:
    if guard is not None:
        guard()


class Shooter:
    """One Chromium with the graphics page open, as a context manager. `shoot(f)` is the PNG of
    frame `f`, as bytes; it can be asked for in any order and as many times as wanted, and the
    same frame always gives the same picture."""

    def __init__(
        self,
        page_html: str,
        work_dir: Path,
        fps: int,
        size: tuple[int, int],
        *,
        guard: Guard | None = None,
    ) -> None:
        self._html = page_html
        self._work_dir = work_dir
        self._fps = fps
        self._size = size
        self._guard = guard
        self._errors: list[str] = []
        self._playwright: Playwright | None = None
        self._browser: Any = None
        self._page: Page | None = None
        self._cdp: Any = None
        self._playwright_error = playwright_error()

    def __enter__(self) -> Self:
        _check(self._guard)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        page_file = self._work_dir / "page.html"
        _check(self._guard)
        write_text_atomic(page_file, self._html)  # replaces the name: never writes through a link
        try:
            self._start(page_file)
        except BaseException:
            self._stop()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._stop()

    def shoot(self, f: int) -> bytes:
        """The PNG of frame `f` (`window.seek(f / fps)`, at most `FRAME_TIMEOUT_S`, and the
        photo: `Page.captureScreenshot` over CDP with `optimizeForSpeed`, as in S1.6b). A page
        error that came with it is a ToolError, and so is a frame that does not end: Chromium is
        closed by the `with` that this is called in.

        What is not cut (001.34, point 1): the photo has no limit of its own (CDP has none, and
        `page.screenshot` costs 1.88 times more because it cannot ask for the fast PNG). A task
        that the page leaves for after the `seek` and that blocks it needs the JavaScript of kcut
        to leave it, and the rules of `gfx/web/` forbid that (`setTimeout`, `setInterval`,
        `requestAnimationFrame`, `requestIdleCallback`, `MessageChannel`, `postMessage`,
        `Worker`); a watchdog that kills Chromium by pid is the cure if it is ever needed."""
        cdp = self._cdp
        if self._page is None or cdp is None:
            raise ToolError("Shooter se usa dentro de un with")
        try:
            evaluate_seek(cdp, f / self._fps, FRAME_TIMEOUT_S, self._playwright_error)
            shot = cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True})
            png = base64.b64decode(shot["data"])
        except FrameTimeout:
            raise ToolError(
                f"un cuadro de los gráficos tardó más de {FRAME_TIMEOUT_S:g} s en dibujarse; "
                "kcut paró la captura"
            ) from None
        except SeekError as exc:
            raise self._failure(f"Chromium falló en el frame {f}", exc) from None
        except (self._playwright_error, KeyError, ValueError) as exc:
            raise self._failure(f"Chromium falló en el frame {f}", exc) from None
        self.finish()
        return png

    def finish(self) -> None:
        """ToolError if the page reported any error (`pageerror` or `console.error`) so far."""
        if self._errors:
            raise self._failure("la página de gráficos dio errores")

    def _start(self, page_file: Path) -> None:
        width, height = self._size
        failure = self._boot()
        if failure is not None:  # the driver may not start, as Chromium may not (001.31, point 11)
            raise MissingDependency(
                f"Chromium no arrancó ({failure}); corre kcut doctor para ver qué falta"
            )
        context = self._browser.new_context(
            viewport={"width": width, "height": height}, device_scale_factor=1
        )
        # before any page and before the route: no WebRTC in the page or in a window it opens
        # (001.33, point 4), and nothing goes to the network (001.1) but the page and `data:`
        # (001.31); on the context, not on the page, so the route covers the windows too (001.32)
        context.add_init_script(NO_WEBRTC)
        context.route("**/*", _only_local(page_file.as_uri()))
        page = context.new_page()
        page.on("pageerror", lambda error: self._errors.append(str(error)))
        page.on("console", self._on_console)
        self._page = page
        try:
            page.goto(page_file.as_uri())
            page.wait_for_function("window.kcutReady === true", timeout=READY_TIMEOUT_MS)
            self._cdp = page.context.new_cdp_session(page)
            self._cdp.send(
                "Emulation.setDefaultBackgroundColorOverride",
                {"color": {"r": 0, "g": 0, "b": 0, "a": 0}},
            )
        except self._playwright_error as exc:
            raise self._failure("la página de gráficos no quedó lista", exc) from None
        self.finish()

    def _boot(self) -> str | None:
        """Start Playwright and launch Chromium. Why it could not (the first line of the error: a
        driver that is not there is an `OSError`, 001.32), or `None` if it did. A driver that does
        not start leaves a future of Playwright that nobody reads, and asyncio tells it in 47 lines
        of traceback when that future is collected (`Future exception was never retrieved`): the
        `asyncio` logger is kept quiet until it has been (001.33, point 6)."""
        from playwright.sync_api import sync_playwright

        asyncio_log = logging.getLogger("asyncio")
        level = asyncio_log.level
        asyncio_log.setLevel(logging.CRITICAL)
        reason: str | None = None
        try:
            try:
                self._playwright = sync_playwright().start()
                self._browser = self._playwright.chromium.launch(
                    **cast("dict[str, Any]", launch_options())
                )
            except (self._playwright_error, OSError) as exc:
                reason = short(exc)
            if reason is not None:
                gc.collect()  # the future that was not read is collected here, with the log quiet
        finally:
            asyncio_log.setLevel(level)
        return reason

    def _on_console(self, message: Any) -> None:
        if message.type == "error":
            self._errors.append(message.text)

    def _stop(self) -> None:
        with contextlib.suppress(Exception):  # a Chromium that already died has nothing to close
            if self._browser is not None:
                self._browser.close()
        with contextlib.suppress(Exception):
            if self._playwright is not None:
                self._playwright.stop()
        self._browser = self._page = self._cdp = self._playwright = None

    def _failure(self, head: str, exc: Exception | None = None) -> ToolError:
        """A ToolError with the first `MAX_REPORTED` things the page said, each one cut and with
        the numbers masked: it is text of a page that drew a transcript."""
        said = list(self._errors)
        if exc is not None:
            said.append(short(exc))
        shown = "; ".join(clean(text) for text in said[:MAX_REPORTED])
        more = f" (y {len(said) - MAX_REPORTED} más)" if len(said) > MAX_REPORTED else ""
        return ToolError(f"{head}: {shown}{more}" if shown else head)
