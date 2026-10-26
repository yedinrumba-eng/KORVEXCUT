"""A number masked in one camera is masked in all of them, at that time (spec 001.17, point 2).

Each camera is read alone, so a member that missed the last group of a phone number the master
heard shows the other groups in plain sight in its own rows ("972 808": six digits, no PII for
it). The spans the detector masks, moved to the master's clock, cover those words too.
"""

from bisect import bisect_right
from collections.abc import Collection, Mapping, Sequence

from kcut.ingest.inventory_model import SyncInfo
from kcut.pack.pii import mask_pii_spans
from kcut.transcribe.model import Transcript, Word


def covered_ids(
    clips: Mapping[str, tuple[Sequence[Word], Collection[str], int]],
) -> dict[str, set[str]]:
    """For each clip, the ids of its words that sit inside a number another camera masked.

    `clips` maps a clip id to `(raw words, ids inside a masked span, offset_ms)`; the offset moves
    the clip to the master's clock. A word is covered when at least half of it lies inside the
    spans of the other cameras (the same half that makes a candidate in the vote). Words already
    inside a span of their own clip are not repeated here.
    """
    spans = _merge(
        [
            (run[0].s_ms + offset, run[-1].e_ms + offset)
            for words, inside, offset in clips.values()
            for run in _runs(words, inside)
        ]
    )
    starts = [s for s, _ in spans]
    covered: dict[str, set[str]] = {}
    for clip_id, (words, inside, offset) in clips.items():
        found = {
            word.id
            for word in words
            if word.text
            and word.id not in inside
            and _overlap(word.s_ms + offset, word.e_ms + offset, spans, starts) * 2
            >= word.e_ms - word.s_ms
        }
        if found:
            covered[clip_id] = found
    return covered


def _runs(words: Sequence[Word], inside: Collection[str]) -> list[list[Word]]:
    """Neighbouring words that are inside a masked span, as lists (deleted words do not cut)."""
    runs: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if not word.text:
            continue
        if word.id in inside:
            current.append(word)
        elif current:
            runs.append(current)
            current = []
    if current:
        runs.append(current)
    return runs


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _overlap(s_ms: int, e_ms: int, spans: list[tuple[int, int]], starts: list[int]) -> int:
    """How many milliseconds of `[s_ms, e_ms)` lie inside the (merged, sorted) spans."""
    total = 0
    i = max(0, bisect_right(starts, s_ms) - 1)
    while i < len(spans) and spans[i][0] < e_ms:
        total += max(0, min(e_ms, spans[i][1]) - max(s_ms, spans[i][0]))
        i += 1
    return total


def covered_by_sync(
    transcripts: Mapping[str, Transcript], sync: SyncInfo, fillers: Sequence[str]
) -> dict[str, set[str]]:
    """`covered_ids` for the master and the members of the sync block that have a transcript."""
    offsets = {m.id: m.offset_ms for m in sync.members}
    if sync.master is not None:
        offsets[sync.master] = 0
    return covered_ids(
        {
            clip_id: (t.words, mask_pii_spans(t.words, fillers)[2], offsets[clip_id])
            for clip_id, t in transcripts.items()
            if clip_id in offsets
        }
    )
