"""The argument lists of the frame reader and the proxy index (spec S1.4, 001.15). Nothing runs."""

from pathlib import Path
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.ff import reader as reader_module
from kcut.ff.reader import FrameReader, proxy_index, reader_args, seek_input
from kcut.ingest.inventory import Clip
from tests.unit.media_fakes import make_video

FFMPEG = Path("C:/tools/ffmpeg.exe")
RGB = "scale=in_color_matrix=bt709:in_range=tv,format=rgb24"
SIZE = (540, 960)  # 001.22: the size the caller has checked, which seek_input asks for
MAX_PIXELS = "1036800"  # 2 * 540 * 960


def _clip(start_ms: int | None) -> Clip:
    video = None if start_ms is None else make_video(start_ms=start_ms)
    return Clip("a1", "crudo/cam.mp4", "cam", "video_voz", "sha256:aaaaaaaa", 10, 4000, 120, video)


class TestSeekInput:
    def test_seek_input_lands_a_quarter_of_a_frame_before_the_frame(self) -> None:
        path = Path("C:/p/a b.mp4")
        # 001.22: the size is asked for and `-max_pixels` sits between the seek and `-i`
        assert seek_input(path, 90, 30, SIZE) == [
            *("-ss", "2.991667", "-max_pixels", MAX_PIXELS, "-i", str(path)),
        ]

    def test_seek_input_the_first_frame_is_time_zero_not_negative(self) -> None:
        assert seek_input(Path("x.mp4"), 0, 30, SIZE)[:2] == ["-ss", "0"]  # 001.22: size

    @pytest.mark.parametrize(("start_f", "fps", "text"), [(1, 30, "0.025"), (60, 24, "2.489583")])
    def test_seek_input_other_frames(self, start_f: int, fps: int, text: str) -> None:
        assert seek_input(Path("x.mp4"), start_f, fps, SIZE)[1] == text  # 001.22: size

    @pytest.mark.parametrize(
        ("size", "pixels"),
        [
            ((540, 960), "1036800"),
            ((1080, 1920), "4147200"),
            ((1, 1), "2"),
            ((4096, 4096), "33554432"),
        ],
    )
    def test_seek_input_max_pixels_is_twice_the_pixels_of_the_size(
        self, size: tuple[int, int], pixels: str
    ) -> None:
        args = seek_input(Path("x.mp4"), 3, 30, size)
        assert args[args.index("-max_pixels") + 1] == pixels

    def test_seek_input_max_pixels_goes_before_the_input_it_limits(self) -> None:
        args = seek_input(Path("x.mp4"), 3, 30, SIZE)
        assert args.index("-max_pixels") < args.index("-i") == len(args) - 2

    def test_seek_input_max_pixels_lets_the_coded_size_of_the_proxy_through(self) -> None:
        coded = 576 * 960  # a proxy of 540x960 is coded in macroblocks of 16: 576 wide
        assert coded <= int(MAX_PIXELS)
        assert int(MAX_PIXELS) < 4 * 540 * 960  # a stream that grows to 4x is cut

    @pytest.mark.parametrize("size", [(0, 960), (540, 0), (-1, 5), (0, 0)])
    def test_seek_input_max_pixels_needs_a_size_that_exists(self, size: tuple[int, int]) -> None:
        with pytest.raises(ValueError):
            seek_input(Path("x.mp4"), 3, 30, size)


class TestReaderArgs:
    def test_reader_args_a_file_with_the_explicit_bt709_matrix(self) -> None:
        inputs = seek_input(Path("clip.mp4"), 90, 30, SIZE)  # 001.22: size
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
        args = reader_args(FFMPEG, seek_input(Path("x y.mp4"), 3, 30, SIZE), 4)  # 001.22: size
        assert all(isinstance(a, str) for a in args) and isinstance(args, list)


class TestFrameReaderMaxPixels:
    """001.22 point 8: the reader hands its size to `seek_input`, so ffmpeg starts with the cap."""

    def test_frame_reader_max_pixels_is_in_the_command_ffmpeg_is_started_with(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        started: list[list[str]] = []

        def popen(args: list[str], **kwargs: Any) -> None:
            started.append(args)
            raise RuntimeError("stop here: only the command was wanted")

        monkeypatch.setattr(reader_module.proc, "tool_path", lambda name: FFMPEG)
        monkeypatch.setattr(reader_module.proc, "popen", popen)
        with pytest.raises(RuntimeError, match="stop here"):
            FrameReader(Path("x.mp4"), 3, 1, 30, (300, 400), log=None)
        args = started[0]
        assert args[args.index("-max_pixels") + 1] == str(2 * 300 * 400)
        assert args.index("-max_pixels") < args.index("-i")


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
