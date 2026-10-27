"""The plan of mezzanines (spec S1.5b row 1, DS12, 001.15 T5): which ranges of each clip the spans
read, with their margin, and how big each one is. Pure: no ffmpeg runs here.
"""

from dataclasses import replace

import pytest

from kcut.edl.model import Edl
from kcut.ff.color import CHAIN_VERSION
from kcut.ingest.inventory import Inventory
from kcut.render.mezz import MezzJob, plan_mezz
from tests.unit.edl_fakes import Doc, config, edit, inventory, parsed
from tests.unit.mezz_build_cases import *  # noqa: F403  (001.25: 300-line rule)
from tests.unit.mezz_files_cases import *  # noqa: F403  (001.25: 300-line rule)
from tests.unit.mezz_land_cases import *  # noqa: F403  (001.26: 300-line rule)


def _jobs(edl: Edl | None = None, inv: Inventory | None = None) -> list[MezzJob]:
    return plan_mezz(edl or parsed(), inv or inventory(), config())


def _spans(clip_id: str, jobs: list[MezzJob]) -> list[tuple[int, int]]:
    return [(j.start_f, j.end_f) for j in jobs if j.clip_id == clip_id]


def _with_video(inv: Inventory, clip_id: str, **changes: object) -> Inventory:
    clips = tuple(
        replace(c, video=replace(c.video, **changes)) if c.id == clip_id and c.video else c
        for c in inv.clips
    )
    return replace(inv, clips=clips)


class TestTheExample:
    def test_mezz_plan_a1_has_three_ranges_and_none_covers_frame_zero(self) -> None:
        jobs = _jobs()
        assert _spans("a1", jobs) == [(45, 135), (195, 255), (285, 360)]
        assert all(j.start_f > 0 for j in jobs if j.clip_id == "a1")

    def test_mezz_plan_a2_is_one_range_shifted_by_the_sync_and_b1_has_two(self) -> None:
        jobs = _jobs()
        assert _spans("a2", jobs) == [(69, 189)]  # frames 120-209 of a1, minus 36 for +1200 ms
        assert _spans("b1", jobs) == [(0, 45), (75, 164)]  # the remap: 0-29 and 90, 92 ... 148

    def test_mezz_plan_the_order_is_the_one_of_the_first_span_that_reads_each_clip(self) -> None:
        assert [j.clip_id for j in _jobs()] == ["a1", "a1", "a1", "a2", "b1", "b1"]

    def test_mezz_short_tail_every_job_says_the_last_frame_the_spans_read_plus_one(self) -> None:
        needs = [(j.clip_id, j.start_f, j.end_f, j.need_end_f) for j in _jobs()]
        assert needs == [
            ("a1", 45, 135, 120),  # frames 60-119 of a1, and the margin of 15 on each side
            ("a1", 195, 255, 240),
            ("a1", 285, 360, 345),
            ("a2", 69, 189, 174),
            ("b1", 0, 45, 30),
            ("b1", 75, 164, 149),
        ]

    def test_mezz_plan_the_name_and_the_path_follow_the_spec(self) -> None:
        job = _jobs()[0]
        assert job.path == f".kcut/mezz/a1_45-135_1440x2560_{CHAIN_VERSION}.mp4"
        assert (job.clip_id, job.start_f, job.end_f, job.w, job.h) == ("a1", 45, 135, 1440, 2560)

    def test_mezz_plan_sizes_the_example_by_its_zoom_and_its_source(self) -> None:
        sizes = {(j.clip_id, j.w, j.h) for j in _jobs()}
        assert sizes == {("a1", 1440, 2560), ("a2", 1080, 1920), ("b1", 1894, 866)}

    def test_mezz_plan_the_chain_scales_to_the_size_and_names_the_color_work(self) -> None:
        by_clip = {j.clip_id: j.chain for j in _jobs()}
        assert "fps=30" in by_clip["a1"] and "scale=1440:2560" in by_clip["a1"]
        assert "scale=1894:866" in by_clip["b1"] and "setparams=" in by_clip["b1"]

    def test_mezz_plan_a_camera_that_is_hdr_gets_the_tone_map_chain(self) -> None:
        inv = _with_video(inventory(), "a2", hdr="hlg", color_transfer="arib-std-b67")
        chain = next(j.chain for j in _jobs(inv=inv) if j.clip_id == "a2")
        assert "tonemap=hable" in chain


