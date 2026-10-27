"""A `Shooter` with no Chromium, for the tests of what `capture` and `graphics still` do with the
folders and the disk (spec S1.6b round 1, 001.31 rows 20, 21, 23 and 24).

It is the real `Shooter` (its `__enter__` writes `page.html`, `capture` and `capture_stills` write
the PNGs, the guards run where they run in the product) with `_start`, `_stop` and `shoot` replaced:
`shoot(f)` gives a PNG of the size of the video with one pixel that is not transparent, so every
frame is kept. Hooks run at the moments a test needs to change the folders under a capture.
"""

from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
import pytest

from kcut.errors import ToolError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.capture import Shooter

__all__ = ["Hooks", "install_fake_shooter"]


class Hooks:
    """What a test wants to happen, and a record of what happened. `on_init` runs when the shooter
    is made (after `capture` made its folder, before `__enter__` writes `page.html`); `on_png`
    runs after each PNG that is written with `capture`'s own `write_png`, with the count so far."""

    def __init__(
        self,
        on_init: Callable[[], None] | None = None,
        on_png: Callable[[int], None] | None = None,
    ) -> None:
        self.on_init = on_init
        self.on_png = on_png
        self.started = 0
        self.shot: list[int] = []


def _png(size: tuple[int, int]) -> bytes:
    """A PNG of `size` (W, H), transparent but for one pixel."""
    width, height = size
    pixels = np.zeros((height, width, 4), np.uint8)
    pixels[0, 0] = (255, 255, 255, 255)
    done, data = cv2.imencode(".png", pixels)
    if not done:
        raise ToolError("the test could not encode a PNG")
    return bytes(data.tobytes())


def install_fake_shooter(monkeypatch: pytest.MonkeyPatch, hooks: Hooks | None = None) -> Hooks:
    """Put the Chromium-less shooter in place of `gfx.capture.Shooter` and, if `hooks.on_png` is
    given, wrap `write_png` so that it runs after each PNG of the capture."""
    seen = hooks or Hooks()

    class FakeShooter(Shooter):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            if seen.on_init is not None:
                seen.on_init()

        def _start(self, page_file: Path) -> None:
            seen.started += 1

        def _stop(self) -> None:
            return None

        def shoot(self, f: int) -> bytes:
            self.finish()
            seen.shot.append(f)
            return _png(self._size)

    real_write = gfx_capture.write_png
    written: list[Path] = []

    def write_png(path: Path, data: bytes) -> None:
        real_write(path, data)
        written.append(path)
        if seen.on_png is not None:
            seen.on_png(len(written))

    monkeypatch.setattr(gfx_capture, "Shooter", FakeShooter)
    monkeypatch.setattr(gfx_capture, "write_png", write_png)
    return seen
