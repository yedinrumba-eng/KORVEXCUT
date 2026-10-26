"""Crops, easings and the screen-card interpolation (spec S1.5a, formulas of `piloto/compose.py`).

Pure arithmetic on numbers: no image, no ffmpeg. `edl.ranges` uses `upscale_factor` for the W01
warning; S1.5b's `frame_fx` uses the rest to cut each frame.
"""

from collections.abc import Sequence
from itertools import pairwise

from kcut.edl.model import ScreenKey

Crop = tuple[int, int, int, int]  # x, y, w, h in pixels of the source
_BACK_C1 = 1.70158
_BACK_C3 = 2.70158


def cover_box(sw: int, sh: int, W: int, H: int) -> tuple[float, float]:
    """The biggest rectangle with the aspect `W / H` that fits inside a `sw x sh` source."""
    if sw * H >= sh * W:  # the source is wider than the output: the height is the limit
        return sh * W / H, float(sh)
    return float(sw), sw * H / W


def cam_crop(
    sw: int, sh: int, W: int, H: int, zoom: float, cx: float, cy: float, anchor: str
) -> Crop:
    """`(x, y, w, h)` of the part of the source a camera shot shows.

    The size is `cover_box / zoom`. `x` centers on `cx * sw` and stays inside `[0, sw - w]`. `y` is
    0 for `top`, `sh - h` for `bottom`, and for `center` centers on `cy * sh`, also inside.
    """
    box_w, box_h = cover_box(sw, sh, W, H)
    w = min(sw, max(1, round(box_w / zoom)))
    h = min(sh, max(1, round(box_h / zoom)))
    x = round(min(max(cx * sw - w / 2, 0), sw - w))
    if anchor == "top":
        y = 0
    elif anchor == "bottom":
        y = sh - h
    else:
        y = round(min(max(cy * sh - h / 2, 0), sh - h))
    return x, y, w, h


def broll_crop(sw: int, sh: int, W: int, H: int, push_k: float, cx: float, cy: float) -> Crop:
    """Like `cam_crop` centered vertically with `zoom = push_k`, the zoom a b-roll shot has at
    frame `k`: it grows from 1 to `1 + push` over the span."""
    return cam_crop(sw, sh, W, H, push_k, cx, cy, "center")


def ease_in_out_cubic(x: float) -> float:
    """0 to 1 with a slow start and end; `x` is held inside `[0, 1]`."""
    x = min(max(x, 0.0), 1.0)
    return 4 * x**3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def back_out(x: float) -> float:
    """0 to 1 that overshoots a little and settles; `x` is held inside `[0, 1]`."""
    x = min(max(x, 0.0), 1.0)
    return 1 + _BACK_C3 * (x - 1) ** 3 + _BACK_C1 * (x - 1) ** 2


def screen_state(
    keys: Sequence[ScreenKey], rel_f: float
) -> tuple[tuple[float, float, float], tuple[float, float]]:
    """`(crop, card)` of a screen insert at the frame `rel_f` of its span: `crop = (cx, cy, cw)`
    and `card = (w, h)`, interpolated with `ease_in_out_cubic` between the two keys that hold
    `rel_f`; before the first key the first one holds, after the last the last one stays."""
    if rel_f <= keys[0].at_f:
        return keys[0].crop, _floats(keys[0].card)
    for before, after in pairwise(keys):
        if rel_f <= after.at_f:
            u = ease_in_out_cubic((rel_f - before.at_f) / (after.at_f - before.at_f))
            return _lerp3(before.crop, after.crop, u), _lerp2(
                _floats(before.card), _floats(after.card), u
            )
    return keys[-1].crop, _floats(keys[-1].card)


def upscale_factor(zoom_max: float, sw: int, sh: int, W: int, H: int) -> float:
    """How much the source is stretched to fill the output at its biggest zoom:
    `W * zoom_max / cover_box(...)[0]`. Above 1 the picture is enlarged (W01 warns past 1.10).
    A mezzanine is never smaller than the resolution that avoids scaling, so it depends only on
    the source."""
    return W * zoom_max / cover_box(sw, sh, W, H)[0]


def _floats(pair: tuple[int, int]) -> tuple[float, float]:
    return float(pair[0]), float(pair[1])


def _lerp3(
    a: tuple[float, float, float], b: tuple[float, float, float], u: float
) -> tuple[float, float, float]:
    return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u


def _lerp2(a: tuple[float, float], b: tuple[float, float], u: float) -> tuple[float, float]:
    return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
