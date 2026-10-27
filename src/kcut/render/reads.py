"""Which frames of a file one reader reads in a row (spec S1.5b). Pure.

An ffmpeg process starts at a frame and goes forward. A span that plays 1x, or sped up, or slowed
down reads its frames in order with small steps between them, so one reader serves the whole
stretch: it reads `[first, last]` without a pause and the frames wanted are picked from what it
delivers (a frame twice if the speed is under 1). A jump back, or a big one forward, starts a new
reader.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ReadRun:
    """One reader: it reads the frames `first` to `last` (both included) of a file, and `picks`
    are the frames that go out, in order, each one as many times as it was asked for."""

    first: int
    last: int
    picks: list[int]


def plan_reads(src_frames: list[int], max_gap: int = 8) -> list[ReadRun]:
    """Split `src_frames` (one source frame for each output frame) into runs of a reader each.

    A run continues while the next frame is not before the last one and is at most `max_gap`
    frames after it (the same frame again, `speed < 1`, is a step of 0). Anything else, a jump
    back or a step bigger than `max_gap`, starts the next run. An empty list has no runs.
    """
    runs: list[ReadRun] = []
    picks: list[int] = []
    for frame in src_frames:
        if picks and not 0 <= frame - picks[-1] <= max_gap:
            runs.append(ReadRun(picks[0], picks[-1], picks))
            picks = []
        picks.append(frame)
    if picks:
        runs.append(ReadRun(picks[0], picks[-1], picks))
    return runs
