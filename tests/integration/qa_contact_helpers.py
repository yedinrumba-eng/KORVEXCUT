"""Pieces for the tests of the masked contact sheet (spec S1.9a rows 18 and 22; 001.39 D19, 001.40,
001.41).

`install_solid_layer` puts a double in place of `gfx.capture.capture_stills`: it records the page
and the frames it was asked for and answers with an opaque magenta layer for each one, so a cell of
the sheet that was built from graphics is magenta and one that came from the video is not.
`sheet_plan` says which frames of the sheet fall in `active_frames` of the graphics of the project,
computed here with `resolve` and no Chromium, as the product computes them. `burn_green` paints
every frame of a video green (the stand-in for the raw subtitles that a finished MP4 has burned in)
and `spy_on_readers` lists the files a `FrameReader` is opened over (001.41, point 2).
"""

import io
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from kcut import proc
from kcut.edl.check import check_edl_file
from kcut.ff.reader import FrameReader
from kcut.gfx import capture as gfx_capture
from kcut.gfx.resolve import resolve
from kcut.project import load_inventory, open_project
from kcut.qa.contact import contact_frames

__all__ = [
    "GREEN",
    "MAGENTA",
    "Spy",
    "burn_green",
    "cell_pixels",
    "install_solid_layer",
    "is_color",
    "mask_pii_off",
    "sheet_plan",
    "spy_on_readers",
]
MAGENTA = (255, 0, 255)  # RGB of the layer that the double gives
GREEN = (0, 215, 0)  # RGB of what `burn_green` paints, as the reader gives it (measured: the
# drawbox of ffmpeg converts with bt601 and the reader with bt709, so 255 comes back as 215)
W, H = 1080, 1920  # the size of the video of the synthetic project
CELL_W, CELL_H = 216, 384


class Spy:
    """What the double of `capture_stills` was asked: one entry per call."""

    def __init__(self) -> None:
        self.pages: list[str] = []
        self.frames: list[list[int]] = []
        self.work_dirs: list[Path] = []


def _magenta_png() -> bytes:
    bgra = np.zeros((H, W, 4), dtype=np.uint8)
    bgra[:, :] = (255, 0, 255, 255)  # BGRA: opaque magenta
    done, encoded = cv2.imencode(".png", bgra)
    assert done
    return bytes(encoded.tobytes())


def install_solid_layer(monkeypatch: pytest.MonkeyPatch) -> Spy:
    """Replace `capture_stills` with a double that records its call and answers with magenta."""
    spy = Spy()
    layer = _magenta_png()

    def fake(
        page_html: str,
        work_dir: Path,
        frames: Any,
        fps: int,
        size: tuple[int, int],
        out_dir: Path,
        progress: Any,
        *,
        on_shot: Any = None,
        guard: Any = None,
    ) -> dict[int, bytes]:
        if guard is not None:
            guard()
        spy.pages.append(page_html)
        spy.frames.append(list(frames))
        spy.work_dirs.append(work_dir)
        assert size == (W, H) and fps == 30
        if on_shot is None:
            return {f: layer for f in frames}
        for f in frames:  # 001.47: each PNG is handed over as it is made and nothing is kept
            on_shot(f, layer)
        return {}

    monkeypatch.setattr(gfx_capture, "capture_stills", fake)
    return spy


def sheet_plan(root: Path) -> tuple[list[int], list[int]]:
    """`(with graphics, without)`: the frames of the sheet that are in `active_frames` of the
    graphics of the project, and the ones that are not."""
    project = open_project(str(root))
    inventory = load_inventory(project)
    checked = check_edl_file(project, inventory, None)
    assert checked.edl is not None
    edl = checked.edl
    live = set(gfx_capture.active_frames(resolve(project, edl, 1, inventory=inventory)))
    sheet = contact_frames(edl.frames, edl.fps)
    return [f for f in sheet if f in live], [f for f in sheet if f not in live]


def cell_pixels(sheet: Path | bytes, k: int) -> NDArray[np.uint8]:
    """The inside of the cell `k` of a sheet (away from its edges, where JPEG blocks of the
    neighbours could reach), as RGB."""
    source = io.BytesIO(sheet) if isinstance(sheet, bytes) else sheet
    picture = np.asarray(Image.open(source).convert("RGB"))
    return np.asarray(picture[40:344, k * CELL_W + 20 : k * CELL_W + CELL_W - 20])


def mask_pii_off(root: Path) -> None:
    """`[privacy] mask_pii = false` in the `kcut.toml` of `root`."""
    path = root / "kcut.toml"
    text = path.read_text(encoding="utf-8")
    assert "mask_pii = true" in text
    path.write_text(text.replace("mask_pii = true", "mask_pii = false"), encoding="utf-8")


def is_color(cell: NDArray[np.uint8], rgb: tuple[int, int, int]) -> bool:
    """True if the cell is (within JPEG noise) one flat `rgb`."""
    mean = cell.reshape(-1, 3).mean(axis=0)
    return bool(np.abs(mean - np.array(rgb)).max() < 40)


def burn_green(video: Path) -> None:
    """`video` with a green picture over every frame, in place: the finished MP4 has the subtitles
    burned in, raw, and whatever it holds must never reach the sheet. The sound is copied."""
    painted = video.with_name("painted.mp4")
    args = [
        str(proc.tool_path("ffmpeg")), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-i", str(video), "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=0x00FF00:t=fill,format=yuv420p",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "12", "-r", "30",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-color_range", "tv", "-c:a", "copy", str(painted),
    ]  # fmt: skip
    proc.run(args, timeout_s=300)
    os.replace(painted, video)


def spy_on_readers(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """The file of every `FrameReader` made from now on (the real reader still runs)."""
    opened: list[Path] = []
    real = FrameReader.__init__

    def init(self: FrameReader, path: Path, *args: Any, **kwargs: Any) -> None:
        opened.append(Path(path))
        real(self, path, *args, **kwargs)

    monkeypatch.setattr(FrameReader, "__init__", init)
    return opened
