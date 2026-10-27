"""Time anchors (spec S1.6a row 2): `kcut.anchors.resolve_time` and the three problems it names.

The EDL is the example of the spec: `a1` frames 60-239 are heard from output frame 30, and 300-344
from output frame 270.
"""

import pytest

from kcut.anchors import Resolved, has_time_shape, resolve_time
from kcut.edl.words import KeptWord
from tests.unit.edl_fakes import edit, parsed


def _word(word_id: str, out_s: int, out_e: int) -> KeptWord:
    return KeptWord(word_id, "texto", 0, out_s, out_e, "a1", 0, 0)


KEPT = [_word("a1:w0001", 40, 52), _word("a1:w0002", 55, 70), _word("a1:w0031", 275, 290)]
EDL = parsed()


def _at(value: object) -> Resolved:
    return resolve_time(value, KEPT, EDL)


@pytest.mark.parametrize("frame", [0, 1, 344, 345, 10**9, -3])
def test_anchors_a_whole_number_is_that_frame(frame: int) -> None:
    assert _at(frame) == Resolved(frame, None, 1)


@pytest.mark.parametrize("value", [True, False, 3.0, 30.5, "30", None, [], (3,), {}])
def test_anchors_anything_that_is_not_a_whole_number_or_an_anchor_is_a_shape_problem(
    value: object,
) -> None:
    assert _at(value) == Resolved(None, "shape", 0)


def test_anchors_a_word_anchor_is_the_start_or_the_end_of_the_kept_word() -> None:
    assert _at({"word": "a1:w0002", "edge": "start"}) == Resolved(55, None, 1)
    assert _at({"word": "a1:w0002", "edge": "end"}) == Resolved(70, None, 1)


def test_anchors_the_offset_of_a_word_anchor_is_added_and_may_be_negative() -> None:
    assert _at({"word": "a1:w0031", "edge": "start", "offset_f": -1}).frame == 274
    assert _at({"word": "a1:w0031", "edge": "start", "offset_f": 30}).frame == 305
    assert _at({"word": "a1:w0031", "edge": "end", "offset_f": 0}).frame == 290


def test_anchors_a_word_that_the_cut_does_not_keep_is_word_not_kept() -> None:
    assert _at({"word": "a1:w0099", "edge": "start"}) == Resolved(None, "word_not_kept", 0)
    assert resolve_time({"word": "a1:w0001", "edge": "start"}, [], EDL).problem == "word_not_kept"


def test_anchors_a_source_anchor_is_where_that_frame_of_the_source_is_heard() -> None:
    assert _at({"src": "a1", "f": 100}) == Resolved(70, None, 1)  # 30 + (100 - 60)
    assert _at({"src": "a1", "f": 60, "offset_f": 5}) == Resolved(35, None, 1)
    assert _at({"src": "a1", "f": 300}).frame == 270
    assert _at({"src": "a1", "f": 239}).frame == 209  # the last frame of the first clip


def test_anchors_a_source_frame_that_is_not_heard_is_src_not_heard() -> None:
    for anchor in ({"src": "a1", "f": 59}, {"src": "a1", "f": 240}, {"src": "a2", "f": 100}):
        assert _at(anchor) == Resolved(None, "src_not_heard", 0)


def test_anchors_a_source_frame_heard_twice_uses_the_first_and_counts_both() -> None:
    twice = parsed(
        edit(
            lambda d: d.update(
                clips=[
                    {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 60, "out_f": 120, "why": "x"},
                    {
                        "kind": "voice",
                        "at_f": 100,
                        "src": "a1",
                        "in_f": 90,
                        "out_f": 150,
                        "why": "x",
                    },
                ]
            )
        )
    )
    found = resolve_time({"src": "a1", "f": 100}, KEPT, twice)
    assert found == Resolved(40, None, 2)  # 0 + (100 - 60), and 100 + (100 - 90) is the second
    assert resolve_time({"src": "a1", "f": 100, "offset_f": 3}, KEPT, twice).frame == 43


@pytest.mark.parametrize(
    "anchor",
    [
        {"word": "a1:w0002"},  # no edge
        {"word": "a1:w0002", "edge": "middle"},
        {"word": "a1:w0002", "edge": "start", "extra": 1},
        {"word": "a1:w0002", "edge": "start", "offset_f": 1.5},
        {"word": "a1:w0002", "edge": "start", "offset_f": True},
        {"word": 7, "edge": "start"},
        {"word": "a1:w0002", "edge": "start", "src": "a1"},
        {"src": "a1"},  # no f
        {"src": "a1", "f": 1.0},
        {"src": "a1", "f": True},
        {"src": 3, "f": 1},
        {"src": "a1", "f": 100, "offset_f": "1"},
        {"src": "a1", "f": 100, "edge": "start"},
        {"f": 100},
    ],
)
def test_anchors_another_form_or_a_key_too_many_is_a_shape_problem(anchor: object) -> None:
    assert _at(anchor) == Resolved(None, "shape", 0)
    assert not has_time_shape(anchor)


def test_anchors_has_time_shape_says_only_the_shape() -> None:
    assert has_time_shape(0) and has_time_shape(-5)
    assert has_time_shape({"word": "no existe", "edge": "end"})  # the shape, not the lookup
    assert has_time_shape({"src": "zz", "f": 3, "offset_f": -2})
