"""Ranges, keys, fades and warnings of an EDL (spec S1.5a): E13, E15, E17, E18 and W01 to W05.

Collected from `test_edl_ranges.py` (300-line rule), which is where the criterion runs them.
"""

from tests.unit.edl_fakes import Doc, check, codes, edit, only

__all__ = ["TestFields", "TestWarnings"]


def _two_shots(doc: Doc, first: float, second: float, push: float = 0.0) -> None:
    """Replace spans 1 to 3 (30..210) by two cam shots of a1: 30..60 and 60..210."""
    doc["spans"][1:4] = [
        {"kind": "cam", "at_f": 30, "dur_f": 30, "src": "a1", "zoom": first, "push": push},
        {"kind": "cam", "at_f": 60, "dur_f": 150, "src": "a1", "zoom": second},
    ]


def _cut_inside_a_shot(doc: Doc, second_in_f: int) -> None:
    """The voice of 30..210 becomes two clips (the second one from `second_in_f`), and spans 1 to
    3 one synchronized shot of a1 over both."""
    voice = {"kind": "voice", "src": "a1"}
    doc["clips"][1:2] = [
        {**voice, "at_f": 30, "in_f": 60, "out_f": 120, "why": "a"},
        {**voice, "at_f": 90, "in_f": second_in_f, "out_f": second_in_f + 120, "why": "b"},
    ]
    doc["spans"][1:4] = [{"kind": "cam", "at_f": 30, "dur_f": 180, "src": "a1"}]


class TestFields:
    def test_edl_ranges_e13_cam_numbers(self) -> None:
        for field, value in (
            ("zoom", 3.5),
            ("zoom", 0.9),
            ("cx", 1.2),
            ("cy", -0.1),
            ("push", 0.6),
        ):
            assert only(edit(lambda d, f=field, v=value: d["spans"][1].update({f: v})), "E13") == [
                f"spans[1].{field}"
            ], (field, value)

    def test_edl_ranges_e13_the_edges_of_the_ranges_are_inside(self) -> None:
        def change(doc: Doc) -> None:
            doc["spans"][1].update(zoom=3.0, cx=0.0, cy=1.0, push=0.5)

        assert only(edit(change), "E13") == []

    def test_edl_ranges_e13_broll_numbers(self) -> None:
        def broll(doc: Doc, **fields: object) -> None:
            doc["spans"][1] = {"kind": "broll", "at_f": 30, "dur_f": 60, "src": "b1", "src_f": 0}
            doc["spans"][1].update(fields)

        assert only(edit(lambda d: broll(d, dim=1.6)), "E13") == ["spans[1].dim"]
        assert only(edit(lambda d: broll(d, sharpen=-0.1)), "E13") == ["spans[1].sharpen"]
        assert only(edit(lambda d: broll(d, push=0.51)), "E13") == ["spans[1].push"]
        assert only(edit(lambda d: broll(d, dim=1.5, sharpen=1.0)), "E13") == []

    def test_edl_ranges_e13_screen_numbers(self) -> None:
        def key(doc: Doc, **fields: object) -> None:
            doc["spans"][4]["keys"][0].update(fields)

        assert only(edit(lambda d: d["spans"][4].update(card_y=1.5)), "E13") == ["spans[4].card_y"]
        assert only(edit(lambda d: key(d, crop=[0.5, 0.5, 0.04])), "E13") == [
            "spans[4].keys[0].crop[2]"
        ]
        assert only(edit(lambda d: key(d, crop=[0.5, 0.5, 1.01])), "E13") == [
            "spans[4].keys[0].crop[2]"
        ]
        assert only(edit(lambda d: d["spans"][4]["remap"][1].update(speed=4.5)), "E13") == [
            "spans[4].remap[1].speed"
        ]
        assert only(edit(lambda d: d["spans"][4]["remap"][1].update(speed=0.2)), "E13") == [
            "spans[4].remap[1].speed"
        ]

    def test_edl_ranges_e13_a_card_that_does_not_fit(self) -> None:
        def key(doc: Doc, card: list[int]) -> None:
            doc["spans"][4]["keys"][0]["card"] = card

        assert only(edit(lambda d: key(d, [1064, 1800])), "E13") == []  # W - 16 by H - 120
        assert only(edit(lambda d: key(d, [1065, 800])), "E13") == ["spans[4].keys[0].card"]
        assert only(edit(lambda d: key(d, [1000, 1801])), "E13") == ["spans[4].keys[0].card"]
        assert only(edit(lambda d: key(d, [0, 500])), "E13") == ["spans[4].keys[0].card"]

    def test_edl_ranges_e13_negative_fades(self) -> None:
        assert only(edit(lambda d: d["spans"][6].update(fade_out_f=-1)), "E13") == [
            "spans[6].fade_out_f"
        ]

    def test_edl_ranges_e15_keys_and_remap_in_order_and_inside_the_span(self) -> None:
        def first(doc: Doc) -> None:
            doc["spans"][4]["keys"][0]["at_f"] = 1

        def same(doc: Doc) -> None:
            doc["spans"][4]["keys"][1]["at_f"] = 0

        def outside(doc: Doc) -> None:
            doc["spans"][4]["keys"][1]["at_f"] = 60

        def remap(doc: Doc) -> None:
            doc["spans"][4]["remap"][1]["at_f"] = 99

        assert "spans[4].keys[0]" in only(edit(first), "E15")
        assert only(edit(same), "E15") == ["spans[4].keys[1]"]
        assert only(edit(outside), "E15") == ["spans[4].keys[1]"]
        assert only(edit(remap), "E15") == ["spans[4].remap[1]"]
        assert only(edit(lambda d: d["spans"][4].update(keys=[])), "E15") == ["spans[4].keys"]

    def test_edl_ranges_e15_remap_is_optional_but_if_there_it_starts_at_zero(self) -> None:
        def no_remap(doc: Doc) -> None:
            doc["spans"][4].pop("remap")

        def late(doc: Doc) -> None:
            doc["spans"][4]["remap"][0]["at_f"] = 3

        assert only(edit(no_remap), "E15") == []
        assert only(edit(late), "E15") == ["spans[4].remap[0]"]

    def test_edl_ranges_e17_fades_longer_than_the_span(self) -> None:
        def change(doc: Doc) -> None:
            doc["spans"][0].update(fade_in_f=20, fade_out_f=11)

        assert only(edit(change), "E17") == ["spans[0]"]
        assert only(edit(lambda d: d["spans"][0].update(fade_in_f=20, fade_out_f=10)), "E17") == []

    def test_edl_ranges_e18_remap_and_src_f_must_agree(self) -> None:
        assert only(edit(lambda d: d["spans"][4].update(src_f=5)), "E18") == ["spans[4].src_f"]
        assert only(edit(lambda d: None), "E18") == []
        assert only(edit(lambda d: d["spans"][4].pop("remap")), "E18") == []  # no remap, no E18


