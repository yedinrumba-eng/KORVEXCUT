"""Votes between cameras: the member camera's transcript checks the master's, word by word."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

from kcut.text.normalize import norm_token
from kcut.transcribe.model import Word

LONG_MS = 2_000  # a member word longer than this goes to the "long" index (rare: a stretched word)
MAX_CANDIDATES = 8  # a master word weighs this many member words at most (spec 001.14, point 5)


@dataclass(frozen=True)
class _Shifted:
    """A member word on the master's clock."""

    s_ms: int
    e_ms: int
    text: str
    token: str
    word_id: str


class _Cand(NamedTuple):
    """What a member heard over a master word: its text, how much of the word it covers, and
    where it sits (the order candidates are ranked and ties are broken in)."""

    overlap_ms: int
    s_ms: int
    e_ms: int
    member: int
    text: str
    token: str
    word_id: str


@dataclass(frozen=True)
class Tally:
    """The result of a vote: the alternatives of the master's words (all members together), the
    word each one came from (`sources`: master word id -> member position and word id, spec 001.16
    point 1) and, per member and in the order given, how many master words that member alone
    disagrees on."""

    alternatives: dict[str, str]
    sources: dict[str, tuple[int, str]]
    disagreements: list[int]


class _Index:
    """Member words sorted by start, searched by bisect instead of scanned.

    `reach[i]` is the largest end among the first `i + 1` words, so the first word that can still
    be running at time `s` is found by bisecting `reach`, and the first that starts too late by
    bisecting the starts. Between the two sit the candidates, plus the few words an earlier, longer
    word keeps in range. They are measured together (numpy), not one by one.
    """

    def __init__(self, words: list[_Shifted]) -> None:
        self.words = words
        self.starts = np.array([w.s_ms for w in words], dtype=np.int64)
        self.ends = np.array([w.e_ms for w in words], dtype=np.int64)
        self.reach = np.maximum.accumulate(self.ends)

    def best(self, s_ms: int, e_ms: int, member: int) -> list[_Cand]:
        """The member words that cover at least half of `[s_ms, e_ms)`: the 8 with the largest
        overlap, and between equal overlaps the earliest."""
        first = int(np.searchsorted(self.reach, s_ms, side="right"))
        last = int(np.searchsorted(self.starts, e_ms, side="left"))
        if first >= last:
            return []
        starts, ends = self.starts[first:last], self.ends[first:last]
        overlap = np.minimum(ends, e_ms) - np.maximum(starts, s_ms)
        half = max(1, (e_ms - s_ms + 1) // 2)  # 2 * overlap >= duration, and some overlap at all
        kept = np.flatnonzero(overlap >= half)
        if kept.size > MAX_CANDIDATES:  # the 8 largest, found without sorting all of them
            kept = kept[_largest(overlap[kept])]
        order = np.lexsort((ends[kept], starts[kept], -overlap[kept]))
        found: list[_Cand] = []
        for i in kept[order]:
            word = self.words[first + int(i)]
            found.append(
                _Cand(
                    int(overlap[i]),
                    word.s_ms,
                    word.e_ms,
                    member,
                    word.text,
                    word.token,
                    word.word_id,
                )
            )
        return found


def _largest(values: NDArray[np.int64]) -> NDArray[np.intp]:
    """Positions of the `MAX_CANDIDATES` largest values, in order of position. Among equal values
    the earliest position wins, and with words sorted by start that is the earliest word."""
    cut = np.partition(values, values.size - MAX_CANDIDATES)[values.size - MAX_CANDIDATES]
    above = np.flatnonzero(values > cut)
    ties = np.flatnonzero(values == cut)[: MAX_CANDIDATES - above.size]
    return np.sort(np.concatenate([above, ties]))


def vote(
    master_words: Sequence[Word], members: Sequence[tuple[Sequence[Word], int]]
) -> dict[str, str]:
    """Master word id -> the text the other cameras heard instead, for each disagreement."""
    return tally(master_words, members).alternatives


def tally(master_words: Sequence[Word], members: Sequence[tuple[Sequence[Word], int]]) -> Tally:
    """Vote once per member and merge (spec 001.14, point 5).

    Each member is `(words, offset_ms)`: its words move to the master's clock by adding
    `offset_ms`. A member word is a candidate for a master word if it overlaps at least 50 % of
    the master word's duration, and a master word looks at 8 candidates at most: the largest
    overlaps, and between equal ones the earliest. If any candidate has the same normalized token
    there is agreement and nothing is recorded. If there are candidates and none matches, the
    alternative is the most frequent candidate text (a tie goes to the larger overlap, then to
    the earlier). A master word with no candidates has no data. Words with no text take no part.

    Every member is voted exactly one time. Its best 8 candidates per master word serve for its
    own disagreements, and the 8 best of all members together serve for the alternatives, which is
    what voting "all together" would give. Candidates come from a sorted search measured with
    numpy, so the work grows with the candidates kept, not with how many overlap.
    """
    tokens = [norm_token(w.text) for w in master_words]
    heard = [
        _vote_member(master_words, tokens, words, offset, k)
        for k, (words, offset) in enumerate(members)
    ]
    alternatives: dict[str, str] = {}
    sources: dict[str, tuple[int, str]] = {}
    disagreements = [0] * len(members)
    for i, word in enumerate(master_words):
        token = tokens[i]
        if not token:
            continue
        for k, member_heard in enumerate(heard):
            if member_heard[i] and all(c.token != token for c in member_heard[i]):
                disagreements[k] += 1
        pooled = _best([c for member_heard in heard for c in member_heard[i]])
        if pooled and all(c.token != token for c in pooled):
            chosen = _most_frequent(pooled)
            alternatives[word.id] = chosen.text
            sources[word.id] = (chosen.member, chosen.word_id)
    return Tally(alternatives, sources, disagreements)


def _vote_member(
    master_words: Sequence[Word],
    tokens: Sequence[str],
    words: Sequence[Word],
    offset_ms: int,
    member: int,
) -> list[list[_Cand]]:
    """For each master word, the best candidates among one member's words (none for a master
    word with no token)."""
    short, long = _indexes(_shift(words, offset_ms))
    return [
        _best(short.best(w.s_ms, w.e_ms, member) + long.best(w.s_ms, w.e_ms, member))
        if tokens[i]
        else []
        for i, w in enumerate(master_words)
    ]


def _best(candidates: list[_Cand]) -> list[_Cand]:
    """The 8 largest overlaps, earliest first between equal ones."""
    ranked = sorted(candidates, key=lambda c: (-c.overlap_ms, c.s_ms, c.e_ms, c.member))
    return ranked[:MAX_CANDIDATES]


def _shift(words: Sequence[Word], offset_ms: int) -> list[_Shifted]:
    """The member's words on the master's clock; a word with nothing to compare (deleted, or
    only punctuation) is left out."""
    moved = [
        _Shifted(w.s_ms + offset_ms, w.e_ms + offset_ms, w.text, token, w.id)
        for w in words
        if (token := norm_token(w.text))
    ]
    return sorted(moved, key=lambda w: (w.s_ms, w.e_ms))


def _indexes(words: list[_Shifted]) -> tuple[_Index, _Index]:
    """Two indexes: ordinary words, and the long ones (which would widen every search)."""
    short = [w for w in words if w.e_ms - w.s_ms <= LONG_MS]
    long = [w for w in words if w.e_ms - w.s_ms > LONG_MS]
    return _Index(short), _Index(long)


def _most_frequent(candidates: Sequence[_Cand]) -> _Cand:
    """The candidate that stands for the most frequent text: the best ranked one with that text."""
    counts = Counter(c.text for c in candidates)
    largest: dict[str, int] = {}
    for c in candidates:
        largest[c.text] = max(largest.get(c.text, 0), c.overlap_ms)
    earliest = sorted(candidates, key=lambda c: (c.s_ms, c.e_ms, c.member))
    texts = list(dict.fromkeys(c.text for c in earliest))
    winner = min(texts, key=lambda t: (-counts[t], -largest[t], texts.index(t)))
    return next(c for c in candidates if c.text == winner)
