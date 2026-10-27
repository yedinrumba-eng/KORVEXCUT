"""The screen insert: a card with a crop of a screen recording, on a dark background with a glow of
the brand color (spec S1.5b; technique of `piloto/compose.py::screen_frame`).

The card comes in with a small overshoot, has rounded corners, an accent border and a soft shadow.
The shadow is blurred only around the card, so a frame costs what the card costs, not the whole
picture. Every function works on BGR `uint8` frames.
"""

from functools import lru_cache

import cv2
import numpy as np
from numpy.typing import NDArray

from kcut.edl.model import ScreenSpan
from kcut.render.geometry import back_out, screen_state

Frame = NDArray[np.uint8]
_GLOW_AT = (0.5, 0.47)  # where the glow of the background is centered, as fractions of W and H
_GLOW_SIGMA = 0.32
_GLOW_GAIN = 0.16
_ENTER_S = 0.32  # seconds the card takes to come in
_FADE_S = 0.18  # seconds it takes to become opaque
_MIN_SCALE = 0.72
_BORDER_PX = 4
_SHADOW_DY = 24
_SHADOW_SIGMA = 28
_SHADOW_ALPHA = 0.65


def bgr_of(color: str) -> tuple[int, int, int]:
    """`(b, g, r)` of a `#RRGGBB`."""
    value = color.lstrip("#")
    return int(value[4:6], 16), int(value[2:4], 16), int(value[0:2], 16)


