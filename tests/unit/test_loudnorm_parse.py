"""The parsers of the two measurements (spec S1.8b row 3, 001.15 T3): the JSON of the first pass of
`loudnorm` and the `Summary` of `ebur128`. The texts are what ffmpeg 8.1.1 printed (a sine of 3 s,
and `anullsrc` for the silence), cut to what the parsers read.
"""

import pytest

from kcut.audio.loudnorm import EburMeasure, LoudnormMeasure, parse_ebur128, parse_pass1
from kcut.errors import ToolError

LOUDNORM = """\
[Parsed_loudnorm_0 @ 000001f5f5697140]
{
\t"input_i" : "-21.75",
\t"input_tp" : "-18.06",
\t"input_lra" : "0.00",
\t"input_thresh" : "-31.75",
\t"output_i" : "-15.95",
\t"output_tp" : "-12.27",
\t"output_lra" : "0.00",
\t"output_thresh" : "-25.95",
\t"normalization_type" : "dynamic",
\t"target_offset" : "-0.05"
}
[out#0/null @ 000001f5f5697c00] video:0KiB audio:1125KiB
"""
LOUDNORM_SILENCE = LOUDNORM.replace('"-21.75"', '"-inf"').replace('"-0.05"', '"inf"')
EBUR = """\
[Parsed_ebur128_0 @ 0000027235b30a00] Summary:

  Integrated loudness:
    I:         -21.8 LUFS
    Threshold: -31.8 LUFS

  Loudness range:
    LRA:        20.0 LU
    Threshold: -41.8 LUFS
    LRA low:   -41.8 LUFS
    LRA high:  -21.8 LUFS

  True peak:
    Peak:      -18.1 dBFS
[out#0/null @ 0000027235a94c00] video:0KiB audio:258KiB
"""


def test_loudnorm_parse_pass1_reads_the_five_numbers_the_second_pass_needs() -> None:
    assert parse_pass1(LOUDNORM) == LoudnormMeasure(-21.75, -18.06, 0.0, -31.75, -0.05)


def test_loudnorm_parse_pass1_takes_the_last_block() -> None:
    older = LOUDNORM.replace("-21.75", "-30.00")
    assert parse_pass1(older + "\nlines in between\n" + LOUDNORM) == parse_pass1(LOUDNORM)


@pytest.mark.parametrize("loudness", ["-inf", "nan", "-60.01", "-70.00"])
def test_loudnorm_parse_pass1_silence_is_none(loudness: str) -> None:
    assert parse_pass1(LOUDNORM.replace('"-21.75"', f'"{loudness}"')) is None


def test_loudnorm_parse_pass1_the_silence_that_ffmpeg_really_printed_is_none() -> None:
    """With `-inf` the other numbers can be `inf` too (`target_offset`): none of them is read."""
    assert parse_pass1(LOUDNORM_SILENCE) is None


def test_loudnorm_parse_pass1_minus_60_is_not_silence() -> None:
    found = parse_pass1(LOUDNORM.replace('"-21.75"', '"-60.00"'))
    assert found is not None and found.input_i == -60.0


@pytest.mark.parametrize(
    "text",
    ["", "no json here", "{}", '{"input_i": "-20"}', '{"input_i": "abc"}', "{ not json }"],
)
def test_loudnorm_parse_pass1_without_a_usable_block_is_a_tool_error(text: str) -> None:
    with pytest.raises(ToolError, match="loudnorm"):
        parse_pass1(text)


def test_loudnorm_parse_pass1_the_error_does_not_repeat_the_stderr() -> None:
    with pytest.raises(ToolError) as info:
        parse_pass1("C:/Users/Maria 809-555-1234/video.mov: Invalid data")
    assert "Maria" not in info.value.message_es and "809" not in info.value.message_es


def test_loudnorm_parse_ebur128_reads_i_tp_and_lra_of_the_summary() -> None:
    assert parse_ebur128(EBUR) == EburMeasure(-21.8, -18.1, 20.0)


def test_loudnorm_parse_ebur128_the_values_inf_and_nan_are_none() -> None:
    silent = EBUR.replace("-18.1 dBFS", "-inf dBFS").replace(
        "-21.8 LUFS\n    Thr", "nan LUFS\n    Thr"
    )
    assert parse_ebur128(silent) == EburMeasure(None, None, 20.0)


def test_loudnorm_parse_ebur128_a_summary_with_a_line_missing_has_none_there() -> None:
    without_peak = EBUR.replace("    Peak:      -18.1 dBFS\n", "")
    assert parse_ebur128(without_peak) == EburMeasure(-21.8, None, 20.0)


def test_loudnorm_parse_ebur128_takes_the_last_summary() -> None:
    older = EBUR.replace("-21.8 LUFS\n    Thr", "-30.0 LUFS\n    Thr")
    assert parse_ebur128(older + EBUR).I == -21.8


def test_loudnorm_parse_ebur128_the_lines_lra_low_and_high_are_not_the_range() -> None:
    assert parse_ebur128(EBUR).LRA == 20.0  # not -41.8 (LRA low) nor -21.8 (LRA high)


def test_loudnorm_parse_ebur128_without_a_summary_is_a_tool_error() -> None:
    with pytest.raises(ToolError, match="ebur128 no dio resumen"):
        parse_ebur128("Input #0, lavfi, from 'sine=d=3':\n  Duration: N/A\n")
