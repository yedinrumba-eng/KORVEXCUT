"""From output frames to source frames and back (spec S1.5a): the shift between cameras, the frame
each kind of span reads, the speed of a remap (exact, with `Fraction`) and where a frame is heard.
"""

import random
from dataclasses import replace

import pytest

from kcut.edl.model import CamSpan, ColorSpan, Edl, RemapPoint, ScreenKey, ScreenSpan
from kcut.edl.timeline import (
    VoiceIndex,
    group_of,
    is_contiguous,
    shift_f,
    source_to_output,
    span_source_bounds,
    span_source_frames,
    voice_at,
)
from kcut.errors import ProjectError
from kcut.ingest.inventory import Inventory, SyncInfo, SyncMember
from tests.unit.edl_fakes import edit, inventory, parsed


def _with_offset(offset_ms: int) -> Inventory:
    member = SyncMember("a2", offset_ms, 0.9, 0.3, 3.0, 0, 0, "envelope+raw")
    return replace(inventory(), sync=SyncInfo("a1", (member,), ()))


def _screen(count: int, remap: tuple[RemapPoint, ...], src_f: int = 0) -> ScreenSpan:
    keys = (ScreenKey(0, (0.5, 0.5, 1.0), (1000, 500)),)
    return ScreenSpan(at_f=0, dur_f=count, src="b1", src_f=src_f, keys=keys, remap=remap)


class TestShift:
    def test_edl_timeline_a2_at_plus_4722_ms_is_minus_142_frames_at_30_fps(self) -> None:
        assert shift_f(_with_offset(4722), "a1", "a2", 30) == -142

    def test_edl_timeline_the_other_way_round_is_plus_142(self) -> None:
        assert shift_f(_with_offset(4722), "a2", "a1", 30) == 142

    def test_edl_timeline_the_shift_of_the_synthetic_cameras(self) -> None:
        assert shift_f(inventory(), "a1", "a2", 30) == -36  # +1200 ms

    def test_edl_timeline_the_same_clip_needs_no_sync(self) -> None:
        assert shift_f(inventory(), "a3", "a3", 30) == 0  # even one the sync rejected
        assert shift_f(inventory(), "a1", "a1", 24) == 0

    def test_edl_timeline_the_rounding_is_in_whole_frames_halves_up(self) -> None:
        inv = _with_offset(50)  # -1.5 frames at 30 fps
        assert shift_f(inv, "a1", "a2", 30) == -1
        assert shift_f(_with_offset(-50), "a1", "a2", 30) == 2  # +1.5

    def test_edl_timeline_two_clips_of_different_groups_have_no_shift(self) -> None:
        with pytest.raises(ProjectError, match="sincronizados"):
            shift_f(inventory(), "a1", "a3", 30)
        with pytest.raises(ProjectError, match="sincronizados"):
            shift_f(inventory(), "a3", "b1", 30)

    def test_edl_timeline_groups(self) -> None:
        inv = inventory()
        assert group_of(inv, "a1") == group_of(inv, "a2") == frozenset({"a1", "a2"})
        assert group_of(inv, "a3") == frozenset({"a3"}) and group_of(inv, "zz") == frozenset({"zz"})


class TestSourceFrames:
    def test_edl_timeline_a_synchronized_camera_reads_the_frame_the_voice_has(self) -> None:
        edl, inv = parsed(), inventory()
        frames = span_source_frames(edl, edl.spans[1], inv)  # a1 over its own voice, 30..90
        assert frames == [60 + k for k in range(60)]  # the voice clip starts at in_f = 60

    def test_edl_timeline_the_other_camera_is_moved_by_the_shift(self) -> None:
        edl, inv = parsed(), inventory()
        frames = span_source_frames(edl, edl.spans[2], inv)  # a2 over the voice, 90..180
        assert frames[0] == 60 + 60 - 36 and frames[-1] == frames[0] + 89 and len(frames) == 90

    def test_edl_timeline_a_synchronized_camera_follows_each_voice_clip(self) -> None:
        doc = edit(lambda d: None)
        doc["clips"][1:2] = [
            {"kind": "voice", "src": "a1", "at_f": 30, "in_f": 60, "out_f": 120, "why": "a"},
            {"kind": "voice", "src": "a1", "at_f": 90, "in_f": 200, "out_f": 320, "why": "b"},
        ]
        edl = parsed(doc)
        frames = span_source_frames(edl, edl.spans[1], inventory())  # 30..90: the first clip
        assert frames == list(range(60, 120))
        wide = replace(edl.spans[1], dur_f=90)
        assert isinstance(wide, CamSpan)
        jump = span_source_frames(edl, wide, inventory())  # 30..120: crosses the cut
        assert jump[:60] == list(range(60, 120)) and jump[60:] == list(range(200, 230))

    def test_edl_timeline_a_free_camera_plays_from_src_f_at_one_times(self) -> None:
        edl = parsed(edit(lambda d: d["spans"][1].update(src_f=100)))
        assert span_source_frames(edl, edl.spans[1], inventory()) == list(range(100, 160))

    def test_edl_timeline_a_screen_without_remap_plays_from_src_f(self) -> None:
        edl = parsed(edit(lambda d: d["spans"][4].pop("remap")))
        assert span_source_frames(edl, edl.spans[4], inventory()) == list(range(60))

    def test_edl_timeline_a_screen_remap_goes_from_the_last_point_at_its_speed(self) -> None:
        edl, inv = parsed(), inventory()
        frames = span_source_frames(edl, edl.spans[4], inv)
        assert frames[:30] == list(range(30))  # 1x from src_f 0
        assert frames[30:] == [90 + 2 * k for k in range(30)]  # 2x from src_f 90 at frame 30

    def test_edl_timeline_a_speed_of_029_for_100_frames_moves_29_not_28(self) -> None:
        assert int(100 * 0.29) == 28  # what a float does
        span = _screen(101, (RemapPoint(0, 0, 0.29),))
        frames = span_source_frames(parsed(), span, inventory())
        assert frames[100] - frames[0] == 29

    def test_edl_timeline_the_fractional_speeds_floor_each_frame(self) -> None:
        span = _screen(7, (RemapPoint(0, 10, 0.5),))
        assert span_source_frames(parsed(), span, inventory()) == [10, 10, 11, 11, 12, 12, 13]
        slow = _screen(5, (RemapPoint(0, 0, 0.25), RemapPoint(2, 50, 4.0)))
        assert span_source_frames(parsed(), slow, inventory()) == [0, 0, 50, 54, 58]

    def test_edl_timeline_a_color_span_reads_nothing(self) -> None:
        edl = parsed()
        assert isinstance(edl.spans[0], ColorSpan)
        assert span_source_frames(edl, edl.spans[0], inventory()) == []
        assert span_source_bounds(edl, edl.spans[0], inventory()) == []

    def test_edl_timeline_a_synchronized_camera_on_a_gap_cannot_be_read(self) -> None:
        edl = parsed()
        span = replace(edl.spans[1], at_f=0, dur_f=40)
        with pytest.raises(ProjectError, match="no tiene voz"):
            span_source_frames(edl, span, inventory())


