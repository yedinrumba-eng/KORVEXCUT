"""The numbers of an EDL (spec S1.5a, 001.15): voice inside the real audio (E06), a contiguous
timeline (E07, E09), sums (E08), source frames inside their clip (E12), ranges (E13), keys and remap
(E15, E18), fades (E17) and the warnings W01 to W05. Every code of the table has a case here.
"""

import time
from dataclasses import replace

import pytest

from kcut.edl import refs
from kcut.edl.model import Edl
from kcut.edl.ranges import check_ranges
from kcut.edl.refs import SourceStatus
from kcut.edl.timeline import VoiceIndex
from kcut.edl.validate import validate
from kcut.ingest.inventory import Inventory
from kcut.issues import exit_code
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
        # 001.24 point 9: `check` keeps `{}` (it used to turn it into the default map), so this
        # goes through the `real is None` branch; without that guard it is a TypeError
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


def _big_doc(n: int) -> Doc:
    """`n` voice clips of 3 frames and `n` synchronized cameras over them (a1 and a2 by turns)."""
    doc = edit(lambda d: None)
    doc["frames"] = 3 * n
    doc["clips"] = [
        {"kind": "voice", "at_f": 3 * i, "src": "a1", "in_f": 60 + i % 200, "why": "x",
         "out_f": 63 + i % 200}
        for i in range(n)
    ]  # fmt: skip
    doc["spans"] = [
        {"kind": "cam", "at_f": 3 * i, "dur_f": 3, "src": "a1" if i % 2 else "a2",
         "zoom": 1.0 + (i % 5) * 0.1}
        for i in range(n)
    ]  # fmt: skip
    return doc


class TestScale:
    """001.24 point 4 (S1.5b row 21): the check is linear. The voice index is made once, each
    source is judged once, and the inventory is searched with a dict."""

    def test_edl_scale_ten_thousand_clips_and_spans_validate_in_under_five_seconds(self) -> None:
        edl = parsed(_big_doc(10_000))
        started = time.monotonic()
        issues = validate(edl, inventory(), config(), 1, {"a1": 360, "a2": 360})
        assert time.monotonic() - started < 5.0
        assert {i.code for i in issues} <= {"W01", "W03", "W04"}  # a real check, no errors

    def test_edl_scale_the_work_does_not_grow_faster_than_the_edl(self) -> None:
        def seconds(n: int) -> float:
            edl = parsed(_big_doc(n))
            started = time.perf_counter()
            validate(edl, inventory(), config(), 1, {"a1": 360, "a2": 360})
            return time.perf_counter() - started

        small, large = seconds(1_000), seconds(8_000)
        assert large < 8 * small * 4 + 0.2  # 8 times the size: nowhere near 64 times the time

    def test_edl_scale_the_index_and_the_status_are_made_once_per_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        made = {"index": 0, "status": 0}
        original_index, original_status = VoiceIndex.__init__, refs.source_status

        def counting_index(self: VoiceIndex, edl: Edl) -> None:
            made["index"] += 1
            original_index(self, edl)

        def counting_status(edl: Edl, inv: Inventory) -> SourceStatus:
            made["status"] += 1
            return original_status(edl, inv)

        monkeypatch.setattr(VoiceIndex, "__init__", counting_index)
        monkeypatch.setattr("kcut.edl.validate.source_status", counting_status)
        validate(parsed(_big_doc(200)), inventory(), config(), 1, audio_f())
        assert made == {"index": 1, "status": 1}

    def test_edl_scale_a_source_used_many_times_is_one_name_and_one_e04(self) -> None:
        doc = _big_doc(300)
        doc["sources"].pop("a2")
        issues = check(doc)
        assert [i.code for i in issues].count("E04") == 1


class TestEmptyEdl:
    """001.24 point 10 (S1.5b row 27): `frames` is at least 1 (E13); an EDL with nothing in it
    is an error, whatever else adds up."""

    @pytest.mark.parametrize("frames", [0, -1, -345])
    def test_edl_empty_frames_under_one_is_e13(self, frames: int) -> None:
        issues = check(edit(lambda d: d.update(frames=frames)))
        assert [i.path for i in issues if i.code == "E13"] == ["frames"]

    def test_edl_empty_one_frame_is_the_least_that_passes_e13(self) -> None:
        doc = edit(
            lambda d: d.update(
                frames=1,
                clips=[{"kind": "gap", "at_f": 0, "dur_f": 1, "why": "x"}],
                spans=[{"kind": "color", "at_f": 0, "dur_f": 1, "color": "#000000"}],
            )
        )
        assert "E13" not in codes(check(doc))

    def test_edl_empty_an_edl_with_no_clips_and_no_spans_exits_1(self) -> None:
        doc = edit(lambda d: d.update(frames=0, clips=[], spans=[]))
        issues = check(doc)
        assert codes(issues) == ["E13"]  # the sums are 0 = 0: only the frames are wrong
        assert exit_code(issues) == 1

    def test_edl_empty_the_frames_error_is_in_check_ranges_too(self) -> None:
        edl = parsed(edit(lambda d: d.update(frames=0, clips=[], spans=[])))
        issues = check_ranges(edl, inventory(), config(), audio_f())
        assert [(i.code, i.path) for i in issues] == [("E13", "frames")]


class TestFramesCap:
    """001.25 point 4 (S1.5b row 35): `frames` is at most `floor(ingest.max_duration_h * 3600 *
    fps)`, so a render cannot ask for days of video with its lock taken."""

    @staticmethod
    def _at(frames: int) -> list[str]:
        edl = parsed(edit(lambda d: d.update(frames=frames)))
        issues = check_ranges(edl, inventory(), config(), audio_f())
        return [i.path for i in issues if i.code == "E13"]

    def test_edl_frames_cap_twelve_hours_at_30_fps_is_the_last_that_passes(self) -> None:
        assert self._at(12 * 3600 * 30) == []
        assert self._at(12 * 3600 * 30 + 1) == ["frames"]

    def test_edl_frames_cap_a_billion_frames_is_e13_and_exit_1_without_waiting(self) -> None:
        issues = check(edit(lambda d: d.update(frames=1_000_000_000)))
        assert [i.path for i in issues if i.code == "E13"] == ["frames"]
        assert exit_code(issues) == 1

    def test_edl_frames_cap_the_message_says_the_cap_and_where_it_comes_from(self) -> None:
        edl = parsed(edit(lambda d: d.update(frames=2_000_000)))
        (issue,) = [
            i for i in check_ranges(edl, inventory(), config(), audio_f()) if i.code == "E13"
        ]
        assert "1296000" in issue.message_es and "ingest.max_duration_h (12 h)" in issue.message_es

    def test_edl_frames_cap_it_follows_the_max_duration_of_the_config(self) -> None:
        cfg = config()
        short = replace(cfg, ingest=replace(cfg.ingest, max_duration_h=0.5))  # 54 000 frames
        for frames, wanted in ((54_000, []), (54_001, ["frames"])):
            edl = parsed(edit(lambda d, f=frames: d.update(frames=f)))
            issues = check_ranges(edl, inventory(), short, audio_f())
            assert [i.path for i in issues if i.code == "E13"] == wanted

    def test_edl_frames_cap_it_follows_the_fps_of_the_edl(self) -> None:
        def at_24(frames: int) -> list[str]:
            edl = parsed(edit(lambda d: d.update(fps=24, frames=frames)))
            issues = check_ranges(edl, inventory(), config(fps=24), audio_f())
            return [i.path for i in issues if i.code == "E13"]

        assert at_24(12 * 3600 * 24) == [] and at_24(12 * 3600 * 24 + 1) == ["frames"]
