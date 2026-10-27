"""The graphics layer over the picture (spec S1.6b, lesson 7): the PNG that Chromium made for a
frame, with its alpha, blended over the frame the render has just made.

The PNGs come from `.kcut/`, which is not trusted (spec 0.9): one that is missing, that is not a
PNG of the size of the video or that does not decode is a `ProjectError` that says how to make
them again, never an `InternalError`. The render reads each PNG minutes after the index was
validated, so each one is looked at again right before it is read (001.32, point 8): one that is no
longer a regular file with a single name (a hard link to something outside the project was put in
its place) is refused, and its content does not get into the video.
"""

import os
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from kcut.errors import ProjectError
from kcut.gfx.capture_index import png_name, read_index
from kcut.jsonio import read_capped
from kcut.paths import lone_file_reason

Frame = NDArray[np.uint8]
MAX_PNG_BYTES = 64 * 1024 * 1024  # a PNG of graphics is far smaller: this is only a ceiling
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_IHDR_END = 24  # signature (8) + chunk length (4) + "IHDR" (4) + width (4) + height (4)
DAMAGED = "el gráfico {f} de la caché está dañado; corre kcut graphics capture --force"
DAMAGED_INDEX = (
    "el índice de los gráficos de la caché está dañado; corre kcut graphics capture --force"
)
CHANGED = (
    "el PNG del frame {f} de la capa de gráficos cambió durante el render; "
    "corre kcut graphics capture --force"
)


def alpha_blend(base: Frame, bgra: Frame) -> Frame:
    """`base` (`(H, W, 3)` BGR) with `bgra` (`(H, W, 4)`, straight alpha) over it:
    `out = (base * (255 - a) + rgb * a + 127) // 255`, in integers of 16 bits (the largest
    value, 255 * 255 + 127, fits). Alpha 0 gives `base`, alpha 255 gives the color of `bgra`."""
    alpha = bgra[:, :, 3:4].astype(np.uint16)
    mixed = base.astype(np.uint16) * (255 - alpha) + bgra[:, :, :3].astype(np.uint16) * alpha + 127
    return np.asarray((mixed // 255).astype(np.uint8))


class OverlaySource:
    """The graphics of a video: `blend(base, out_f)` puts the PNG of frame `out_f` over `base`
    if the index of `index_path` has it, and gives `base` back as it is if it does not. The PNGs
    are in the folder of the index and are `W x H`."""

    def __init__(self, index_path: Path, W: int, H: int) -> None:
        index = read_index(index_path)
        if index is None:
            raise ProjectError(DAMAGED_INDEX)
        self._folder = index_path.parent
        self._frames = frozenset(index.frames)
        self._w, self._h = W, H

    def blend(self, base_bgr: Frame, out_f: int) -> Frame:
        """`base_bgr` with the graphics of frame `out_f` over it (`alpha_blend`)."""
        if out_f not in self._frames:
            return base_bgr
        return alpha_blend(base_bgr, self._decode(out_f))

    def _decode(self, f: int) -> Frame:
        """The PNG of frame `f` as `(H, W, 4)` BGRA, decoded from its bytes (never `cv2.imread`:
        it fails on a path with letters outside ASCII, 001.15 T8). Its header is looked at first,
        so a PNG that says it is huge is not decoded. Before it is read, the name is looked at
        (`lone_file_reason` of `os.lstat`, so a link is not followed): a PNG that is not a regular
        file with one name any more is `CHANGED`; one that is gone is `DAMAGED`."""
        path = self._folder / png_name(f)
        try:
            reason = lone_file_reason(os.lstat(path))
        except OSError:
            raise ProjectError(DAMAGED.format(f=f)) from None
        if reason is not None:
            raise ProjectError(CHANGED.format(f=f))
        try:
            raw = read_capped(path, MAX_PNG_BYTES)
        except (ProjectError, OSError):
            raise ProjectError(DAMAGED.format(f=f)) from None
        if raw[:8] != _PNG_SIGNATURE or raw[12:16] != b"IHDR" or len(raw) < _IHDR_END:
            raise ProjectError(DAMAGED.format(f=f))
        size = (int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big"))
        if size != (self._w, self._h):
            raise ProjectError(DAMAGED.format(f=f))
        decoded = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if decoded is None or decoded.dtype != np.uint8 or decoded.shape != (self._h, self._w, 4):
            raise ProjectError(DAMAGED.format(f=f))
        return np.asarray(decoded)
