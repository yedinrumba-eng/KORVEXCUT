"""Votes between cameras when many words overlap (spec 001.14 point 5, 001.16 point 8)."""

import random
import time
from typing import Any

import numpy as np
import pytest

from kcut.pack import votes
from kcut.pack.votes import vote
from kcut.text.normalize import norm_token
from kcut.transcribe.model import Word


def word(clip: str, i: int, text: str, s_ms: int, e_ms: int) -> Word:
    return Word(f"{clip}:w{i:04d}", i, text, s_ms, e_ms, 0.9)


_w = word


def _pooled(master: list[Word], members: list[tuple[list[Word], int]]) -> dict[str, str]:
    """The vote written the slow, obvious way: pool every member's candidates, keep the 8 best."""
    found: dict[str, str] = {}
    for word in master:
        token = norm_token(word.text)
        pool = []
        for k, (words, offset) in enumerate(members):
            for other in words:
                s, e = other.s_ms + offset, other.e_ms + offset
                overlap = min(e, word.e_ms) - max(s, word.s_ms)
                if norm_token(other.text) and overlap > 0 and 2 * overlap >= word.e_ms - word.s_ms:
                    pool.append((overlap, s, e, k, other.text))
        top = sorted(pool, key=lambda c: (-c[0], c[1], c[2], c[3]))[:8]
        if token and top and all(norm_token(c[4]) != token for c in top):
            order = sorted(top, key=lambda c: (c[1], c[2], c[3]))
            texts = list(dict.fromkeys(c[4] for c in order))
            count = {x: sum(c[4] == x for c in top) for x in texts}
            best = {x: max(c[0] for c in top if c[4] == x) for x in texts}
            found[word.id] = min(texts, key=lambda x: (-count[x], -best[x], texts.index(x)))
    return found


class TestVoteOverlapCapped:
    """001.14 point 5: a master word weighs at most 8 candidates, and each member votes once."""

    def test_vote_overlap_capped_masses_of_overlap_finish_fast(self) -> None:
        n = 2000
        master = [_w("a1", i, f"m{i}", 1000 + i % 50, 1500) for i in range(n)]
        member = [_w("a2", i, f"q{i}", 1000 + (i * 7) % 50, 1500) for i in range(n)]
        started = time.monotonic()
        alternatives = vote(master, [(member, 0)])
        assert time.monotonic() - started < 5.0
        assert len(alternatives) == n  # nobody agrees, and every word got an answer

    def test_vote_overlap_capped_only_the_8_largest_overlaps_count(self) -> None:
        master = [_w("a1", 0, "casa", 1000, 2000)]
        # overlaps 500, 510, ... 690 ms: the 8 largest are t12..t19, and "casa" overlaps the least
        member = [_w("a2", i, f"t{i}", 1500 - 10 * i, 2000) for i in range(20)]
        member.append(_w("a2", 20, "casa", 1500, 2000))
        assert vote(master, [(member, 0)]) == {"a1:w0000": "t19"}  # counts tie: the largest overlap

    @pytest.mark.parametrize(
        ("casa_overlap", "expected"),
        [(625, {}), (615, {"a1:w0000": "t19"})],
        ids=["8th_counts", "9th_does_not"],
    )
    def test_vote_overlap_capped_the_8th_overlap_counts_and_the_9th_does_not(
        self, casa_overlap: int, expected: dict[str, str]
    ) -> None:
        master = [_w("a1", 0, "casa", 1000, 2000)]
        member = [_w("a2", i, f"t{i}", 1500 - 10 * i, 2000) for i in range(20)]  # 500 + 10 i ms
        member.append(_w("a2", 20, "casa", 2000 - casa_overlap, 2000))
        assert vote(master, [(member, 0)]) == expected

    def test_vote_overlap_capped_a_tie_in_overlap_goes_to_the_earliest(self) -> None:
        master = [_w("a1", 0, "casa", 1000, 2000)]
        member = [_w("a2", i, f"t{i:02d}", 1000 + i, 1500 + i) for i in range(12)]  # 500 ms each
        assert vote(master, [(member, 0)]) == {"a1:w0000": "t00"}

    def test_vote_overlap_capped_every_member_is_voted_exactly_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[int] = []
        real = votes._vote_member

        def counting(*args: Any, **kwargs: Any) -> Any:
            calls.append(1)
            return real(*args, **kwargs)

        monkeypatch.setattr(votes, "_vote_member", counting)
        master = [_w("a1", i, f"p{i}", i * 100, i * 100 + 80) for i in range(30)]
        members = [
            (
                [
                    _w(f"a{k}", i, f"p{i}" if i % k else f"x{i}", i * 100, i * 100 + 80)
                    for i in range(30)
                ],
                0,
            )
            for k in (2, 3, 5)
        ]
        result = votes.tally(master, members)
        assert len(calls) == 3
        assert result.alternatives == vote(master, members)
        assert result.disagreements == [len(vote(master, [m])) for m in members]

    def test_vote_overlap_capped_merging_members_matches_a_brute_force_pool(self) -> None:
        rng = random.Random(3)
        for _ in range(60):
            master = [_w("a1", i, rng.choice("abc"), i * 100, i * 100 + 90) for i in range(6)]
            members = [
                (
                    [
                        _w("a2", i, rng.choice("abc"), i * 100 + rng.randint(0, 40), i * 100 + 90)
                        for i in range(6)
                        if rng.random() < 0.8
                    ],
                    0,
                )
                for _ in range(rng.randint(1, 3))
            ]
            assert vote(master, members) == _pooled(master, members)


