"""The command lines of `loudnorm` and `ebur128` (spec S1.8b row 9, 001.15 T3): the measurements
print their result at the `info` level, so `pass1_args` and `ebur128_args` go without `-loglevel`
and with `-nostats`; the second pass is not a measurement and keeps `-loglevel error`. Pure: nothing
is run here (the real ffmpeg is in `tests/integration/test_ebur128_live.py`).
"""

from pathlib import Path

import pytest

from kcut.audio.loudnorm import LoudnormMeasure, ebur128_args, pass1_args, pass2_args

FFMPEG = Path("C:/tools/ffmpeg.exe")
SRC, DST = Path("C:/p/in.f32"), Path("C:/p/out.f32.partial")
MEASURE = LoudnormMeasure(-21.75, -18.06, 3.5, -31.75, -0.05)


def test_loudnorm_args_pass1_is_at_info_level_with_nostats() -> None:
    args = pass1_args(FFMPEG, SRC, -16.0, -2.0, 11.0)
    assert "-loglevel" not in args
    assert args[:4] == [str(FFMPEG), "-hide_banner", "-nostdin", "-nostats"]
    assert args[4:] == [
        "-f", "f32le", "-ar", "48000", "-ac", "1", "-i", str(SRC),
        "-af", "loudnorm=I=-16:TP=-2:LRA=11:print_format=json", "-f", "null", "-",
    ]  # fmt: skip


def test_loudnorm_args_pass2_keeps_loglevel_error_and_gives_the_measure_back() -> None:
    args = pass2_args(FFMPEG, SRC, DST, -16.0, -2.0, 11.0, MEASURE)
    assert args[:5] == [str(FFMPEG), "-hide_banner", "-nostdin", "-loglevel", "error"]
    assert "-nostats" not in args and "-y" not in args
    spec = args[args.index("-af") + 1]
    assert spec == (
        "loudnorm=I=-16:TP=-2:LRA=11:measured_I=-21.75:measured_TP=-18.06:measured_LRA=3.5"
        ":measured_thresh=-31.75:offset=-0.05:linear=true:print_format=summary,aresample=48000"
    )
    assert args[args.index("-af") + 2 :] == [
        "-f", "f32le", "-ar", "48000", "-ac", "1", str(DST),
    ]  # fmt: skip


def test_loudnorm_args_ebur128_has_the_true_peak_a_quiet_frame_log_and_no_loglevel() -> None:
    inputs = ["-f", "lavfi", "-i", "sine=d=3"]
    args = ebur128_args(FFMPEG, inputs)
    assert args == [
        str(FFMPEG), "-hide_banner", "-nostdin", "-nostats", *inputs,
        "-map", "0:a:0", "-af", "ebur128=peak=true:framelog=quiet", "-f", "null", "-",
    ]  # fmt: skip
    assert "-loglevel" not in args


def test_loudnorm_args_the_numbers_are_written_with_fnum() -> None:
    spec = pass1_args(FFMPEG, SRC, -14.5, -1.5, 11.0)[-4]
    assert spec == "loudnorm=I=-14.5:TP=-1.5:LRA=11:print_format=json"


def test_loudnorm_args_a_nan_never_reaches_the_command_line() -> None:
    with pytest.raises(ValueError, match="no finito"):
        pass1_args(FFMPEG, SRC, float("nan"), -1.5, 11.0)
