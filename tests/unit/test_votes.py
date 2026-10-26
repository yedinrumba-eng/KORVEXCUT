"""Votes between cameras: agreement, disagreement, no data, offsets and tie-breaks."""

import time

from kcut.pack.votes import vote

# The classes on overlap live in `vote_cases.py` (300-line rule) and are collected here, which is
# the file the criteria of the spec run.
from tests.unit.vote_cases import TestVoteOverlapCapped, TestVoteStacked, word  # noqa: F401

_w = word


MASTER = [
    _w("a1", 0, "ven,", 1000, 1300),
    _w("a1", 1, "que", 1400, 1600),
    _w("a1", 2, "te", 1700, 1900),
    _w("a1", 3, "voy", 2000, 2300),
]


def test_agreement_records_nothing() -> None:
    member = [_w("a2", 0, "Ven", 0, 300), _w("a2", 1, "que", 400, 600)]
    assert vote(MASTER, [(member, 1000)]) == {}


def test_disagreement_records_what_the_other_camera_heard() -> None:
    member = [_w("a2", 0, "ven", 0, 300), _w("a2", 1, "de", 700, 900)]
    assert vote(MASTER, [(member, 1000)]) == {"a1:w0002": "de"}


def test_no_candidates_means_no_data() -> None:
    assert vote(MASTER, [([_w("a2", 0, "hola", 5000, 5300)], 0)]) == {}
    assert vote(MASTER, []) == {}


def test_the_offset_moves_the_member_words_to_the_master_clock() -> None:
    member = [_w("a2", 0, "dede", 700, 900)]  # +1000 -> 1700..1900, over "te"
    assert vote(MASTER, [(member, 1000)]) == {"a1:w0002": "dede"}
    assert vote(MASTER, [(member, 0)]) == {}  # at 700..900 it overlaps no master word
    assert vote(MASTER, [(member, -300)]) == {}


def test_a_negative_offset_works_too() -> None:
    member = [_w("a2", 0, "dede", 2700, 2900)]  # -1000 -> 1700..1900
    assert vote(MASTER, [(member, -1000)]) == {"a1:w0002": "dede"}


def test_overlap_must_reach_half_of_the_master_word() -> None:
    # "te" lasts 200 ms (1700-1900): 100 ms of overlap is enough, 99 is not
    assert vote(MASTER, [([_w("a2", 0, "x", 1800, 1950)], 0)]) == {"a1:w0002": "x"}
    assert vote(MASTER, [([_w("a2", 0, "x", 1801, 1950)], 0)]) == {}


def test_overlap_is_measured_against_the_master_word_not_the_member_word() -> None:
    # a long member word covering the whole master word counts fully
    assert vote(MASTER, [([_w("a2", 0, "x", 1000, 2500)], 0)]).keys() == {
        "a1:w0000",
        "a1:w0001",
        "a1:w0002",
        "a1:w0003",
    }


def test_one_matching_candidate_is_enough_for_agreement() -> None:
    member = [_w("a2", 0, "de", 1700, 1800), _w("a2", 1, "te", 1800, 1900)]
    assert vote(MASTER, [(member, 0)]) == {}


def test_the_most_frequent_text_wins() -> None:
    master = [_w("a1", 0, "casa", 1000, 2000)]
    members = [
        ([_w("a2", 0, "caza", 1000, 1500)], 0),
        ([_w("a3", 0, "cosa", 1000, 1900)], 0),
        ([_w("a4", 0, "caza", 1100, 1700)], 0),
    ]
    assert vote(master, members) == {"a1:w0000": "caza"}


def test_a_tie_goes_to_the_larger_overlap() -> None:
    master = [_w("a1", 0, "casa", 1000, 2000)]
    members = [
        ([_w("a2", 0, "caza", 1000, 1500)], 0),  # 500 ms
        ([_w("a3", 0, "cosa", 1000, 1900)], 0),  # 900 ms
    ]
    assert vote(master, members) == {"a1:w0000": "cosa"}


def test_a_full_tie_keeps_the_first_candidate() -> None:
    master = [_w("a1", 0, "casa", 1000, 2000)]
    members = [
        ([_w("a2", 0, "caza", 1000, 1600)], 0),
        ([_w("a3", 0, "cosa", 1000, 1600)], 0),
    ]
    assert vote(master, members) == {"a1:w0000": "caza"}


def test_candidates_from_several_members_are_pooled_for_agreement() -> None:
    master = [_w("a1", 0, "casa", 1000, 2000)]
    members = [
        ([_w("a2", 0, "caza", 1000, 1900)], 0),
        ([_w("a3", 0, "Casa.", 1000, 1900)], 0),
    ]
    assert vote(master, members) == {}


def test_deleted_and_punctuation_only_member_words_take_no_part() -> None:
    member = [_w("a2", 0, "", 1000, 1300), _w("a2", 1, "-", 1400, 1600)]
    assert vote(MASTER, [(member, 0)]) == {}


def test_deleted_master_words_get_no_vote() -> None:
    master = [_w("a1", 0, "", 1000, 1300)]
    assert vote(master, [([_w("a2", 0, "algo", 1000, 1300)], 0)]) == {}


def test_a_very_long_earlier_member_word_is_still_found() -> None:
    member = [_w("a2", 0, "largo", 0, 5000), _w("a2", 1, "corto", 3000, 3100)]
    assert vote([_w("a1", 0, "otra", 4000, 4400)], [(member, 0)]) == {"a1:w0000": "largo"}


def test_vote_is_not_quadratic() -> None:
    """20 000 dense words per camera plus one member word of 30 s (the longest a cached word may
    be): candidates come from a sorted search, not from scanning a 30 s window for every word."""
    n = 20_000
    master = [_w("a1", i, f"p{i}", i * 10, i * 10 + 8) for i in range(n)]
    member = [
        _w("a2", i, f"q{i}" if i % 1000 == 0 else f"p{i}", i * 10, i * 10 + 8) for i in range(n)
    ]
    member.append(_w("a2", n, "largo", 0, 30_000))
    started = time.monotonic()
    alternatives = vote(master, [(member, 0)])
    elapsed = time.monotonic() - started
    assert elapsed < 5.0, f"{elapsed:.1f} s"
    # the 30 s word is a candidate of the first 3000 master words. Where the member disagrees
    # ("q0", "q1000", "q2000") the texts tie on count and overlap, and the first heard wins.
    assert alternatives["a1:w0000"] == "q0" and alternatives["a1:w1000"] == "largo"
    assert alternatives["a1:w19000"] == "q19000" and "a1:w0005" not in alternatives
    assert len(alternatives) == 20