def make_background(W: int, H: int, dark: str, accent: str) -> Frame:
    """The `dark` color with a radial glow of `accent` at (0.5, 0.47): sigma 0.32, strength 0.16."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    base = np.empty((H, W, 3), np.float32)
    base[:] = np.array(bgr_of(dark), np.float32)
    d = np.sqrt(((xx - W * _GLOW_AT[0]) / W) ** 2 + ((yy - H * _GLOW_AT[1]) / H) ** 2)
    glow = np.exp(-((d / _GLOW_SIGMA) ** 2))[..., None] * np.array(bgr_of(accent), np.float32)
    return np.asarray((base + glow * _GLOW_GAIN).clip(0, 255).astype(np.uint8))


def screen_frame(
    src: Frame,
    rel_f: int,
    fps: int,
    span: ScreenSpan,
    bg: Frame,
    accent: str,
    dark: str | None = None,
) -> Frame:
    """The frame `rel_f` of a screen insert: `src` (a frame of the recording) cropped and shown on
    a card over `bg`. The card is interpolated between the keys of `span`; its crop is `cw`
    of the width of `src` and as tall as the card needs, filled with `dark` (by default the
    corner of `bg`, which is that color) where it leaves the picture. It comes in over
    `_ENTER_S` seconds, centered at `(W / 2, card_y * H)`."""
    height, width = bg.shape[:2]
    (cx, cy, cw), (card_w, card_h) = screen_state(span.keys, rel_f)
    kw, kh = max(2, round(card_w)), max(2, round(card_h))
    fill = bgr_of(dark) if dark is not None else tuple(int(v) for v in bg[0, 0])
    card = _crop_card(src, cx, cy, cw, kw, kh, fill, height)
    rel_s = rel_f / fps
    scale = _MIN_SCALE + (1 - _MIN_SCALE) * back_out(rel_s / _ENTER_S)
    alpha = min(1.0, rel_s / _FADE_S)
    kw2, kh2 = max(2, int(kw * scale)), max(2, int(kh * scale))
    small: Frame = np.asarray(
        cv2.resize(card, (kw2, kh2), interpolation=cv2.INTER_AREA), dtype=np.uint8
    )
    r = min(max(6, int(28 * scale)), kw2 // 2, kh2 // 2)
    x, y = width // 2 - kw2 // 2, int(height * span.card_y) - kh2 // 2
    out = bg.astype(np.float32)
    _shadow(out, x, y, _mask(kw2, kh2, r), alpha)
    _border_and_card(out, x, y, small, r, alpha, bgr_of(accent))
    return np.asarray(np.rint(out.clip(0, 255)).astype(np.uint8))


def _crop_card(
    src: Frame,
    cx: float,
    cy: float,
    cw: float,
    kw: int,
    kh: int,
    fill: tuple[int, ...],
    max_pad: int,
) -> Frame:
    """The part of `src` the card shows, scaled to `kw`x`kh`: `cw` is the width as a fraction of
    the source, the height is the one that keeps the card's proportion, and where it leaves the
    source (above or below) it is `fill`.

    The `fill` above and below the source is never more than `max_pad` rows (the height of the
    output frame): a tall and thin card would otherwise ask for a picture of thousands of rows.
    What the crop has beyond that is `fill` anyway, so the card gets its rows from the part that
    is made, in the place they belong, and the rest of the card is `fill` (001.25, point 6)."""
    sh, sw = src.shape[:2]
    cw_px = cw * sw
    ch_px = cw_px * kh / kw
    x0 = min(max(cx * sw - cw_px / 2, 0), sw - cw_px)
    y0 = cy * sh - ch_px / 2
    pad = min(int(max(0, -y0, y0 + ch_px - sh)) + 2, max_pad)
    padded = cv2.copyMakeBorder(src, pad, pad, 0, 0, cv2.BORDER_CONSTANT, value=fill)
    wanted_top, wanted_bottom = y0 + pad, y0 + pad + ch_px  # rows of `padded` the card wants
    top, bottom = max(wanted_top, 0.0), min(wanted_bottom, float(sh + 2 * pad))
    first, left = int(top), int(x0)
    crop = padded[first : max(first + 1, int(bottom)), left : max(left + 1, int(x0 + cw_px))]
    mode = cv2.INTER_AREA if cw_px > kw else cv2.INTER_CUBIC
    if (top, bottom) == (wanted_top, wanted_bottom):
        return np.asarray(cv2.resize(crop, (kw, kh), interpolation=mode))
    row0 = min(kh - 1, round((top - wanted_top) * kh / ch_px))  # where the part goes in the card
    rows = max(1, min(kh, kh - round((wanted_bottom - bottom) * kh / ch_px)) - row0)
    card = np.empty((kh, kw, 3), np.uint8)
    card[:] = fill
    card[row0 : row0 + rows] = cv2.resize(crop, (kw, rows), interpolation=mode)
    return card


@lru_cache(maxsize=16)
def _mask(w: int, h: int, r: int) -> NDArray[np.float32]:
    """A white rounded rectangle on black, anti-aliased, as floats from 0 to 1 (read only)."""
    m = np.zeros((h, w), np.uint8)
    cv2.rectangle(m, (r, 0), (w - r, h), 255, -1)
    cv2.rectangle(m, (0, r), (w, h - r), 255, -1)
    for cx, cy in ((r, r), (w - r, r), (r, h - r), (w - r, h - r)):
        cv2.circle(m, (cx, cy), r, 255, -1, lineType=cv2.LINE_AA)
    out = (m / np.float32(255)).astype(np.float32)
    out.flags.writeable = False
    return out


def _shadow(
    out: NDArray[np.float32], x: int, y: int, mask: NDArray[np.float32], alpha: float
) -> None:
    """Darken `out` with the card's shadow: its mask moved down and blurred. Only the square
    around the card (as far as the blur reaches) is touched."""
    h, w = mask.shape
    reach = 3 * _SHADOW_SIGMA
    canvas = np.zeros((h + 2 * reach + _SHADOW_DY, w + 2 * reach), np.float32)
    canvas[reach + _SHADOW_DY : reach + _SHADOW_DY + h, reach : reach + w] = mask
    blurred = cv2.GaussianBlur(canvas, (0, 0), _SHADOW_SIGMA)
    window = _window(out, x - reach, y - reach, canvas.shape[1], canvas.shape[0])
    if window is not None:
        region, (u0, v0, u1, v1) = window
        region *= (1 - _SHADOW_ALPHA * alpha * blurred[v0:v1, u0:u1])[..., None]


def _border_and_card(
    out: NDArray[np.float32],
    x: int,
    y: int,
    card: Frame,
    r: int,
    alpha: float,
    accent: tuple[int, int, int],
) -> None:
    """Paint the accent border (a bigger rounded rectangle behind the card) and then the card."""
    h, w = card.shape[:2]
    bp = _BORDER_PX
    window = _window(out, x - bp, y - bp, w + 2 * bp, h + 2 * bp)
    if window is None:
        return
    region, (u0, v0, u1, v1) = window
    border = _mask(w + 2 * bp, h + 2 * bp, r + bp)[v0:v1, u0:u1, None] * alpha
    region[:] = region * (1 - border) + np.array(accent, np.float32) * border
    inner = np.zeros((h + 2 * bp, w + 2 * bp), np.float32)
    inner[bp : bp + h, bp : bp + w] = _mask(w, h, r) * alpha
    picture = np.zeros((h + 2 * bp, w + 2 * bp, 3), np.float32)
    picture[bp : bp + h, bp : bp + w] = card
    keep = inner[v0:v1, u0:u1, None]
    region[:] = region * (1 - keep) + picture[v0:v1, u0:u1] * keep


def _window(
    out: NDArray[np.float32], x: int, y: int, w: int, h: int
) -> tuple[NDArray[np.float32], tuple[int, int, int, int]] | None:
    """The part of `out` inside the rectangle `(x, y, w, h)` (a view), and where that part sits in
    the rectangle as `(u0, v0, u1, v1)`; None if the rectangle is all outside."""
    height, width = out.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, width), min(y + h, height)
    if x0 >= x1 or y0 >= y1:
        return None
    return out[y0:y1, x0:x1], (x0 - x, y0 - y, x1 - x, y1 - y)
