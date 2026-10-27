"""Shared pieces of the `frame_fx` unit tests: the context (108x192, 9:16) and the spans."""

import numpy as np
from numpy.typing import NDArray

from kcut.config.model import BrandSection
from kcut.edl.model import BrollSpan, CamSpan, ColorSpan, ScreenKey, ScreenSpan
from kcut.render.frame_fx import FxContext
from kcut.render.screen_card import make_background

W, H, FPS = 108, 192, 30
BRAND = BrandSection("#E5FF1F", "#2FA8FF", "#0B0B0E", "#FFFFFF")
Frame = NDArray[np.uint8]


def _ctx(w: int = W, h: int = H) -> FxContext:
    bg = make_background(w, h, BRAND.dark, BRAND.accent)
    return FxContext(w, h, FPS, bg, "#0B0B0E", "#E5FF1F")


def _square_source(
    side: int = 54, w: int = 216, h: int = 384, at: tuple[int, int] | None = None
) -> Frame:
    """A black source with a white square of `side` px centered (or at `at`, its top-left); the
    centered one sits on even coordinates, so that scaling by 1/2 does not split a pixel."""
    src = np.zeros((h, w, 3), np.uint8)
    x, y = at if at is not None else (((w - side) // 4) * 2, ((h - side) // 4) * 2)
    src[y : y + side, x : x + side] = 255
    return src


def _white(frame: Frame) -> int:
    return int((frame[..., 0] > 127).sum())


def _cam(n: int = 11, **fields: float | str) -> CamSpan:
    return CamSpan(at_f=0, dur_f=n, src="a1", **fields)  # type: ignore[arg-type]


def _broll(n: int = 11, **fields: float) -> BrollSpan:
    return BrollSpan(at_f=0, dur_f=n, src="a1", src_f=0, **fields)


def _color(n: int = 30, color: str = "#0B0B0E", **fields: int | str) -> ColorSpan:
    return ColorSpan(at_f=0, dur_f=n, color=color, **fields)  # type: ignore[arg-type]


def _screen(n: int = 60, **fields: object) -> ScreenSpan:
    keys = (
        ScreenKey(0, (0.5, 0.5, 1.0), (80, 40)),
        ScreenKey(30, (0.7, 0.4, 0.3), (60, 80)),
    )
    return ScreenSpan(at_f=0, dur_f=n, src="b1", src_f=0, keys=keys, **fields)  # type: ignore[arg-type]