class TestVoteStacked:
    """001.16 point 8: with every word on top of every other, the 8 best candidates come out of a
    partition before any sorting, so the cost per word stays bounded. 001.17 point 10: what is
    checked is the sorting (a spy), and the clock only has a loose limit, for a loaded machine."""

    @pytest.mark.slow
    def test_vote_stacked_20k_words_per_camera_in_500_ms_never_sort_more_than_8(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sizes: list[int] = []
        real = np.lexsort

        def spy(keys: Any, *args: Any, **kwargs: Any) -> Any:
            sizes.append(len(keys[0]))
            return real(keys, *args, **kwargs)

        monkeypatch.setattr(np, "lexsort", spy)
        n = 20_000  # every word on the very same 500 ms: each one has 20 000 candidates
        master = [_w("a1", i, f"m{i}", 1000, 1500) for i in range(n)]
        member = [_w("a2", i, f"q{i}", 1000, 1500) for i in range(n)]
        started = time.monotonic()
        alternatives = vote(master, [(member, 0)])
        elapsed = time.monotonic() - started
        assert len(alternatives) == n  # nobody agrees and every word got an answer
        assert sizes and max(sizes) <= votes.MAX_CANDIDATES
        assert elapsed < 30.0, f"{elapsed:.1f} s"

    def test_vote_stacked_20k_candidates_only_the_8_best_are_ever_sorted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sizes: list[int] = []
        real = np.lexsort

        def spy(keys: Any, *args: Any, **kwargs: Any) -> Any:
            sizes.append(len(keys[0]))
            return real(keys, *args, **kwargs)

        monkeypatch.setattr(np, "lexsort", spy)
        master = [_w("a1", i, f"m{i}", 1000, 1500) for i in range(100)]
        member = [_w("a2", i, f"q{i}", 1000, 1500) for i in range(20_000)]  # 20 000 candidates each
        assert len(vote(master, [(member, 0)])) == 100
        assert sizes and max(sizes) <= votes.MAX_CANDIDATES

    def test_vote_stacked_the_8_best_match_a_brute_force_pool_with_many_candidates(self) -> None:
        rng = random.Random(16)
        for _ in range(40):
            master = [_w("a1", i, rng.choice("abcd"), 1000 + i, 1100 + i * 3) for i in range(5)]
            members = []
            for _ in range(rng.randint(1, 3)):
                words = [
                    _w(
                        "a2",
                        i,
                        rng.choice("abcd"),
                        1000 + rng.randint(0, 60),
                        1100 + rng.randint(0, 90),
                    )
                    for i in range(rng.randint(10, 40))
                ]
                members.append((words, rng.randint(-20, 20)))
            members = [
                (sorted(words, key=lambda w: (w.s_ms, w.e_ms)), off) for words, off in members
            ]
            assert vote(master, members) == _pooled(master, members)

    def test_vote_stacked_equal_overlaps_at_the_cut_go_to_the_earliest_word(self) -> None:
        master = [_w("a1", 0, "casa", 1000, 2000)]
        member = [_w("a2", i, f"t{i:02d}", 1000 + i, 1500 + i) for i in range(30)]  # all 500 ms
        assert vote(master, [(member, 0)]) == {"a1:w0000": "t00"}