class TestBounds:
    def test_edl_timeline_bounds_are_the_first_and_the_last_frame_of_each_stretch(self) -> None:
        edl, inv = parsed(), inventory()
        assert span_source_bounds(edl, edl.spans[1], inv) == [(60, 119)]
        assert span_source_bounds(edl, edl.spans[4], inv) == [(0, 29), (90, 148)]

    def test_edl_timeline_bounds_agree_with_the_list_of_frames(self) -> None:
        rng = random.Random(7)
        for _ in range(200):
            points = [RemapPoint(0, rng.randrange(50), rng.choice([0.25, 0.29, 1.0, 1.5, 3.7]))]
            for at in sorted(rng.sample(range(1, 80), rng.randrange(0, 4))):
                points.append(RemapPoint(at, rng.randrange(300), rng.choice([0.5, 1.0, 2.0, 4.0])))
            span = _screen(rng.randrange(1, 90), tuple(points), points[0].src_f)
            frames = span_source_frames(parsed(), span, inventory())
            bounds = span_source_bounds(parsed(), span, inventory())
            assert min(b[0] for b in bounds) == min(frames)
            assert max(b[1] for b in bounds) == max(frames)

    def test_edl_timeline_bounds_do_not_make_a_list(self) -> None:
        edl = parsed()
        span = replace(edl.spans[1], src_f=5, dur_f=10**12)
        assert span_source_bounds(edl, span, inventory()) == [(5, 5 + 10**12 - 1)]


class TestVoiceAndMapping:
    def test_edl_timeline_voice_at(self) -> None:
        edl = parsed()
        assert voice_at(edl, 29) is None and voice_at(edl, 30) is edl.clips[1]
        assert voice_at(edl, 209) is edl.clips[1] and voice_at(edl, 210) is None
        assert voice_at(edl, 270) is edl.clips[3] and voice_at(edl, 345) is None

    def test_edl_timeline_source_to_output_where_a_frame_is_heard(self) -> None:
        edl = parsed()
        assert source_to_output(edl, "a1", 60) == [30] and source_to_output(edl, "a1", 239) == [209]
        assert source_to_output(edl, "a1", 240) == [] and source_to_output(edl, "a1", 59) == []
        assert source_to_output(edl, "a1", 300) == [270]
        assert source_to_output(edl, "a2", 60) == []

    def test_edl_timeline_a_frame_used_twice_is_heard_twice(self) -> None:
        doc = edit(lambda d: d["clips"][3].update(in_f=100, out_f=145))
        assert source_to_output(parsed(doc), "a1", 120) == [30 + 60, 270 + 20]

    def test_edl_timeline_the_index_finds_the_clips_that_overlap(self) -> None:
        index = VoiceIndex(parsed())
        assert [i for i, _ in index.overlapping(0, 30)] == [0]
        assert [i for i, _ in index.overlapping(29, 31)] == [0, 1]
        assert [i for i, _ in index.overlapping(100, 300)] == [1, 2, 3]
        assert index.overlapping(345, 400) == []

    def test_edl_timeline_contiguous(self) -> None:
        edl = parsed()
        assert is_contiguous(edl.clips)
        assert not is_contiguous(replace(edl, clips=edl.clips[1:]).clips)
        broken = parsed(edit(lambda d: d["clips"][2].update(at_f=215)))
        assert not is_contiguous(broken.clips) and is_contiguous(())


def test_edl_timeline_an_edl_object_is_what_the_functions_take() -> None:
    assert isinstance(parsed(), Edl)
