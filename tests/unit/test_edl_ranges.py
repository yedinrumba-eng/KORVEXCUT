"""The numbers of an EDL (spec S1.5a, 001.15): voice inside the real audio (E06), a contiguous
timeline (E07, E09), sums (E08), source frames inside their clip (E12), ranges (E13), keys and remap
(E15, E18), fades (E17) and the warnings W01 to W05. Every code of the table has a case here.
"""

from dataclasses import replace

from kcut.edl.ranges import check_ranges
from kcut.ingest.inventory import Inventory
from tests.unit.edl_cases_fields import *  # noqa: F403
from tests.unit.edl_fakes import Doc, audio_f, check, codes, config, edit, inventory, only, parsed
from tests.unit.media_fakes import make_video


def _late_a1(start_ms: int) -> Inventory:
    """The inventory where the video of a1 starts `start_ms` after the container (spec 0.6)."""
    inv = inventory()
    clips = tuple(
        replace(c, video=make_video(start_ms=start_ms)) if c.id == "a1" else c for c in inv.clips
    )
    return replace(inv, clips=clips)


class TestTheExample:
    def test_edl_ranges_the_example_has_no_error_and_only_w01_in_spans_3(self) -> None:
        issues = check()
        assert [(i.code, i.path, i.level) for i in issues] == [("W01", "spans[3]", "warning")]
        assert "1440x2560" in issues[0].message_es and "1.12" in issues[0].message_es

    def test_edl_ranges_it_can_be_called_without_the_references(self) -> None:
        assert [i.code for i in check_ranges(parsed(), inventory(), config(), audio_f())] == ["W01"]


class TestVoice:
    def test_edl_ranges_e06_in_before_zero_and_out_not_after_in(self) -> None:
        assert only(edit(lambda d: d["clips"][1].update(in_f=-1)), "E06") == ["clips[1]"]
        assert only(edit(lambda d: d["clips"][1].update(out_f=60)), "E06") == ["clips[1]"]
        assert only(edit(lambda d: d["clips"][1].update(out_f=10)), "E06") == ["clips[1]"]

    def test_edl_ranges_e06_real_audio_out_past_the_audio_names_the_clip(self) -> None:
        # the inventory says 360 frames, but the wav16 only has 300: audio_f is 300
        issues = check(
            edit(lambda d: d["clips"][3].update(out_f=345)), audio={"a1": 300, "a2": 360}
        )
        e06 = [i for i in issues if i.code == "E06"]
        assert [i.path for i in e06] == ["clips[3]"] and "'a1'" in e06[0].message_es
        assert "300" in e06[0].message_es

    def test_edl_ranges_e06_real_audio_the_last_frame_of_the_audio_is_fine(self) -> None:
        assert only(edit(lambda d: None), "E06", audio={"a1": 345, "a2": 360}) == []
        assert only(edit(lambda d: None), "E06", audio={"a1": 344, "a2": 360}) == ["clips[3]"]

    def test_edl_ranges_e06_a_source_without_a_known_length_is_not_a_crash(self) -> None:
        assert only(edit(lambda d: None), "E06", audio={}) == []

    def test_edl_ranges_w02_a_voice_of_less_than_three_frames(self) -> None:
        def change(doc: Doc) -> None:
            doc["clips"][3].update(in_f=300, out_f=302)
            doc["clips"][3]["why"] = "chasquido"

        assert "W02" in codes(check(edit(change)))
        assert "W02" not in codes(check(edit(lambda d: d["clips"][3].update(out_f=303))))

    def test_edl_ranges_w02_is_not_added_to_an_e06(self) -> None:
        issues = check(edit(lambda d: d["clips"][3].update(out_f=300)))
        assert "E06" in codes(issues) and "W02" not in codes(issues)


