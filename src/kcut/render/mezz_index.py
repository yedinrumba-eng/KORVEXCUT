"""What the mezzanines are, as data: a job to make one, an entry that says where one is, the index
of all of a render and a file name that was listed (spec S1.5b, DS12, 001.25, 001.26).

Split from `mezz_files.py` by the 300-line rule (001.26); `mezz_files` names them again, so
`from kcut.render.mezz_files import MezzEntry` still works.
"""

from dataclasses import dataclass, field
from pathlib import Path

from kcut.errors import InternalError


@dataclass(frozen=True)
class MezzJob:
    """One mezzanine to have: frames `[start_f, end_f)` of clip `clip_id`, `w`x`h` pixels, made
    with the ffmpeg chain `chain`. `path` is relative to the project (`.kcut/mezz/<name>.mp4`).
    `need_end_f` is the last frame the EDL reads from it, plus 1, without the margin of the range
    (001.26, point 1): a file whose video reaches it has everything the render needs."""

    clip_id: str
    start_f: int
    end_f: int
    w: int
    h: int
    chain: str
    path: str
    need_end_f: int


@dataclass(frozen=True)
class MezzEntry:
    """A mezzanine that exists: where it is, which frames of the clip it holds (`end_f` is where
    its video really ends, which may be before the end of its name: 001.26) and its size."""

    path: Path
    start_f: int
    end_f: int
    w: int
    h: int


@dataclass
class MezzIndex:
    """The mezzanines of a render, by clip. `built` and `reused` count what `ensure_mezz` did."""

    entries: dict[str, list[MezzEntry]] = field(default_factory=dict)
    built: int = 0
    reused: int = 0

    def locate_run(self, clip_id: str, first: int, last: int) -> tuple[Path, int, tuple[int, int]]:
        """`(file, index of frame first inside it, (w, h))` for the frames `first` to `last` of the
        clip's own clock, which one mezzanine has to hold **whole**. Entries of a clip may
        overlap (a bigger file that was reused, and one made for the rest), so the first one that
        has `first` is not necessarily the one that has `last` (001.25, point 1)."""
        for entry in self.entries.get(clip_id, ()):
            if entry.start_f <= first and last < entry.end_f:
                return entry.path, first - entry.start_f, (entry.w, entry.h)
        raise InternalError(
            f"los frames {first} a {last} de {clip_id} no están juntos en ningún mezzanine del plan"
        )


@dataclass(frozen=True)
class Listed:
    """A file of `.kcut/mezz/` that has the name of a mezzanine, read from the name."""

    name: str
    start_f: int
    end_f: int
    w: int
    h: int
    chain: str
