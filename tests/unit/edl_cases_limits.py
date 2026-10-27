"""The limits of an EDL on the parser (spec 001.24, points 4, 5, 7 and 10): how many clips and spans
it may have and how big a whole number may be (S1.5b rows 21, 22, 24 and 27).

Collected from `test_edl_model.py`, which is at the 300-line limit.
"""

from collections.abc import Callable

import pytest

from kcut.edl.parse import parse_edl
from tests.unit.edl_fakes import Doc, edit

__all__ = ["TestLimits"]
BIG = 10**15  # the first whole number an EDL may not hold (001.24, point 5)


class TestLimits:
    """The parser refuses what is too big and reads the biggest it allows."""

    @pytest.mark.parametrize("key", ["clips", "spans"])
    def test_edl_scale_more_than_ten_thousand_items_is_one_e01_with_the_count(
        self, key: str
    ) -> None:
        item = {"kind": "gap", "at_f": 0, "dur_f": 1, "why": "x"}
        if key == "spans":
            item = {"kind": "color", "at_f": 0, "dur_f": 1, "color": "#000000"}
        doc = edit(lambda d: d.update({key: [item] * 10_001}))
        edl, issues = parse_edl(doc)
        assert edl is None and [(i.code, i.path) for i in issues] == [("E01", key)]
        assert "10001" in issues[0].message_es and "10000" in issues[0].message_es

    @pytest.mark.parametrize("key", ["clips", "spans"])
    def test_edl_scale_exactly_ten_thousand_items_are_read(self, key: str) -> None:
        item = {"kind": "gap", "at_f": 0, "dur_f": 1, "why": "x"}
        if key == "spans":
            item = {"kind": "color", "at_f": 0, "dur_f": 1, "color": "#000000"}
        edl, issues = parse_edl(edit(lambda d: d.update({key: [item] * 10_000})))
        assert issues == [] and edl is not None and len(getattr(edl, key)) == 10_000

    @pytest.mark.parametrize(
        ("path", "change"),
        [
            ("version", lambda d: d.update(version=BIG)),
            ("fps", lambda d: d.update(fps=BIG)),
            ("frames", lambda d: d.update(frames=BIG)),
            ("output.w", lambda d: d["output"].update(w=BIG)),
            ("clips[1].in_f", lambda d: d["clips"][1].update(in_f=BIG)),
            ("clips[1].at_f", lambda d: d["clips"][1].update(at_f=BIG)),
            ("clips[0].dur_f", lambda d: d["clips"][0].update(dur_f=BIG)),
            ("spans[1].dur_f", lambda d: d["spans"][1].update(dur_f=BIG)),
            ("spans[6].fade_out_f", lambda d: d["spans"][6].update(fade_out_f=BIG)),
            ("spans[4].src_f", lambda d: d["spans"][4].update(src_f=BIG)),
            ("spans[4].keys[0].at_f", lambda d: d["spans"][4]["keys"][0].update(at_f=BIG)),
            ("spans[4].keys[0].card[0]", lambda d: d["spans"][4]["keys"][0]["card"].insert(0, BIG)),
            ("spans[4].remap[1].src_f", lambda d: d["spans"][4]["remap"][1].update(src_f=BIG)),
        ],
    )
    def test_edl_output_capped_a_whole_number_of_ten_to_the_fifteen_is_an_e01(
        self, path: str, change: Callable[[Doc], object]
    ) -> None:
        edl, issues = parse_edl(edit(change))
        assert edl is None and issues and all(i.code == "E01" for i in issues)
        if "card" not in path:  # the card is a list: its own error is about its length
            assert path in [i.path for i in issues]

    def test_edl_output_capped_the_largest_whole_number_is_still_read(self) -> None:
        big = 10**15 - 1
        edl, issues = parse_edl(edit(lambda d: d["clips"][1].update(in_f=big - 1, out_f=big)))
        assert issues == [] and edl is not None

    def test_edl_output_capped_two_durations_of_4300_digits_are_e01_and_never_a_crash(self) -> None:
        def change(doc: Doc) -> None:
            doc["clips"][0]["dur_f"] = 10**4299
            doc["spans"][0]["dur_f"] = 10**4299

        edl, issues = parse_edl(edit(change))
        assert edl is None and [(i.code, i.path) for i in issues] == [
            ("E01", "clips[0].dur_f"),
            ("E01", "spans[0].dur_f"),
        ]
        assert all("4300 dígitos" in i.message_es for i in issues)

    def test_edl_output_capped_a_negative_whole_number_is_capped_too(self) -> None:
        edl, issues = parse_edl(edit(lambda d: d["spans"][1].update(fade_in_f=-(10**15))))
        assert edl is None and [(i.code, i.path) for i in issues] == [("E01", "spans[1].fade_in_f")]

    def test_edl_empty_an_edl_with_nothing_in_it_is_read_and_then_judged_not_read_as_an_error(
        self,
    ) -> None:
        doc = edit(lambda d: d.update(frames=0, clips=[], spans=[]))
        edl, issues = parse_edl(doc)
        assert issues == [] and edl is not None
        assert (edl.frames, edl.clips, edl.spans) == (0, (), ())
