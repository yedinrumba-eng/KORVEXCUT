"""The argument lists of the frame reader and the proxy index (spec S1.4, 001.15). Nothing runs."""

from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.ff.reader import proxy_index, reader_args, seek_input
from kcut.ingest.inventory import Clip
from tests.unit.media_fakes import make_video

FFMPEG = Path("C:/tools/ffmpeg.exe")
RGB = "scale=in_color_matrix=bt709:in_range=tv,format=rgb24"


def _clip(start_ms: int | None) -> Clip:
    video = None if start_ms is None else make_video(start_ms=start_ms)
    return Clip("a1", "crudo/cam.mp4", "cam", "video_voz", "sha256:aaaaaaaa", 10, 4000, 120, video)


class TestSeekInput:
    def test_seek_input_lands_a_quarter_of_a_frame_before_the_frame(self) -> None:
        path = Path("C:/p/a b.mp4")
        assert seek_input(path, 90, 30) == ["-ss", "2.991667", "-i", str(path)]

    def test_seek_input_the_first_frame_is_time_zero_not_negative(self) -> None:
        assert seek_input(Path("x.mp4"), 0, 30)[:2] == ["-ss", "0"]

    @pytest.mark.parametrize(("start_f", "fps", "text"), [(1, 30, "0.025"), (60, 24, "2.489583")])
    def test_seek_input_other_frames(self, start_f: int, fps: int, text: str) -> None:
        assert seek_input(Path("x.mp4"), start_f, fps)[1] == text


class TestReaderArgs:
    def test_reader_args_a_file_with_the_explicit_bt709_matrix(self) -> None:
        inputs = seek_input(Path("clip.mp4"), 90, 30)
        args = reader_args(FFMPEG, inputs, 5)
        assert args == [
            str(FFMPEG),
            *("-hide_banner", "-nostdin", "-loglevel", "error"),
            *inputs,
            *("-map", "0:v:0", "-an", "-frames:v", "5"),
            *("-vf", f"{RGB},format=bgr24"),
            *("-f", "rawvideo", "-"),
        ]

    def test_reader_args_rgb_filters_sit_between_the_two_conversions(self) -> None:
        args = reader_args(FFMPEG, ["-i", "x.mp4"], 1, rgb_filters="eq=saturation=1.2")
        assert args[args.index("-vf") + 1] == f"{RGB},eq=saturation=1.2,format=bgr24"

    def test_reader_args_pre_filters_come_before_the_conversion(self) -> None:
        args = reader_args(FFMPEG, ["-i", "x.mp4"], 3, pre_filters="fps=1/2:round=up")
        assert args[args.index("-vf") + 1] == f"fps=1/2:round=up,{RGB},format=bgr24"

    def test_reader_args_both_kinds_of_filter_keep_their_places(self) -> None:
        args = reader_args(FFMPEG, ["-i", "x"], 2, pre_filters="fps=2", rgb_filters="negate")
        assert args[args.index("-vf") + 1] == f"fps=2,{RGB},negate,format=bgr24"

    def test_reader_args_a_lavfi_input_goes_in_as_it_is(self) -> None:
        inputs = ["-f", "lavfi", "-i", "testsrc2=s=64x64:r=30:d=1"]
        args = reader_args(FFMPEG, inputs, 1)
        start = args.index("-f")
        assert args[start : start + 4] == inputs and args.count("-i") == 1

    def test_reader_args_maps_the_first_video_and_drops_audio(self) -> None:
        args = reader_args(FFMPEG, ["-i", "x.mp4"], 1)
        assert args[args.index("-map") + 1] == "0:v:0" and "-an" in args

    @pytest.mark.parametrize("count", [0, -1])
    def test_reader_args_needs_at_least_one_frame(self, count: int) -> None:
        with pytest.raises(ValueError):
            reader_args(FFMPEG, ["-i", "x.mp4"], count)

    def test_reader_args_is_all_strings_and_never_the_shell(self) -> None:
        args = reader_args(FFMPEG, seek_input(Path("x y.mp4"), 3, 30), 4)
        assert all(isinstance(a, str) for a in args) and isinstance(args, list)


class TestProxyIndex:
    def test_proxy_index_without_an_offset_is_the_frame_itself(self) -> None:
        assert proxy_index(_clip(0), 90, 30) == 90

    def test_proxy_index_subtracts_the_first_frame_of_video(self) -> None:
        # the video starts 0.5 s late: frame 15 of the clock is index 0 of the proxy
        assert proxy_index(_clip(500), 45, 30) == 30
        assert proxy_index(_clip(500), 15, 30) == 0
        assert proxy_index(_clip(500), 14, 30) == -1  # before the video: the caller refuses it

    def test_proxy_index_rounds_the_start_to_the_nearest_frame(self) -> None:
        assert proxy_index(_clip(49), 10, 30) == 9  # 1.47 frames -> 1
        assert proxy_index(_clip(51), 10, 30) == 8  # 1.53 frames -> 2

    def test_proxy_index_a_clip_without_video_is_a_project_error(self) -> None:
        with pytest.raises(ProjectError):
            proxy_index(_clip(None), 10, 30)
