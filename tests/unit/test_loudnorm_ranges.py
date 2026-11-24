"""`parse_pass1` checks the measure against the ranges that the second pass of `loudnorm` accepts
(spec 001.38, point 1; S1.9a row 11), and not only that it is a finite number.

ffmpeg 8.1.1 takes `measured_I` in -99..0, `measured_TP` in -99..99, `measured_LRA` in 0..99,
`measured_thresh` in -99..0 and `offset` in -99..99 (`ffmpeg -h filter=loudnorm`). A measure over
0 LUFS is a mix that is too loud: the plan has to change, so it is a CheckFailed (exit 1) that says
what to lower. Any other field out of range is a ToolError that does not repeat the stderr.
"""

import pytest

from kcut.audio.loudnorm import LoudnormMeasure, parse_pass1
from kcut.errors import CheckFailed, ToolError
from tests.unit.test_loudnorm_parse import LOUDNORM

TOO_LOUD = (
    "la mezcla pasa de 0 LUFS antes de normalizar; baja las ganancias de la música o de los efectos"
)
OUT_OF_RANGE = "loudnorm dio una medición fuera de rango"
FIELDS = {  # field: (what the fixture says, lowest accepted, highest accepted)
    "input_tp": ("-18.06", -99.0, 99.0),
    "input_lra": ("0.00", 0.0, 99.0),
    "input_thresh": ("-31.75", -99.0, 0.0),
    "target_offset": ("-0.05", -99.0, 99.0),
}


def _with(field: str, value: str) -> str:
    """The measure of the fixture with `field` set to `value`."""
    return LOUDNORM.replace(f'"{field}" : "{FIELDS[field][0]}"', f'"{field}" : "{value}"')


@pytest.mark.parametrize("loudness", ["0.01", "5.12", "+5.12", "99"])
def test_loudnorm_ranges_an_input_over_zero_lufs_is_a_check_failed_that_says_what_to_lower(
    loudness: str,
) -> None:
    with pytest.raises(CheckFailed) as info:
        parse_pass1(LOUDNORM.replace('"-21.75"', f'"{loudness}"'))
    assert info.value.message_es == TOO_LOUD and info.value.exit_code == 1


def test_loudnorm_ranges_zero_lufs_is_the_edge_and_it_is_accepted() -> None:
    found = parse_pass1(LOUDNORM.replace('"-21.75"', '"0.00"'))
    assert found == LoudnormMeasure(0.0, -18.06, 0.0, -31.75, -0.05)


@pytest.mark.parametrize("field", list(FIELDS))
def test_loudnorm_ranges_the_edges_of_every_field_are_accepted(field: str) -> None:
    _, low, high = FIELDS[field]
    for edge in (low, high):
        found = parse_pass1(_with(field, f"{edge:.2f}"))
        assert found is not None and getattr(found, field) == edge


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_tp", "99.01"),
        ("input_tp", "-99.01"),
        ("input_tp", "inf"),
        ("input_tp", "-inf"),
        ("input_tp", "nan"),
        ("input_lra", "-0.01"),
        ("input_lra", "99.01"),
        ("input_lra", "nan"),
        ("input_thresh", "0.01"),
        ("input_thresh", "-99.01"),
        ("input_thresh", "-inf"),
        ("target_offset", "99.01"),
        ("target_offset", "-99.01"),
        ("target_offset", "inf"),
    ],
)
def test_loudnorm_ranges_a_field_out_of_range_is_a_tool_error(field: str, value: str) -> None:
    with pytest.raises(ToolError) as info:
        parse_pass1(_with(field, value))
    assert info.value.message_es == OUT_OF_RANGE and info.value.exit_code == 4


def test_loudnorm_ranges_the_error_does_not_cite_the_output_of_ffmpeg() -> None:
    text = "C:/Users/Maria 809-555-1234/mix.f32: odd\n" + _with("input_lra", "500.00")
    with pytest.raises(ToolError) as info:
        parse_pass1(text)
    message = info.value.message_es
    assert message == OUT_OF_RANGE
    assert not any(piece in message for piece in ("Maria", "809", "500"))


def test_loudnorm_ranges_a_loudness_over_zero_wins_over_a_field_out_of_range() -> None:
    """Both are wrong; the first one that is read is the one that is told (the loudness)."""
    text = _with("input_lra", "500.00").replace('"-21.75"', '"3.00"')
    with pytest.raises(CheckFailed):
        parse_pass1(text)


def test_loudnorm_ranges_silence_is_still_none_whatever_the_other_fields_say() -> None:
    assert parse_pass1(_with("input_lra", "500.00").replace('"-21.75"', '"-inf"')) is None
