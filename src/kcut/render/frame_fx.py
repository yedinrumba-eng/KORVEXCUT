"""The picture of one output frame, from the frame of the source it comes from (spec S1.5b, 001.15).

One function for every use: the render (`compose`) and the previews of the graphics and the
storyboard (`render/preview.py`, S1.6b) call `span_frame`, so a still looks like the frame the
video will have. It cuts and scales (camera and b-roll), builds the card of a screen insert, fills
a color span and applies the fades. Pure: arrays in, arrays out.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from kcut.config.model import BrandSection
from kcut.edl.model import BrollSpan, CamSpan, ColorSpan, Edl, ScreenSpan, Span
from kcut.render.geometry import broll_crop, cam_crop
from kcut.render.looks import look_chain
from kcut.render.screen_card import bgr_of, screen_frame

Frame = NDArray[np.uint8]
_SHARPEN_SIGMA = 2.0


@dataclass(frozen=True, eq=False)
class FxContext:
    """What every frame of a render shares: the output size, the fps, the background of the screen
    inserts (made once with `screen_card.make_background`) and the brand colors it was made of."""

    W: int
    H: int
    fps: int
    bg: Frame
    dark: str
    accent: str


def look_for(edl: Edl, span: Span, brand: BrandSection) -> str:
    """The chain of the look that the reader of `span` applies. A color span has none (its `look`
    is ignored: W05). Any other uses its own look or, if it has none, the one of the EDL. In a
    screen insert the chain goes to the source of the card; the background never gets a look."""
    if isinstance(span, ColorSpan):
        return ""
    return look_chain(span.look if span.look is not None else edl.look, brand)


def span_frame(src: Frame | None, span: Span, i: int, ctx: FxContext) -> Frame:
    """Frame `i` (from 0) of `span` as `(H, W, 3)` BGR. `src` is the frame of the source, of any
    size (the mezzanine or the proxy: the cut is computed from `src.shape`); `None` only for a
    color span."""
    if isinstance(span, ColorSpan):
        frame = np.empty((ctx.H, ctx.W, 3), np.uint8)
        frame[:] = np.array(bgr_of(span.color), np.uint8)
        return _fade(frame, span, i)
    if src is None:
        raise ValueError("a span that reads a source needs its frame")
    if isinstance(span, ScreenSpan):
        return _fade(screen_frame(src, i, ctx.fps, span, ctx.bg, ctx.accent, ctx.dark), span, i)
    if isinstance(span, CamSpan):
        zoom = span.zoom * (1 + span.push * i / max(1, span.dur_f - 1))
        sh, sw = src.shape[:2]
        box = cam_crop(sw, sh, ctx.W, ctx.H, zoom, span.cx, span.cy, span.anchor)
        return _fade(_scaled(src, box, ctx), span, i)
    zoom = 1 + span.push * i / max(1, span.dur_f - 1)
    sh, sw = src.shape[:2]
    picture = _scaled(src, broll_crop(sw, sh, ctx.W, ctx.H, zoom, span.cx, span.cy), ctx)
    return _fade(_sharpen_and_dim(picture, span), span, i)


def _scaled(src: Frame, box: tuple[int, int, int, int], ctx: FxContext) -> Frame:
    """The crop `(x, y, w, h)` of `src` scaled to the output: `INTER_AREA` going down (it
    averages, no shimmer), `INTER_CUBIC` going up."""
    x, y, w, h = box
    mode = cv2.INTER_AREA if w * h >= ctx.W * ctx.H else cv2.INTER_CUBIC
    return np.asarray(cv2.resize(src[y : y + h, x : x + w], (ctx.W, ctx.H), interpolation=mode))


def _sharpen_and_dim(picture: Frame, span: BrollSpan) -> Frame:
    """`picture * (1 + s) - blur(picture, sigma 2) * s`, then `* dim`, kept between 0 and 255
    (as `ferrari_frame` of the pilot). A b-roll with neither is not touched."""
    if span.sharpen == 0 and span.dim == 1.0:
        return picture
    work = picture.astype(np.float32)
    if span.sharpen:
        blur = cv2.GaussianBlur(work, (0, 0), _SHARPEN_SIGMA)
        work = work * (1 + span.sharpen) - blur * span.sharpen
    return _to_bytes(work * span.dim)


def _fade(frame: Frame, span: Span, i: int) -> Frame:
    """The fade in (the first `fade_in_f` frames: `(i + 1) / (fade_in_f + 1)`) and the fade out
    (the last `fade_out_f`: `(n - i) / (fade_out_f + 1)`), both to and from black."""
    n = span.dur_f
    gain = 1.0
    if i < span.fade_in_f:
        gain *= (i + 1) / (span.fade_in_f + 1)
    if span.fade_out_f and i >= n - span.fade_out_f:
        gain *= (n - i) / (span.fade_out_f + 1)
    return frame if gain == 1.0 else _to_bytes(frame.astype(np.float32) * gain)


def _to_bytes(values: NDArray[np.float32]) -> Frame:
    return np.asarray(np.rint(values.clip(0, 255)).astype(np.uint8))
