"""Which words of the transcript stay in the cut, and where they fall in the output (spec S1.5a,
lesson 4: Whisper's timestamps lie, a word that starts early or is stretched past a cut is still
the word of that clip). Pure; integers only, in the units of spec 0.6.

With `A = in_f * 1000`, `B = out_f * 1000`, `S = s_ms * fps` and `E = e_ms * fps` (all in
`1 / (1000 * fps)` seconds), a word belongs to a voice clip when:
(a) `A + 80 * fps < E <= B` (it ends inside, by more than 80 ms), or
(b) `A <= S < B - 50 * fps` and `E > B` (it starts inside and Whisper stretched it past the cut).
"""

from bisect import bisect_left
from collections.abc import Mapping
from dataclasses import dataclass

from kcut.edl.model import Edl, VoiceClip
from kcut.timebase import ms_to_f_ceil, rdiv
from kcut.transcribe.model import Word

END_GRACE_MS = 80  # (a): a word must end this much after the start of the clip
START_GRACE_MS = 50  # (b): a stretched word must start this much before the end of the clip
MAX_WORD_SHOWN_MS = 900  # a word is not shown for longer than this
MIN_WORD_SHOWN_MS = 120  # nor for less (a subtitle that flashes cannot be read)


@dataclass(frozen=True)
class KeptWord:
    """A word of the transcript that the cut keeps. `clip_index` is its voice clip's index in
    `edl.clips`; `out_s_f` and `out_e_f` are the output frames it is shown in; `text` is the
    corrected text, as raw as the transcript has it; `s_ms` and `e_ms` are the transcript's."""

    id: str
    text: str
    clip_index: int
    out_s_f: int
    out_e_f: int
    src: str
    s_ms: int
    e_ms: int


def map_words(edl: Edl, transcripts: Mapping[str, list[Word]], fps: int) -> list[KeptWord]:
    """The kept words of every voice clip, ordered by `out_s_f`.

    `transcripts` is the corrected words of each clip id (corrections are applied before this);
    a word with no text is dropped. A word that belongs to several clips stays with the one it
    overlaps most (the first on a tie)."""
    chosen: dict[tuple[str, int], tuple[int, int, VoiceClip]] = {}  # (src, word) -> its clip
    ordered = {src: _by_start(words) for src, words in transcripts.items()}
    for index, clip in enumerate(edl.clips):
        if not isinstance(clip, VoiceClip) or clip.src not in ordered or clip.dur_f <= 0:
            continue
        words, starts, ends = ordered[clip.src]
        a, b = clip.in_f * 1000, clip.out_f * 1000
        first = bisect_left(ends, a // fps + 1)  # words that end before the clip begins: none
        last = bisect_left(starts, -(-b // fps))  # words that start at or after the end: none
        for position in range(first, last):
            word = words[position]
            overlap = _overlap(word, a, b, fps)
            if overlap is None:
                continue
            key = (clip.src, position)
            if key not in chosen or overlap > chosen[key][0]:
                chosen[key] = (overlap, index, clip)
    owned = sorted(chosen.items(), key=lambda item: (item[1][1], item[0][1]))  # clip, then word
    kept = [
        _placed(ordered[src][0][position], index, clip, fps)
        for (src, position), (_, index, clip) in owned
    ]
    kept.sort(key=lambda word: word.out_s_f)  # stable: same frame keeps clip and transcript order
    return kept


def _by_start(words: list[Word]) -> tuple[list[Word], list[int], list[int]]:
    """The words with text, ordered by start, with their starts and the running maximum of their
    ends (so the words that end before a moment can be skipped with a bisect)."""
    kept = sorted((w for w in words if w.text), key=lambda w: (w.s_ms, w.i))
    ends: list[int] = []
    top = 0
    for word in kept:
        top = max(top, word.e_ms)
        ends.append(top)
    return kept, [w.s_ms for w in kept], ends


def _overlap(word: Word, a: int, b: int, fps: int) -> int | None:
    """How much of the word is inside `[a, b)` if it belongs to the clip, else `None`."""
    s, e = word.s_ms * fps, word.e_ms * fps
    inside = a + END_GRACE_MS * fps < e <= b  # (a)
    stretched = a <= s < b - START_GRACE_MS * fps and e > b  # (b)
    if not (inside or stretched):
        return None
    return min(e, b) - max(s, a)


def _placed(word: Word, index: int, clip: VoiceClip, fps: int) -> KeptWord:
    a, b = clip.in_f * 1000, clip.out_f * 1000
    s0 = max(word.s_ms * fps, a)
    e0 = min(word.e_ms * fps, b, s0 + MAX_WORD_SHOWN_MS * fps)
    limit = clip.at_f + clip.dur_f
    out_s = clip.at_f + rdiv(s0 - a, 1000)
    floor = out_s + ms_to_f_ceil(MIN_WORD_SHOWN_MS, fps)
    out_e = min(max(floor, clip.at_f + rdiv(e0 - a, 1000)), limit)
    if out_e <= out_s:  # at least one frame, and inside the clip
        out_e = min(out_s + 1, limit)
        if out_e <= out_s:
            out_s = out_e - 1
    return KeptWord(word.id, word.text, index, out_s, out_e, clip.src, word.s_ms, word.e_ms)
