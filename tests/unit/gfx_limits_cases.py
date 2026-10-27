"""The limits of `edit/graphics.json` (spec S1.6a round 2, 001.28 point 3; row 24): at most 500 cues
and at most 1 MiB. Here the schema; the command is in `graphics_limits_cases.py`.

Collected from `test_gfx_schema.py`.
"""

from typing import Any

from kcut.gfx import resolve, schema
from kcut.gfx.schema import MAX_CUES, MAX_HIDE, SCHEMA, parse_graphics

__all__ = [
    "test_gfx_schema_graphics_limits_500_cues_are_read",
    "test_gfx_schema_graphics_limits_501_cues_are_one_g01_and_no_cue_is_looked_at",
    "test_gfx_schema_graphics_limits_the_numbers_are_the_ones_of_the_spec",
    "test_gfx_schema_hide_limits_500_windows_are_read",
    "test_gfx_schema_hide_limits_501_windows_are_one_g01_and_no_window_is_looked_at",
    "test_gfx_schema_hide_limits_the_number_is_the_one_of_the_spec",
]


def _cue(i: int) -> dict[str, Any]:
    return {
        "id": f"cue-{i:04d}",
        "component": "label",
        "start": 0,
        "end": 30,
        "params": {"text": "x"},
    }


def test_gfx_schema_graphics_limits_the_numbers_are_the_ones_of_the_spec() -> None:
    assert MAX_CUES == 500 and schema.MAX_CUES == 500
    assert resolve.MAX_GRAPHICS_BYTES == 1024 * 1024


def test_gfx_schema_graphics_limits_500_cues_are_read() -> None:
    doc, issues = parse_graphics({"schema": SCHEMA, "cues": [_cue(i) for i in range(MAX_CUES)]})
    assert issues == [] and doc is not None and len(doc.cues) == MAX_CUES
    assert doc.cues[-1].id == "cue-0499"


def test_gfx_schema_graphics_limits_501_cues_are_one_g01_and_no_cue_is_looked_at() -> None:
    """With more than 500 cues the answer is one G01 on `cues`, with a fixed text, and nothing of
    what the cues say is judged (here none of them is valid: no `id`, no `component`)."""
    broken: list[Any] = [{"nada": i} for i in range(MAX_CUES + 1)]
    doc, issues = parse_graphics({"schema": SCHEMA, "cues": broken})
    assert doc is None
    assert [(i.code, i.level, i.path, i.message_es) for i in issues] == [
        ("G01", "error", "cues", "hay más de 500 cues; kcut no los revisa")
    ]
    valid = [_cue(i) for i in range(MAX_CUES + 1)]
    doc, issues = parse_graphics({"schema": SCHEMA, "cues": valid})
    assert doc is None and [(i.code, i.path) for i in issues] == [("G01", "cues")]


def _hidden(count: int, item: Any = None) -> dict[str, Any]:
    window = {"start": 0, "end": 30} if item is None else item
    return {"schema": SCHEMA, "captions": {"hide": [window] * count}, "cues": []}


def test_gfx_schema_hide_limits_the_number_is_the_one_of_the_spec() -> None:  # 001.30
    assert MAX_HIDE == 500 and schema.MAX_HIDE == 500


def test_gfx_schema_hide_limits_500_windows_are_read() -> None:  # 001.30
    doc, issues = parse_graphics(_hidden(MAX_HIDE))
    assert issues == [] and doc is not None and len(doc.hide) == MAX_HIDE
    assert [w.index for w in doc.hide] == list(range(MAX_HIDE))


def test_gfx_schema_hide_limits_501_windows_are_one_g01_and_no_window_is_looked_at() -> None:
    """001.30 point 1: with more than 500 windows the answer is one G01 on `captions.hide`, with
    a fixed text, and no window is judged (here none is valid: a number, an empty object)."""
    for window in (7, {}, {"start": "x", "end": [1], "otra": 1}):
        doc, issues = parse_graphics(_hidden(MAX_HIDE + 1, window))
        assert doc is None
        assert [(i.code, i.level, i.path, i.message_es) for i in issues] == [
            (
                "G01",
                "error",
                "captions.hide",
                "hay más de 500 ventanas en captions.hide; kcut no las revisa",
            )
        ]
