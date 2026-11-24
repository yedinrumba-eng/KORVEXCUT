"""The `black` and `freeze` checks of `kcut qa` (spec S1.9a, 001.15 T3): `blackdetect` and
`freezedetect` print their intervals at the `info` level, one ffmpeg for each filter.

The parsers are pure. An interval is `(start_f, end_f)` in frames of the video (`round(t * fps)`).
`classify_intervals` says which ones the EDL explains:

- **black** is expected if 80 % or more of its frames are in a `color` span with luma at most 0.12
  (`0.2126 R + 0.7152 G + 0.0722 B`, normalized) or in a fade zone (the first `fade_in_f` and the
  last `fade_out_f` frames of any span);
- **freeze** is expected if 80 % or more are in a `color`, `screen` or `broll` span; a picture that
  is frozen inside a `cam` is the one that fails.

The stderr is read by the parser and nothing of it is shown (spec 0.8): the log gets it cleaned.
"""

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from kcut import proc
from kcut.edl.model import BrollSpan, ColorSpan, Edl, ScreenSpan, Span
from kcut.qa.report import Check

Kind = Literal["black", "freeze"]
Interval = tuple[int, int]
BLACK_FILTER = "blackdetect=d=0.15:pix_th=0.06"
FREEZE_FILTER = "freezedetect=n=0.002:d=0.6"
MAX_LUMA = 0.12
SHARE = (4, 5)  # 80 %: `covered * 5 >= frames * 4`
_BLACK = re.compile(r"black_start:(\S+)\s+black_end:(\S+)")
_FREEZE = re.compile(r"lavfi\.freezedetect\.freeze_(start|end):\s*(\S+)")
_COLOR = re.compile(r"#([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})")


@dataclass(frozen=True)
class Classified:
    start_f: int
    end_f: int
    expected: bool


def detect_args(ffmpeg: Path, video: Path, filter_graph: str) -> list[str]:
    """The ffmpeg that runs one detection filter over the picture of `video` and throws it away.
    Level info, which is where the filters print (no `-loglevel error`); `video` is a
    `salida/vN.mp4`, never a file of the user."""
    return [
        str(ffmpeg), "-hide_banner", "-nostdin", "-nostats", "-i", str(video),
        "-map", "0:v:0", "-an", "-vf", filter_graph, "-f", "null", "-",
    ]  # fmt: skip


def black_args(ffmpeg: Path, video: Path) -> list[str]:
    return detect_args(ffmpeg, video, BLACK_FILTER)


def freeze_args(ffmpeg: Path, video: Path) -> list[str]:
    return detect_args(ffmpeg, video, FREEZE_FILTER)


def parse_black(stderr: str, fps: int) -> list[Interval]:
    """The `black_start:` / `black_end:` lines as frame intervals; a line whose numbers are not
    finite is left out."""
    found: list[Interval] = []
    for match in _BLACK.finditer(stderr):
        start, end = _frame(match.group(1), fps), _frame(match.group(2), fps)
        if start is not None and end is not None:
            found.append((start, end))
    return found


def parse_freeze(stderr: str, fps: int, total_f: int | None = None) -> list[Interval]:
    """The `freeze_start` / `freeze_end` lines as frame intervals.

    A freeze that lasts to the end of the video has a start and no end (ffmpeg prints it when
    it closes): it ends at `total_f`, the frames of the video, and without `total_f` it is left
    out. An end with no start is ignored."""
    found: list[Interval] = []
    open_at: int | None = None
    for match in _FREEZE.finditer(stderr):
        at = _frame(match.group(2), fps)
        if at is None:
            continue
        if match.group(1) == "start":
            if open_at is not None and total_f is not None:  # the one before never closed
                found.append((open_at, total_f))
            open_at = at
        elif open_at is not None:
            found.append((open_at, at))
            open_at = None
    if open_at is not None and total_f is not None:
        found.append((open_at, total_f))
    return found


def _frame(seconds: str, fps: int) -> int | None:
    """`round(t * fps)` of a time printed as text, or `None` if it is not a finite number."""
    try:
        value = float(seconds)
    except ValueError:
        return None
    if not math.isfinite(value) or not math.isfinite(value * fps):
        return None
    return round(value * fps)


def classify_intervals(intervals: list[Interval], edl: Edl, kind: Kind) -> list[Classified]:
    """Each interval with whether the EDL explains it (see the module). Intervals are cut at the
    video, an empty one counts as one frame, and one that is not in the video at all is not
    expected."""
    zone = _zone(edl, kind)
    result: list[Classified] = []
    for start, end in intervals:
        low, high = max(0, min(start, edl.frames)), max(0, min(end, edl.frames))
        count = max(1, high - low)
        covered = int(zone[low : max(high, low + 1)].sum())
        result.append(Classified(start, end, covered * SHARE[1] >= count * SHARE[0]))
    return result


def _zone(edl: Edl, kind: Kind) -> NDArray[np.bool_]:
    """For each frame of the EDL: is a black (or frozen) picture there explained?"""
    zone = np.zeros(edl.frames, dtype=np.bool_)
    for span in edl.spans:
        low = max(0, span.at_f)
        high = min(edl.frames, span.at_f + span.dur_f)
        if high <= low:
            continue
        if _fully_explains(span, kind):
            zone[low:high] = True
        if kind == "black":
            fade_in = min(max(0, span.fade_in_f), high - low)
            fade_out = min(max(0, span.fade_out_f), high - low)
            zone[low : low + fade_in] = True
            zone[high - fade_out : high] = True
    return zone


def _fully_explains(span: Span, kind: Kind) -> bool:
    if kind == "freeze":
        return isinstance(span, ColorSpan | ScreenSpan | BrollSpan)
    return isinstance(span, ColorSpan) and luma(span.color) <= MAX_LUMA


def luma(color: str) -> float:
    """`0.2126 R + 0.7152 G + 0.0722 B` of `#RRGGBB`, each in 0 to 1; `1.0` (not dark) for a
    text that is not a color."""
    match = _COLOR.fullmatch(color)
    if match is None:
        return 1.0
    r, g, b = (int(part, 16) / 255 for part in match.groups())
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def check_detect(kind: Kind, intervals: list[Interval], edl: Edl) -> Check:
    """The check `black` or `freeze`: it passes if every interval is expected (or there is none)."""
    classified = classify_intervals(intervals, edl, kind)
    listed: list[object] = [
        {"start_f": item.start_f, "end_f": item.end_f, "expected": item.expected}
        for item in classified
    ]
    ok = all(item.expected for item in classified)
    return Check(kind, "pass" if ok else "fail", {"intervals": listed})


def run_detect(
    kind: Kind, video: Path, edl: Edl, total_f: int, log: Path | None, timeout_s: float
) -> Check:
    """Run the filter of `kind` over `video` and judge what it found. `total_f` is the frames of
    the video, which closes a freeze that runs to the end."""
    ffmpeg = proc.tool_path("ffmpeg")
    args = black_args(ffmpeg, video) if kind == "black" else freeze_args(ffmpeg, video)
    stderr = proc.run(args, log=log, timeout_s=timeout_s, capture_stderr=True).stderr
    if kind == "black":
        return check_detect(kind, parse_black(stderr, edl.fps), edl)
    return check_detect(kind, parse_freeze(stderr, edl.fps, total_f), edl)
