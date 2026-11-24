"""The contact sheet `qa/vN/contact.jpg` (spec S1.9a, 001.15): a frame every 2 seconds of the video.

Each frame is 216x384 (a 9:16 video) or 384x216 (16:9), in 13 columns, with its time (`mm:ss.s`)
and its frame number written under it with Pillow (never `drawtext`). The frames come from one
`FrameReader` over `salida/vN.mp4` with `pre_filters="fps=1/2:round=up"`: `n = (frames + 2 * fps
- 1) // (2 * fps)` of them, and the one at place `k` is the frame `2 * k * fps` of the video.
Measured with ffmpeg 8.1.1: without `round=up`, `fps=1/2` gives the frames 29, 89, 149... and not
always `n` of them. The picture is a JPEG of quality 85.

Where the pictures come from (001.39 D19, 001.41): the finished video has the subtitles burned in
raw, and Claude reads the sheet. With `privacy.mask_pii = false` all of them are read from the
video (`contact_jpeg`). With it on, none is: `qa/contact_gfx.py` makes every cell from the proxy,
with the masked page of the graphics over the ones that have graphics, and `cells_jpeg` puts them
on the sheet, labelled as these are.
"""

import io
from collections.abc import Iterable
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image

from kcut.ff.reader import FrameReader
from kcut.timebase import fmt_tc
from kcut.viz.grid import SheetBuilder

COLUMNS = 13
JPEG_QUALITY = 85
STEP_S = 2  # seconds between two frames of the sheet
_VERTICAL = (216, 384)
_HORIZONTAL = (384, 216)
PRE_FILTERS = "fps=1/2:round=up"


def contact_count(frames: int, fps: int) -> int:
    """How many frames the sheet has: `(frames + 2 * fps - 1) // (2 * fps)`."""
    step = STEP_S * fps
    return (frames + step - 1) // step


def contact_frames(frames: int, fps: int) -> list[int]:
    """The frame of the video that each place of the sheet shows: `0, 2*fps, 4*fps...`."""
    return [k * STEP_S * fps for k in range(contact_count(frames, fps))]


def contact_label(k: int, fps: int) -> str:
    """`mm:ss.s fN` for the place `k`, with `N = 2 * k * fps`."""
    frame = k * STEP_S * fps
    return f"{fmt_tc(frame, fps)} f{frame}"


def cell_size(width: int, height: int) -> tuple[int, int]:
    """216x384 for a video taller than wide, 384x216 for the rest."""
    return _VERTICAL if height > width else _HORIZONTAL


def contact_jpeg(
    video: Path, frames: int, fps: int, size: tuple[int, int], log: Path | None
) -> bytes:
    """The sheet of `video` as the bytes of a JPEG. `frames` is how many it has and `size` its
    `(width, height)`, which the reader needs to cut the raw frames it receives. Every picture is
    a frame of the video: only for a project that does not mask (001.41)."""
    count = contact_count(frames, fps)
    cell = cell_size(*size)
    with FrameReader(video, 0, count, fps, size, pre_filters=PRE_FILTERS, log=log) as reader:
        return cells_jpeg((cell_of(frame, cell) for frame in reader), frames, fps, size)


def cells_jpeg(cells: Iterable[Image.Image], frames: int, fps: int, size: tuple[int, int]) -> bytes:
    """The sheet of the pictures in `cells` as the bytes of a JPEG: the place `k` gets the `k`-th
    one, labelled `contact_label(k, fps)`. `frames` and `size` (`(width, height)`) of the video say
    how many places there are and how big. `cells` is read one at a time, so the caller can make
    each one when it is asked for."""
    builder = SheetBuilder(contact_count(frames, fps), cell_size(*size), COLUMNS)
    for k, picture in enumerate(cells):
        builder.add(picture, contact_label(k, fps))
    out = io.BytesIO()
    builder.image().save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def cell_of(frame: NDArray[np.uint8], cell: tuple[int, int]) -> Image.Image:
    """A BGR frame as a Pillow picture that fits `cell` (reduced, never enlarged)."""
    picture = Image.fromarray(np.ascontiguousarray(frame[:, :, ::-1]), "RGB")
    scale = min(cell[0] / picture.width, cell[1] / picture.height, 1.0)
    if scale < 1.0:
        size = (max(1, round(picture.width * scale)), max(1, round(picture.height * scale)))
        picture = picture.resize(size, Image.Resampling.LANCZOS)
    return picture
