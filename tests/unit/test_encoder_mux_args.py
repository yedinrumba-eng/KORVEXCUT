"""The ffmpeg commands of the encoder and the mux (spec S1.5b), built without running anything."""

from pathlib import Path

from kcut.pipeline.mux import mux_args
from kcut.render.encoder import encoder_args

FFMPEG = Path("C:/fake/ffmpeg.exe")


class TestEncoderArgs:
    def test_encoder_args_are_the_ones_of_the_spec_in_order(self) -> None:
        args = encoder_args(FFMPEG, Path("C:/p/video.partial.mp4"), 1080, 1920, 30)
        assert args == [
            str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1080x1920", "-r", "30", "-i", "-",
            "-vf",
            "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
            "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-g", "60",
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-color_range", "tv",
            "-movflags", "+faststart",
            str(Path("C:/p/video.partial.mp4")),
        ]  # fmt: skip

    def test_encoder_args_the_keyframe_interval_is_two_seconds(self) -> None:
        for fps in (24, 25, 30, 48, 50, 60):
            args = encoder_args(FFMPEG, Path("x.partial.mp4"), 1080, 1920, fps)
            assert args[args.index("-g") + 1] == str(2 * fps)
            assert args[args.index("-r") + 1] == str(fps)

    def test_encoder_args_the_size_is_the_one_asked_for(self) -> None:
        args = encoder_args(FFMPEG, Path("x.partial.mp4"), 1920, 1080, 30)
        assert args[args.index("-s") + 1] == "1920x1080"

    def test_encoder_args_y_only_for_a_partial_file(self) -> None:
        assert "-y" in encoder_args(FFMPEG, Path("v.partial.mp4"), 2, 2, 30)
        assert "-y" not in encoder_args(FFMPEG, Path("v.mp4"), 2, 2, 30)

    def test_encoder_args_every_item_is_a_string_and_the_binary_is_first(self) -> None:
        args = encoder_args(FFMPEG, Path("v.partial.mp4"), 2, 2, 30)
        assert all(isinstance(item, str) for item in args) and args[0] == str(FFMPEG)
        assert args[-1].endswith("v.partial.mp4") and args[args.index("-i") + 1] == "-"


class TestMuxArgs:
    def test_mux_args_the_raw_voice_comes_with_its_format_before_its_input(self) -> None:
        args = mux_args(
            FFMPEG, Path("C:/b/video.mp4"), Path("C:/b/voice_raw.f32"),
            Path("C:/b/render.partial.mp4"), audio_f32=True,
        )  # fmt: skip
        assert args == [
            str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-i", str(Path("C:/b/video.mp4")),
            "-f", "f32le", "-ar", "48000", "-ac", "1", "-i", str(Path("C:/b/voice_raw.f32")),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            str(Path("C:/b/render.partial.mp4")),
        ]  # fmt: skip

    def test_mux_args_a_file_with_a_header_has_no_format_flags(self) -> None:
        args = mux_args(FFMPEG, Path("v.mp4"), Path("a.wav"), Path("o.mp4"), audio_f32=False)
        assert "f32le" not in args and "-y" not in args
        assert args.count("-i") == 2 and args.count("-ar") == 1

    def test_mux_args_the_video_is_copied_and_never_re_encoded(self) -> None:
        args = mux_args(FFMPEG, Path("v.mp4"), Path("a.f32"), Path("o.partial.mp4"), audio_f32=True)
        assert args[args.index("-c:v") + 1] == "copy"
        assert "libx264" not in args