class TestRanges:
    def _one_clip(self, frames: list[int], total: int = 360) -> Doc:
        """A free camera of a1 that reads exactly `frames` (one span each, a color between)."""

        def change(doc: Doc) -> None:
            spans: list[Doc] = []
            clips: list[Doc] = []
            at = 0
            for k, f in enumerate(frames):
                spans.append({"kind": "cam", "at_f": at, "dur_f": 1, "src": "a1", "src_f": f})
                clips.append({"kind": "gap", "at_f": at, "dur_f": 1, "why": str(k)})
                at += 1
            doc.update(frames=at, clips=clips, spans=spans)

        return edit(change)

    def test_mezz_plan_ranges_closer_than_two_seconds_are_one(self) -> None:
        # 100 and 159: 58 frames between them (< 60): one range; margin 15 each side
        jobs = _jobs(parsed(self._one_clip([100, 159])))
        assert _spans("a1", jobs) == [(85, 175)]

    def test_mezz_plan_ranges_two_seconds_apart_or_more_are_two(self) -> None:
        # the gap is 60 frames (not < 60): two ranges, each with its margin, which do not touch
        jobs = _jobs(parsed(self._one_clip([100, 161])))
        assert _spans("a1", jobs) == [(85, 116), (146, 177)]

    def test_mezz_plan_a_second_range_is_as_long_as_its_own_frames_and_margin(self) -> None:
        jobs = _jobs(parsed(self._one_clip([100, 161, 162])))
        assert _spans("a1", jobs) == [(85, 116), (146, 178)]  # [161, 163) and 15 each side

    def test_mezz_plan_ranges_whose_margins_touch_are_one_file(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # With the real gap of 2 s the margins can never meet (2 s - 2 * 0.5 s are left between
        # them), so the union of what touches is a guard. A gap of 1 s makes them meet.
        monkeypatch.setattr("kcut.render.mezz.MERGE_GAP_FACTOR", 1)
        doc = edit(
            lambda d: d.update(
                fps=24,
                frames=2,
                clips=[{"kind": "gap", "at_f": 0, "dur_f": 2, "why": "x"}],
                spans=[
                    {"kind": "cam", "at_f": 0, "dur_f": 1, "src": "a1", "src_f": 100},
                    {"kind": "cam", "at_f": 1, "dur_f": 1, "src": "a1", "src_f": 125},
                ],
            )
        )
        found = plan_mezz(parsed(doc), inventory(), config(fps=24))
        assert [(j.start_f, j.end_f) for j in found] == [(88, 138)]  # [101, 125): 24 apart

    def test_mezz_short_tail_the_need_is_the_last_frame_read_with_no_margin(self) -> None:
        def needs(frames: list[int]) -> list[tuple[int, int, int]]:
            jobs = _jobs(parsed(self._one_clip(frames)))
            return [(j.start_f, j.end_f, j.need_end_f) for j in jobs if j.clip_id == "a1"]

        assert needs([100, 159]) == [(85, 175, 160)]  # one range: its last frame is 159
        assert needs([100, 161]) == [(85, 116, 101), (146, 177, 162)]
        assert needs([3, 358]) == [(0, 19, 4), (343, 360, 359)]  # the end is cut by the clip, not
        assert needs([10, 11, 12]) == [(0, 28, 13)]  # the need is not

    def test_mezz_plan_the_margin_is_half_a_second_and_stays_inside_the_clip(self) -> None:
        jobs = _jobs(parsed(self._one_clip([3, 358])))
        assert _spans("a1", jobs) == [(0, 19), (343, 360)]

    def test_mezz_plan_a_range_never_starts_before_where_the_video_starts(self) -> None:
        inv = _with_video(inventory(), "a1", start_ms=500)  # vs_f = 15
        jobs = _jobs(parsed(self._one_clip([20, 200])), inv)
        assert _spans("a1", jobs) == [(15, 36), (185, 216)]
        assert min(s for s, _ in _spans("a1", jobs)) >= 15

    def test_mezz_plan_vs_f_is_rounded_to_a_frame(self) -> None:
        inv = _with_video(inventory(), "a1", start_ms=516)  # 15.48 frames: vs_f = 15
        assert _spans("a1", _jobs(parsed(self._one_clip([16])), inv)) == [(15, 32)]
        inv = _with_video(inventory(), "a1", start_ms=517)  # 15.51: vs_f = 16
        assert _spans("a1", _jobs(parsed(self._one_clip([16])), inv)) == [(16, 32)]

    def test_mezz_plan_the_frames_of_a_free_camera_and_of_a_synchronized_one_are_both_read(
        self,
    ) -> None:
        assert _spans("a1", _jobs())[0] == (45, 135)  # the synchronized one: frames 60-119
        free = self._one_clip([10, 11, 12])
        assert _spans("a1", _jobs(parsed(free))) == [(0, 28)]  # [10, 13) and 15 of margin

    def test_mezz_plan_an_edl_with_no_camera_has_no_mezzanines(self) -> None:
        doc = edit(
            lambda d: d.update(
                frames=30,
                clips=[{"kind": "gap", "at_f": 0, "dur_f": 30, "why": "x"}],
                spans=[{"kind": "color", "at_f": 0, "dur_f": 30, "color": "#000000"}],
            )
        )
        assert _jobs(parsed(doc)) == []


class TestSizes:
    def _zoomed(self, zoom: float, push: float = 0.0, src: str = "a1") -> Doc:
        def change(doc: Doc) -> None:
            doc.update(
                frames=10,
                clips=[{"kind": "gap", "at_f": 0, "dur_f": 10, "why": "x"}],
                spans=[{"kind": "cam", "at_f": 0, "dur_f": 10, "src": src, "src_f": 100,
                        "zoom": zoom, "push": push}],
            )  # fmt: skip

        return edit(change)

    def _big_inventory(self) -> Inventory:
        return _with_video(inventory(), "a1", w=2160, h=3840, display_w=2160, display_h=3840)

    def test_mezz_plan_a_4k_source_is_scaled_down_to_what_the_biggest_zoom_needs(self) -> None:
        job = _jobs(parsed(self._zoomed(1.0)), self._big_inventory())[0]
        assert (job.w, job.h) == (1080, 1920)  # H * 1 / 3840 = 0.5
        job = _jobs(parsed(self._zoomed(1.5)), self._big_inventory())[0]
        assert (job.w, job.h) == (1620, 2880)  # 1920 * 1.5 / 3840 = 0.75
        job = _jobs(parsed(self._zoomed(2.0, push=0.5)), self._big_inventory())[0]
        assert (job.w, job.h) == (2160, 3840)  # zoom 3.0 at the end: never above the source

    def test_mezz_plan_the_scale_never_goes_above_one(self) -> None:
        job = _jobs(parsed(self._zoomed(3.0, push=0.5)))[0]  # a1 is 1440x2560
        assert (job.w, job.h) == (1440, 2560)

    def test_mezz_plan_the_biggest_zoom_of_all_the_spans_of_a_clip_counts(self) -> None:
        def change(doc: Doc) -> None:
            doc.update(
                frames=20,
                clips=[{"kind": "gap", "at_f": 0, "dur_f": 20, "why": "x"}],
                spans=[
                    {"kind": "cam", "at_f": 0, "dur_f": 10, "src": "a1", "src_f": 0, "zoom": 1.0},
                    {"kind": "cam", "at_f": 10, "dur_f": 10, "src": "a1", "src_f": 0, "zoom": 1.5},
                ],
            )

        job = _jobs(parsed(edit(change)), self._big_inventory())[0]
        assert (job.w, job.h) == (1620, 2880)

    def test_mezz_plan_a_wide_source_uses_the_height_of_the_biggest_picture_that_fits(self) -> None:
        wide = _with_video(inventory(), "a1", w=3840, h=2160, display_w=3840, display_h=2160)
        job = _jobs(parsed(self._zoomed(1.0)), wide)[0]
        # cover_box of 3840x2160 for 9:16 is 1215x2160: s = 1920 / 2160 = 0.889
        assert (job.w, job.h) == (3414, 1920)

    def test_mezz_plan_a_screen_is_kept_up_to_3840_on_its_long_side(self) -> None:
        big = _with_video(inventory(), "b1", w=7680, h=2160, display_w=7680, display_h=2160)
        sizes = {(j.w, j.h) for j in _jobs(inv=big) if j.clip_id == "b1"}
        assert sizes == {(3840, 1080)}
        small = {(j.w, j.h) for j in _jobs() if j.clip_id == "b1"}
        assert small == {(1894, 866)}

    def test_mezz_plan_sizes_are_even(self) -> None:
        odd = _with_video(inventory(), "b1", w=1895, h=867, display_w=1895, display_h=867)
        for job in _jobs(inv=odd):
            assert job.w % 2 == 0 and job.h % 2 == 0
        assert {(j.w, j.h) for j in _jobs(inv=odd) if j.clip_id == "b1"} == {(1896, 868)}

    def test_mezz_plan_a_clip_that_is_a_picture_and_a_screen_takes_the_bigger_size(self) -> None:
        def change(doc: Doc) -> None:
            doc.update(
                frames=20,
                clips=[{"kind": "gap", "at_f": 0, "dur_f": 20, "why": "x"}],
                spans=[
                    {"kind": "cam", "at_f": 0, "dur_f": 10, "src": "b1", "src_f": 0},
                    {"kind": "screen", "at_f": 10, "dur_f": 10, "src": "b1", "src_f": 0,
                     "keys": [{"at_f": 0, "crop": [0.5, 0.5, 1.0], "card": [1000, 500]}]},
                ],
            )  # fmt: skip

        job = _jobs(parsed(edit(change)))[0]
        assert (job.w, job.h) == (1894, 866)  # the screen wants it whole; the cam wanted 0.89

    def test_mezz_plan_the_display_size_is_the_one_that_counts_for_a_rotated_clip(self) -> None:
        rotated = _with_video(
            inventory(), "a1", w=2560, h=1440, display_w=1440, display_h=2560, rotation=-90
        )
        job = _jobs(inv=rotated)[0]
        assert (job.w, job.h) == (1440, 2560)

    @pytest.mark.parametrize("fps", [24, 25, 30, 48, 50, 60])
    def test_mezz_plan_the_margin_and_the_gap_follow_the_fps(self, fps: int) -> None:
        doc = edit(
            lambda d: d.update(
                fps=fps,
                frames=2,
                clips=[{"kind": "gap", "at_f": 0, "dur_f": 2, "why": "x"}],
                spans=[
                    {"kind": "cam", "at_f": 0, "dur_f": 1, "src": "a1", "src_f": 200},
                    {"kind": "cam", "at_f": 1, "dur_f": 1, "src": "a1", "src_f": 201 + 2 * fps},
                ],
            )
        )
        found = plan_mezz(parsed(doc), inventory(), config(fps=fps))
        margin = fps // 2
        assert [(j.start_f, j.end_f) for j in found] == [
            (200 - margin, 201 + margin),
            (201 + 2 * fps - margin, 202 + 2 * fps + margin),
        ]
