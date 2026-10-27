"""The index of the captured graphics, `.kcut/build/vN/gfx/index.json` (spec S1.6b, 001.15).

It says which frames of the video have a PNG of graphics, and the hash of the page they were
captured from: with the same hash nothing is captured again. `.kcut/` is not trusted (spec 0.9), so
the index is checked whole when it is read; one that fails any check is treated as if it were not
there, and the graphics are captured again.
"""

import hashlib
import os
import re
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from kcut.errors import ProjectError
from kcut.jsonio import MAX_INDEX_BYTES, read_json
from kcut.paths import lone_file_reason

INDEX_NAME = "index.json"
_HASH = re.compile(r"[0-9A-Fa-f]{64}")
_KEYS = frozenset({"fps", "frames", "hash"})


@dataclass(frozen=True)
class CaptureIndex:
    """What `index.json` says: the fps, the frames that have a PNG (strictly increasing) and the
    sha256 of the page that was captured."""

    fps: int
    frames: tuple[int, ...]
    hash: str


def png_name(f: int) -> str:
    """The file of frame `f` of the video: `000050.png`."""
    return f"{f:06d}.png"


def page_hash(page_html: str) -> str:
    """sha256 of the page: the data (cues, chunks, brand, images), the runtime, the scripts of the
    components, the style and the fonts are all inside it, so any of them changing changes it.

    The bytes are the ones that `write_text_atomic` writes to `page.html`: UTF-8 with `replace`, so
    a lone surrogate in a text of the page (U+D800) is a `?` in both and not an exception
    (001.31, point 6)."""
    return hashlib.sha256(page_html.encode("utf-8", errors="replace")).hexdigest()


def index_document(fps: int, frames: list[int], digest: str) -> dict[str, object]:
    """The JSON that is written to `index.json`."""
    return {"fps": fps, "frames": frames, "hash": digest}


def parse_index(data: object) -> CaptureIndex | None:
    """The index in `data`, or `None` if it does not have the shape: an object with exactly `fps`
    (an integer, no `bool`), `frames` (a list of integers, no `bool`, strictly increasing and not
    negative) and `hash` (64 hexadecimal digits)."""
    if not isinstance(data, dict) or set(data) != _KEYS:
        return None
    fps, frames, digest = data["fps"], data["frames"], data["hash"]
    if not _is_int(fps) or not isinstance(frames, list) or not isinstance(digest, str):
        return None
    if _HASH.fullmatch(digest) is None or not all(_is_int(f) and f >= 0 for f in frames):
        return None
    if any(a >= b for a, b in pairwise(frames)):
        return None
    return CaptureIndex(fps, tuple(frames), digest.lower())


def read_index(path: Path) -> CaptureIndex | None:
    """The index at `path` if it is there and has the shape; `None` if it is not there, is not
    JSON, is too big or has another shape."""
    try:
        return parse_index(read_json(path, MAX_INDEX_BYTES))
    except ProjectError:
        return None


def load_index(folder: Path, fps: int, video_frames: int) -> tuple[CaptureIndex | None, bool]:
    """The index of `folder`, checked for a video of `fps` and `video_frames`: `(index, damaged)`.

    `index` is `None` unless the file is there and: it has the shape (`parse_index`), its `fps` is
    the project's, every frame is in `[0, video_frames)` and every frame has its PNG as a regular
    file in `folder` (not a link, not a folder). `damaged` is true when there was a file and it
    failed, so the caller can say the cache is being rebuilt; it is false when there is none.

    The index and each PNG have to be a regular file with one name (`_is_regular`): a hard link is
    a second name of a file that may be outside the project, and it is not trusted (001.31,
    point 3)."""
    path = folder / INDEX_NAME
    if not os.path.lexists(path):
        return None, False
    if not _is_regular(path):
        return None, True
    index = read_index(path)
    if index is None or index.fps != fps or any(f >= video_frames for f in index.frames):
        return None, True
    if not all(_is_regular(folder / png_name(f)) for f in index.frames):
        return None, True
    return index, False


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_regular(path: Path) -> bool:
    """A regular file with a single link, looked at by its name and not through a link."""
    try:
        return lone_file_reason(os.lstat(path)) is None
    except OSError:
        return False
