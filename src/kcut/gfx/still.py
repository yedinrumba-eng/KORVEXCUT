"""The still of one frame: what Chromium drew, over the frame of the cut (spec S1.6b, 001.40).

Chromium gives, for a frame, a PNG with alpha of the size of the video: the graphics alone. A still
is that layer blended over `render.preview.base_frame`, the frame of the cut made from the proxy.
`kcut graphics still` makes PNG files of it and the contact sheet of `kcut qa` makes the cells of
its sheet from it, so the steps live here, in a module that is not a command: `decode_layer` (the
PNG as pixels, refused if it is not a PNG with alpha of the size of the video), `compose` (the
blend), `png_bytes` and `transparent_png`. Everything is made in memory; nothing is written.

`STILLS_WORK` is the folder of `.kcut/build/vN/gfx/` where the page of the stills goes (the one with
the text masked, the one Claude may see): both users of the stills write it there and nowhere else.
"""

import cv2
import numpy as np
from numpy.typing import NDArray

from kcut.errors import ToolError
from kcut.gfx.overlay import alpha_blend

STILLS_WORK = "stills_work"  # `.kcut/build/vN/gfx/stills_work/`: the page of the stills (masked)
Frame = NDArray[np.uint8]


def decode_layer(shot: bytes, size: tuple[int, int]) -> Frame:
    """The PNG that Chromium made, as `(H, W, 4)` BGRA. `size` is `(W, H)`. Anything that is not a
    PNG with alpha of that size is a ToolError."""
    width, height = size
    try:
        bgra = cv2.imdecode(np.frombuffer(shot, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    except cv2.error:  # an empty buffer is an assertion of OpenCV, not a `None`
        bgra = None
    if bgra is None or bgra.dtype != np.uint8 or bgra.shape != (height, width, 4):
        raise ToolError("Chromium no entregó un PNG con alfa del tamaño del video")
    return np.asarray(bgra)


def compose(base: Frame, layer: Frame) -> Frame:
    """`base` (`(H, W, 3)` BGR) with `layer` (`(H, W, 4)` BGRA, from `decode_layer`) over it."""
    return alpha_blend(base, layer)


def png_bytes(picture: Frame) -> bytes:
    """`picture` (BGR or BGRA) as the bytes of a PNG, encoded in memory (never `cv2.imwrite`)."""
    done, encoded = cv2.imencode(".png", picture)
    if not done:
        raise ToolError("no pude codificar el PNG del still")
    return bytes(encoded.tobytes())


def transparent_png(size: tuple[int, int]) -> bytes:
    """An RGBA PNG of `size` (W, H) with alpha 0 everywhere: no graphics in a still."""
    return png_bytes(np.zeros((size[1], size[0], 4), dtype=np.uint8))
