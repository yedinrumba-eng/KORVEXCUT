"""Doubles for the unit tests of the contact sheet of `kcut qa` (spec S1.9a rows 18, 22 and 26;
001.39 D19, 001.40, 001.41), with no ffmpeg and no Chromium.

`resolve` is the real one over a phone number said in the transcript (`fake_kept`), the proxy is a
gray frame (`Proxy`, in place of `base_frame`) and Chromium is a double (`Chromium`, in place of
`capture_stills`) that records the page and the frames it is asked for and answers a layer.
"""

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from kcut.gfx import capture as gfx_capture
from kcut.qa import contact_gfx
from kcut.qa.contact import contact_frames
from tests.unit.gfx_resolve_fakes import word

__all__ = ["CELL", "RAW", "SHEET", "SHOWN", "WORDS", "Chromium", "H", "Proxy", "W", "install"]
W, H = 1080, 1920
CELL = (216, 384)
RAW = ("972", "808", "3211")
WORDS = [  # a phone number said between output frames 112 and 140: the sheet has the frame 120
    word(0, "Llama", 100, 110),
    word(1, "972", 112, 120),
    word(2, "808", 122, 130),
    word(3, "3211", 132, 140),
]
SHOWN = {"a1:w0001": "***", "a1:w0002": "***", "a1:w0003": "**11"}
SHEET = contact_frames(345, 30)  # 0, 60, 120, 180, 240, 300


def _png(bgra: tuple[int, int, int, int]) -> bytes:
    pixels = np.zeros((H, W, 4), dtype=np.uint8)
    pixels[:, :] = bgra
    done, data = cv2.imencode(".png", pixels)
    assert done
    return bytes(data.tobytes())


class Chromium:
    """Stands in for `capture_stills`: it records the page and the frames, and answers `layer`."""

    def __init__(self, layer: bytes, fail: Exception | None = None) -> None:
        self.layer = layer
        self.fail = fail
        self.pages: list[str] = []
        self.frames: list[list[int]] = []

    def __call__(
        self,
        page_html: str,
        work_dir: Path,
        frames: Any,
        fps: int,
        size: tuple[int, int],
        out_dir: Path,
        progress: Any,
        *,
        guard: Any = None,
    ) -> dict[int, bytes]:
        if guard is not None:
            guard()
        self.pages.append(page_html)
        self.frames.append(list(frames))
        if self.fail is not None:
            raise self.fail
        return {f: self.layer for f in frames}


class Proxy:
    """Stands in for `base_frame`: a flat gray frame, and a count of the frames it was asked for."""

    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.asked: list[int] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.asked.append(int(args[3]))
        if self.fail is not None:
            raise self.fail
        return np.full((H, W, 3), 100, dtype=np.uint8)


def install(
    monkeypatch: pytest.MonkeyPatch,
    layer: tuple[int, int, int, int] = (255, 0, 255, 255),
    *,
    chromium: Exception | None = None,
    proxy: Exception | None = None,
) -> tuple[Chromium, Proxy]:
    """Put the doubles in place of Chromium and of the proxy; `layer` is BGRA."""
    shooter, base = Chromium(_png(layer), chromium), Proxy(proxy)
    monkeypatch.setattr(gfx_capture, "capture_stills", shooter)
    monkeypatch.setattr(contact_gfx, "base_frame", base)
    monkeypatch.setattr(contact_gfx, "fx_context", lambda project, edl: None)
    return shooter, base
