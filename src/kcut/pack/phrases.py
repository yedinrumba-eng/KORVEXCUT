"""Phrases: words grouped by the silences measured on the audio (lesson 2).

Whisper stretches a word over the pause that follows it ("con" lasting 1.68 s), so neither the
cuts between phrases nor their edges come from Whisper's timestamps: they come from the energy.
"""

from bisect import bisect_left
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from kcut.analysis.energy import Run, containing_run
from kcut.transcribe.model import Word

CUT_TOLERANCE_MS = 50  # a word that starts this soon after a silence began belongs before it


@dataclass(frozen=True)
class Phrase:
    words: Sequence[Word]
    start_ms: int
    end_ms: int
    pause_before_ms: int | None


def split_phrases(words: Sequence[Word], runs: Sequence[Run], phrase_pause_ms: int) -> list[Phrase]:
    """Cut `words` (in time order) into phrases at every silence of `phrase_pause_ms` or more.

    For each such silence `R` the phrase is cut before the first word with
    `s_ms >= R.start + 50`. Each phrase takes its edges from the energy: it starts where its
    first word starts, unless a silence contains that instant (then where the silence ends), and
    ends where its last word ends, unless a silence contains that instant (then where the
    silence starts). If that leaves `end_ms <= start_ms`, the raw word times are used.
    `pause_before_ms` is the start of the phrase minus the end of the one before it.
    """
    if not words:
        return []
    starts = [word.s_ms for word in words]
    cuts = {
        bisect_left(starts, run[0] + CUT_TOLERANCE_MS)
        for run in runs
        if run[1] - run[0] >= phrase_pause_ms
    }
    bounds = [0, *sorted(c for c in cuts if 0 < c < len(words)), len(words)]
    phrases: list[Phrase] = []
    for first, last in pairwise(bounds):
        group = words[first:last]
        start, end = _edges(group, runs)
        previous = phrases[-1].end_ms if phrases else None
        phrases.append(Phrase(group, start, end, None if previous is None else start - previous))
    return phrases


def _edges(group: Sequence[Word], runs: Sequence[Run]) -> tuple[int, int]:
    raw_start, raw_end = group[0].s_ms, group[-1].e_ms
    start, end = raw_start, raw_end
    opening = containing_run(runs, raw_start)
    if opening is not None:
        start = opening[1]
    closing = _run_holding_end(runs, raw_end)
    if closing is not None:
        end = closing[0]
    return (start, end) if end > start else (raw_start, raw_end)


def _run_holding_end(runs: Sequence[Run], end_ms: int) -> Run | None:
    """The run with `start < end_ms <= end` (an instant that closes inside a silence)."""
    return containing_run(runs, end_ms - 1)  # start <= end_ms - 1 < end  <=>  start < end_ms <= end