class TestWarnings:
    def test_edl_ranges_w01_zoom_over_the_pixels_of_the_source(self) -> None:
        assert only(edit(lambda d: d["spans"][1].update(zoom=1.5)), "W01") == [
            "spans[1]",
            "spans[3]",
        ]
        assert only(edit(lambda d: d["spans"][3].update(zoom=1.3)), "W01") == []  # 0.975 of 1440

    def test_edl_ranges_w01_push_counts_for_the_biggest_zoom(self) -> None:
        def change(doc: Doc) -> None:
            doc["spans"][2].update(zoom=1.0, push=0.2)  # a2 is 1080 wide: 1.2 > 1.10

        assert only(edit(change), "W01") == ["spans[2]", "spans[3]"]

    def test_edl_ranges_w01_a_broll_enlarges_by_one_plus_push(self) -> None:
        def broll(doc: Doc) -> None:
            doc["spans"][1] = {
                "kind": "broll", "at_f": 30, "dur_f": 60, "src": "b1", "src_f": 0, "push": 0.5,
            }  # fmt: skip

        assert "spans[1]" in only(edit(broll), "W01")  # b1 is 1894x866: 487 px of it fill 1080

    def test_edl_ranges_w03_two_shots_of_one_camera_with_almost_the_same_zoom(self) -> None:
        assert only(edit(lambda d: _two_shots(d, 1.0, 1.1)), "W03") == ["spans[2]"]
        assert only(edit(lambda d: _two_shots(d, 1.0, 0.9)), "W03") == ["spans[2]"]

    def test_edl_ranges_w03_a_change_of_15_percent_or_more_is_a_real_cut(self) -> None:
        assert only(edit(lambda d: _two_shots(d, 1.0, 1.15)), "W03") == []  # exactly 15 %
        assert only(edit(lambda d: _two_shots(d, 1.0, 1.5)), "W03") == []
        assert only(edit(lambda d: _two_shots(d, 1.5, 1.0)), "W03") == []

    def test_edl_ranges_w03_the_push_of_the_first_shot_counts(self) -> None:
        # the first one ends at 1.0 * 1.2 = 1.2: the second at 1.2 is no change at all
        assert only(edit(lambda d: _two_shots(d, 1.0, 1.2, push=0.2)), "W03") == ["spans[2]"]
        assert only(edit(lambda d: _two_shots(d, 1.0, 1.0, push=0.2)), "W03") == []

    def test_edl_ranges_w03_another_camera_or_a_screen_between_is_no_flat_cut(self) -> None:
        assert only(edit(lambda d: None), "W03") == []  # the example cuts to a2 and to a screen

    def test_edl_ranges_w04_a_synchronized_shot_across_a_voice_cut(self) -> None:
        issues = check(edit(lambda d: _cut_inside_a_shot(d, 200)))
        assert [i.path for i in issues if i.code == "W04"] == ["spans[1]"]
        assert not [i for i in issues if i.level == "error"]

    def test_edl_ranges_w04_two_clips_that_go_on_in_the_source_are_not_a_cut(self) -> None:
        issues = check(edit(lambda d: _cut_inside_a_shot(d, 120)))
        assert "W04" not in codes(issues) and not [i for i in issues if i.level == "error"]

    def test_edl_ranges_w04_a_free_camera_does_not_care_about_the_voice_cut(self) -> None:
        def change(doc: Doc) -> None:
            _cut_inside_a_shot(doc, 200)
            doc["spans"][1]["src_f"] = 0

        assert "W04" not in codes(check(edit(change)))

    def test_edl_ranges_w05_a_look_on_a_color_span_is_ignored(self) -> None:
        assert only(edit(lambda d: d["spans"][0].update(look="calido")), "W05") == ["spans[0].look"]
        assert only(edit(lambda d: d["spans"][0].update(look=None)), "W05") == []
