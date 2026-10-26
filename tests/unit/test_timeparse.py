"""`parse_time`: the times a person types, read exactly (spec S1.4, 001.15: no `float`)."""

import ast
import inspect

import pytest

from kcut import timeparse
from kcut.errors import UsageError
from kcut.timeparse import parse_time


@pytest.mark.parametrize(
    ("text", "frames"),
    [
        ("90", 90),
        ("0", 0),
        ("3s", 90),
        ("0.15s", 5),  # with a float it came out as 4
        ("2.5s", 75),
        ("3.0167s", 91),
        ("1:02", 1860),
        ("0:03.5", 105),
        ("00:00", 0),
        ("59:59.98", 107_999),
    ],
)
def test_parse_time_the_fixed_cases_at_30_fps(text: str, frames: int) -> None:
    assert parse_time(text, 30) == frames


@pytest.mark.parametrize(
    "text",
    [
        "1:75",  # seconds are under 60
        "1:60",
        "1e3s",
        "-3",
        "",
        "9" * 5000,
        "9" * 33,
        " 3s",
        "3 s",
        "3S",
        "s",
        ".5s",
        "5.s",
        "1:2:3",
        "1,5s",
        "1:5.",
        "٣s",  # Arabic-Indic digit: not a digit here
        "٣",
        "90\n",
    ],
)
def test_parse_time_rejects_the_rest(text: str) -> None:
    with pytest.raises(UsageError):
        parse_time(text, 30)


def test_parse_time_a_number_of_32_characters_is_the_longest_that_is_read() -> None:
    assert parse_time("1" * 32, 30) == int("1" * 32)
    with pytest.raises(UsageError):
        parse_time("1" * 33, 30)


@pytest.mark.parametrize(
    ("text", "fps", "frames"),
    [
        ("1s", 24, 24),
        ("1:00", 25, 1500),
        ("0.5s", 60, 30),
        ("0.0165s", 30, 1),  # 16.5 ms: halves go up
        ("0.0164s", 30, 0),
        ("0.0005s", 30, 0),
        ("2.9999999999999999999s", 30, 90),  # exact, not a float that rounds up to 3
    ],
)
def test_parse_time_follows_the_fps_and_rounds_halves_up(text: str, fps: int, frames: int) -> None:
    assert parse_time(text, fps) == frames


def test_parse_time_uses_no_float_at_all() -> None:
    tree = ast.parse(inspect.getsource(timeparse))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    floats = [
        n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)
    ]
    divisions = [n for n in ast.walk(tree) if isinstance(n, ast.Div)]
    assert "float" not in names and not floats and not divisions
