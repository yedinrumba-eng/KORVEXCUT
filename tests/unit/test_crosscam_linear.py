"""`crosscam.covered_ids` costs O(n log n), not O(words x spans) (spec 001.18, point 6).

The overlap of a word with the masked spans comes from running totals and `bisect`: a hostile
transcript of 8 000 words of 30 s over 2 000 spans must not walk 16 million pairs.
"""

import random
import time

from kcut.pack.crosscam import covered_ids
from kcut.transcribe.model import Word


def _word(clip: str, i: int, s_ms: int, e_ms: int) -> Word:
    return Word(f"{clip}:w{i:05d}", i, "x", s_ms, e_ms, 0.9)


def _brute(
    clips: dict[str, tuple[list[Word], set[str], int]],
) -> dict[str, set[str]]:
    """The definition, word by word and span by span: at least half of the word is under a span
    of another camera's number (merged and moved to the master's clock)."""
    spans: list[tuple[int, int]] = []
    for words, inside, offset in clips.values():
        run: list[Word] = []
        for word in words:
            if word.text and word.id in inside:
                run.append(word)
            elif word.text and run:
                spans.append((run[0].s_ms + offset, run[-1].e_ms + offset))
                run = []
        if run:
            spans.append((run[0].s_ms + offset, run[-1].e_ms + offset))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    found: dict[str, set[str]] = {}
    for clip_id, (words, inside, offset) in clips.items():
        ids = {
            w.id
            for w in words
            if w.text
            and w.id not in inside
            and sum(max(0, min(w.e_ms + offset, e) - max(w.s_ms + offset, s)) for s, e in merged)
            * 2
            >= w.e_ms - w.s_ms
        }
        if ids:
            found[clip_id] = ids
    return found


def test_crosscam_linear_16000_words_2000_spans_and_8000_long_words_are_fast() -> None:
    master = [_word("a1", i, 2 * i, 2 * i + 1) for i in range(16_000)]
    inside = {w.id for w in master[::8]}  # 2 000 numbers of one word, 16 ms apart
    member = [_word("a2", i, i, i + 30_000) for i in range(8_000)]  # 30 s each: every span is hit
    started = time.monotonic()
    found = covered_ids({"a1": (master, inside, 0), "a2": (member, set(), 0)})
    assert time.monotonic() - started < 2.0
    assert found == {}  # a long word is covered only if half of it is: 2 000 ms of 30 000


def test_crosscam_linear_gives_what_the_definition_gives() -> None:
    rng = random.Random(18)
    for _ in range(60):
        clips: dict[str, tuple[list[Word], set[str], int]] = {}
        for clip in ("a1", "a2", "a3"):
            t, words = 0, []
            for i in range(rng.randint(5, 40)):
                t += rng.randint(0, 120)
                length = rng.choice([30, 90, 300, 1500])
                words.append(_word(clip, i, t, t + length))
                t += rng.randint(0, 200)
            inside = {w.id for w in words if rng.random() < 0.3}
            clips[clip] = (words, inside, rng.randint(-300, 300))
        assert covered_ids(clips) == _brute(clips)
