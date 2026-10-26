"""A number masked in one camera is masked in all of them, at that time (spec 001.17, point 2).

Each camera is read alone, so a member that missed the last group of a phone number the master
heard shows the other groups in plain sight in its own rows ("972 808": six digits, no PII for
it). The spans the detector masks, moved to the master's clock, cover those words too.

The length of a word under the spans comes from running totals and one `bisect`, so it costs
O(log spans) whatever the word's length (spec 001.18, point 6): a hostile transcript of long
words over thousands of spans does not walk every pair.
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
    index = _Spans(spans)
    covered: dict[str, set[str]] = {}
    for clip_id, (words, inside, offset) in clips.items():
        found = {
            word.id
            for word in words
            if word.text
            and word.id not in inside
            and index.overlap(word.s_ms + offset, word.e_ms + offset) * 2 >= word.e_ms - word.s_ms
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


class _Spans:
    """Merged, sorted, disjoint spans with the running length of those before each one."""

    def __init__(self, spans: list[tuple[int, int]]) -> None:
        self.starts = [s for s, _ in spans]
        self.ends = [e for _, e in spans]
        self.before = [0]  # before[i]: total length of spans[:i]
        for s, e in spans:
            self.before.append(self.before[-1] + e - s)

    def below(self, t_ms: int) -> int:
        """Milliseconds of the spans that lie before `t_ms`."""
        i = bisect_right(self.starts, t_ms)  # spans[:i] start at or before t_ms
        if i == 0:
            return 0
        return self.before[i - 1] + min(t_ms, self.ends[i - 1]) - self.starts[i - 1]

    def overlap(self, s_ms: int, e_ms: int) -> int:
        """How many milliseconds of `[s_ms, e_ms)` lie inside the spans."""
        return self.below(e_ms) - self.below(s_ms)


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
