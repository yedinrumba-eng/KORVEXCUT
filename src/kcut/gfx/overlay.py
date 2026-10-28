"""The graphics layer over the picture (spec S1.6b, lesson 7): the PNG that Chromium made for a
frame, with its alpha, blended over the frame the render has just made.

The PNGs come from `.kcut/`, which is not trusted (spec 0.9): one that is missing, that is not a
PNG of the size of the video or that does not decode is a `ProjectError` that says how to make
them again, never an `InternalError`. The render reads each PNG minutes after the index was
validated, so each one is looked at again right before it is read (001.32, point 8): one that is no
longer a regular file with a single name (a hard link to something outside the project was put in
its place) is refused, and its content does not get into the video. That look follows a junction in
the folder, so the folders are looked at too, with the guard that the capture uses (`build/vN` and
`gfx/`, 001.33 point 5): the whole `guard()` runs once, when the source is made, and what it saw is
kept as the identity of each folder (`os.lstat`: device and inode, and not a link or a reparse
point). Before each PNG only those identities are compared, with an `lstat` each, which costs
microseconds where the whole guard cost 1.6 ms a frame (001.35, point 6): a folder that is not the
one that was seen is a ProjectError, and the whole guard says why when it can.
"""

import os
import stat
from collections.abc import Callable, Sequence
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
FOLDER_CHANGED = (
    "una carpeta de la caché de los gráficos cambió durante el render; corre kcut render otra vez"
)

Identity = tuple[int, int]


def folder_identity(path: Path) -> Identity | None:
    """`(st_dev, st_ino)` of the folder `path` itself (`os.lstat`: a link is not followed), or
    `None` if it is not there or is a link or a reparse point (a junction on Windows). One `lstat`:
    this is what is compared before each PNG (001.35, point 6)."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    reparse = getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
        return None
    return (info.st_dev, info.st_ino)


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
    are in the folder of the index and are `W x H`.

    `guard` (the render gives it the one of `build/vN` and `gfx/`) is the whole check of the
    folders. It runs once here, and `watch` (the render gives `.kcut`, `.kcut/build`, `build/vN` and
    `gfx/`) are the folders whose identity is then kept: before each PNG is looked at they are
    compared with an `lstat` each (`folder_identity`), and one that is not the folder that was seen
    is a ProjectError, and nothing of what it leads to is read. Without `watch` the whole `guard`
    runs before each PNG, as it did (001.33)."""

    def __init__(
        self,
        index_path: Path,
        W: int,
        H: int,
        *,
        guard: Callable[[], None] | None = None,
        watch: Sequence[Path] = (),
    ) -> None:
        index = read_index(index_path)
        if index is None:
            raise ProjectError(DAMAGED_INDEX)
        self._guard = guard
        self._watch = tuple(watch)
        self._identities: list[Identity] = []
        if guard is not None:
            guard()  # the whole check, once; what it saw is what is kept
            for folder in self._watch:
                seen = folder_identity(folder)
                if seen is None:
                    raise ProjectError(FOLDER_CHANGED)
                self._identities.append(seen)
        self._folder = index_path.parent
        self._frames = frozenset(index.frames)
        self._w, self._h = W, H

    def blend(self, base_bgr: Frame, out_f: int) -> Frame:
        """`base_bgr` with the graphics of frame `out_f` over it (`alpha_blend`)."""
        if out_f not in self._frames:
            return base_bgr
        return alpha_blend(base_bgr, self._decode(out_f))

    def _folders_unchanged(self) -> None:
        """ProjectError unless each folder of `watch` is still the one that `guard` saw when the
        source was made (an `lstat` each). The whole `guard` is the one that says why, if the folder
        became a link or leaves `.kcut/`; if it lets it pass (a real folder that is another one),
        the message is `FOLDER_CHANGED`."""
        if self._guard is None:
            return
        if not self._watch:
            self._guard()
            return
        for folder, seen in zip(self._watch, self._identities, strict=True):
            if folder_identity(folder) != seen:
                self._guard()
                raise ProjectError(FOLDER_CHANGED)

    def _decode(self, f: int) -> Frame:
        """The PNG of frame `f` as `(H, W, 4)` BGRA, decoded from its bytes (never `cv2.imread`:
        it fails on a path with letters outside ASCII, 001.15 T8). Its header is looked at first,
        so a PNG that says it is huge is not decoded. Before it is read, the folders are looked at
        (`_folders_unchanged`) and then the name (`lone_file_reason` of `os.lstat`, so a link is not
        followed): a PNG that is not a regular file with one name any more is `CHANGED`; one that
        is gone is `DAMAGED`."""
        path = self._folder / png_name(f)
        self._folders_unchanged()
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