class TestTimeline:
    def test_edl_ranges_e07_clips_that_do_not_follow(self) -> None:
        assert only(edit(lambda d: d["clips"][2].update(at_f=215, dur_f=55)), "E07") == ["clips[2]"]
        assert only(edit(lambda d: d["clips"][0].update(at_f=1, dur_f=29)), "E07") == ["clips[0]"]
        # a clip pushed 5 frames late without shortening: it and the next one that it overlaps
        assert only(edit(lambda d: d["clips"][2].update(at_f=215)), "E07") == [
            "clips[2]",
            "clips[3]",
        ]

    def test_edl_ranges_e07_one_hole_is_one_finding(self) -> None:
        assert only(edit(lambda d: d["clips"][2].update(at_f=215, dur_f=55)), "E07") == ["clips[2]"]

    def test_edl_ranges_e08_the_clips_and_the_spans_must_add_up_to_frames(self) -> None:
        assert only(edit(lambda d: d.update(frames=346)), "E08") == ["clips", "spans"]
        assert only(edit(lambda d: d["clips"][4].update(dur_f=31)), "E08") == ["clips"]
        assert only(edit(lambda d: d["spans"][6].update(dur_f=29)), "E08") == ["spans"]

    def test_edl_ranges_e09_spans_that_do_not_follow_or_have_no_length(self) -> None:
        assert only(edit(lambda d: d["spans"][3].update(at_f=181, dur_f=29)), "E09") == ["spans[3]"]
        assert only(edit(lambda d: d["spans"][0].update(dur_f=0)), "E09") == [
            "spans[0]",
            "spans[1]",
        ]
        assert only(edit(lambda d: d["spans"][0].update(dur_f=-5)), "E09")[0] == "spans[0]"

    def test_edl_ranges_e13_a_gap_needs_at_least_a_frame(self) -> None:
        assert "clips[0].dur_f" in only(edit(lambda d: d["clips"][0].update(dur_f=0)), "E13")


class TestSourceFrames:
    def test_edl_ranges_e12_a_free_camera_past_the_end_of_its_clip(self) -> None:
        def change(doc: Doc) -> None:
            doc["spans"][1].update(src_f=310)  # 60 frames from 310 reach 369; a1 has 360

        assert only(edit(change), "E12") == ["spans[1]"]
        assert only(edit(lambda d: d["spans"][1].update(src_f=300)), "E12") == []  # 300..359

    def test_edl_ranges_e12_a_screen_remap_past_the_end(self) -> None:
        def change(doc: Doc) -> None:
            doc["spans"][4]["remap"][1].update(src_f=200)  # 200 + 29 * 2 = 258 > 239

        assert only(edit(change), "E12") == ["spans[4]"]

    def test_edl_ranges_e12_a_synchronized_camera_whose_shifted_frames_leave_the_clip(self) -> None:
        def change(doc: Doc) -> None:
            doc["clips"][1].update(in_f=0, out_f=180)  # a2 would read a1 frame - 36 = -36
            doc["spans"][1].update(src="a2")
            doc["sources"]["a2"] = {"qhash": "sha256:bbbbbbbb"}

        assert "spans[1]" in only(edit(change), "E12")

    def test_edl_ranges_e12_video_frames_start_where_the_video_starts(self) -> None:
        def change(doc: Doc) -> None:
            doc["spans"][1].update(src_f=14)  # a1 starts at frame 15: frame 14 has no picture

        assert only(edit(change), "E12", inv=_late_a1(500)) == ["spans[1]"]
        assert only(edit(lambda d: d["spans"][1].update(src_f=15)), "E12", inv=_late_a1(500)) == []
        assert only(edit(lambda d: d["spans"][1].update(src_f=14)), "E12") == []  # starts at 0

    def test_edl_ranges_e12_a_negative_start_is_out_too(self) -> None:
        assert only(edit(lambda d: d["spans"][1].update(src_f=-1)), "E12") == ["spans[1]"]

    def test_edl_ranges_e12_a_span_of_a_billion_frames_is_judged_without_making_a_list(
        self,
    ) -> None:
        def change(doc: Doc) -> None:
            doc["spans"][1].update(src_f=0, dur_f=10**9)

        assert "spans[1]" in only(edit(change), "E12")
