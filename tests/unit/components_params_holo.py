"""The parameters of `holo_board` (spec S1.7 rows 1 and 19): defaults, lengths, ranges, and
`accent_index`, an `int` between 0 and 11 that may be `null` (001.34, point 2): not given, the last
letter has the accent; `null`, none has it; an index that is not inside `text` is a G03.
Collected by `test_components_params.py` (300-line rule)."""

from typing import Any

import pytest

from kcut.gfx.components import COMPONENTS
from tests.unit.components_params_fakes import BRAND, PATH, check, messages, paths

OUTSIDE = "accent_index apunta fuera del texto"


def _holo(**extra: Any) -> dict[str, Any]:
    return {"text": "HOLA", "type_at_f": 30, **extra}


def test_components_params_holo_board_defaults() -> None:
    out, issues = check("holo_board", _holo())
    assert issues == []
    assert out == {
        "label": "",
        "corner_text": "",
        "text": "HOLA",
        "type_at_f": 30,
        "type_step_f": 4,
        "born": {"x": 0.479, "y": 0.199},
        "center": {"x": 0.5, "y": 0.448},
        "w_px": 860,
        "h_px": 500,
        "color": "#6FF6FF",
        "beams_from": [],
    }
    assert "accent_index" not in out  # not given is not null: the last letter has the accent


def test_components_params_holo_board_is_big_and_hides_the_subtitles_by_default() -> None:
    assert COMPONENTS["holo_board"].big is True
    assert COMPONENTS["sticker"].big is False


def test_components_params_holo_board_text_is_required_and_from_one_to_twelve_letters() -> None:
    assert paths(check("holo_board", {"type_at_f": 3})[1]) == [f"{PATH}.text"]
    assert check("holo_board", _holo(text="X"))[1] == []
    assert check("holo_board", _holo(text="DOCE LETRAS!"))[1] == []  # 12 characters
    too_long = check("holo_board", _holo(text="TRECE LETRAS!"))[1]
    assert paths(too_long) == [f"{PATH}.text"] and "como máximo 12" in messages(too_long)[0]
    empty = check("holo_board", _holo(text=""))[1]
    assert paths(empty) == [f"{PATH}.text"]
    assert messages(empty) == ["debe tener al menos 1 carácter (tiene 0)"]
    assert paths(check("holo_board", _holo(text=5))[1]) == [f"{PATH}.text"]  # one issue only


@pytest.mark.parametrize(
    ("name", "good", "bad"),
    [
        ("type_at_f", [0, 30, 10_000], [-1, 1.5, True, "30"]),
        ("type_step_f", [1, 4, 15], [0, 16, 2.5, False]),
        ("w_px", [300, 860, 2000], [299, 2001, 860.5]),  # 001.35: 300 to 2000 (it was 100)
        ("h_px", [100, 500, 2000], [99, 2001, "500"]),
    ],
)
def test_components_params_holo_board_ranges(name: str, good: list[Any], bad: list[Any]) -> None:
    for value in good:
        assert check("holo_board", _holo(**{name: value}))[1] == [], (name, value)
    for value in bad:
        assert paths(check("holo_board", _holo(**{name: value}))[1]) == [f"{PATH}.{name}"], value


def test_components_params_holo_board_type_at_f_is_required() -> None:
    assert paths(check("holo_board", {"text": "HOLA"})[1]) == [f"{PATH}.type_at_f"]


def test_components_params_holo_board_label_and_corner_text_are_up_to_24() -> None:
    out, issues = check("holo_board", _holo(label="x" * 24, corner_text="IA · EN VIVO"))
    assert issues == [] and out["label"] == "x" * 24 and out["corner_text"] == "IA · EN VIVO"
    for name in ("label", "corner_text"):
        assert paths(check("holo_board", _holo(**{name: "x" * 25}))[1]) == [f"{PATH}.{name}"]
        assert paths(check("holo_board", _holo(**{name: 5}))[1]) == [f"{PATH}.{name}"]


def test_components_params_holo_board_accent_index_not_given_is_left_out() -> None:
    out, issues = check("holo_board", _holo())
    assert issues == [] and "accent_index" not in out


def test_components_params_holo_board_accent_index_null_is_none_and_it_is_in_the_result() -> None:
    out, issues = check("holo_board", _holo(accent_index=None))
    assert issues == []
    assert "accent_index" in out and out["accent_index"] is None  # null is not "not given"


@pytest.mark.parametrize(("text", "index"), [("HOLA", 0), ("HOLA", 3), ("DOCE LETRAS!", 11)])
def test_components_params_holo_board_accent_index_inside_the_text_is_fine(
    text: str, index: int
) -> None:
    out, issues = check("holo_board", _holo(text=text, accent_index=index))
    assert issues == [] and out["accent_index"] == index


@pytest.mark.parametrize(("text", "index"), [("HOLA", 4), ("HOLA", 11), ("X", 1), ("X", 5)])
def test_components_params_holo_board_accent_index_outside_the_text_is_a_g03(
    text: str, index: int
) -> None:
    issues = check("holo_board", _holo(text=text, accent_index=index))[1]
    assert paths(issues) == [f"{PATH}.accent_index"] and messages(issues) == [OUTSIDE]


@pytest.mark.parametrize("index", [-1, 12, 100, 1.5, "2", True, [0], {"i": 0}])
def test_components_params_holo_board_accent_index_out_of_its_range_or_type_is_one_issue(
    index: object,
) -> None:
    issues = check("holo_board", _holo(text="DOCE LETRAS!", accent_index=index))[1]
    assert paths(issues) == [f"{PATH}.accent_index"]
    assert messages(issues) != [OUTSIDE]  # `check_params` said it (not the rule as well)


def test_components_params_holo_board_the_index_counts_characters_not_bytes() -> None:
    assert check("holo_board", _holo(text="ÑANDÚ", accent_index=4))[1] == []
    assert paths(check("holo_board", _holo(text="ÑANDÚ", accent_index=5))[1]) == [
        f"{PATH}.accent_index"
    ]


def test_components_params_holo_board_born_and_center_are_points_of_the_picture() -> None:
    out, issues = check("holo_board", _holo(born={"x": 0, "y": 1}, center={"x": 0.25, "y": 0.5}))
    assert issues == [] and out["born"] == {"x": 0.0, "y": 1.0}
    assert out["center"] == {"x": 0.25, "y": 0.5}
    assert paths(check("holo_board", _holo(born={"x": 1.5, "y": 0.5}))[1]) == [f"{PATH}.born.x"]
    assert paths(check("holo_board", _holo(center={"x": 0.5, "y": -1}))[1]) == [f"{PATH}.center.y"]
    for name in ("born", "center"):
        for bad in ({"x": 0.5}, {"x": 0.5, "y": 0.5, "z": 1}, [0.5, 0.5], "a", None):
            assert paths(check("holo_board", _holo(**{name: bad}))[1]) == [f"{PATH}.{name}"]


def test_components_params_holo_board_color_by_hex_or_token() -> None:
    assert check("holo_board", _holo(color="#ff00aa"))[0]["color"] == "#FF00AA"
    assert check("holo_board", _holo(color="accent2"))[0]["color"] == BRAND.accent2
    assert paths(check("holo_board", _holo(color="cian"))[1]) == [f"{PATH}.color"]


def test_components_params_holo_board_beams_from_is_zero_to_two_points() -> None:
    assert check("holo_board", _holo(beams_from=[]))[1] == []
    one = [{"x": 0.25, "y": 0.2}]
    two = [*one, {"x": 0.7, "y": 0.19}]
    assert check("holo_board", _holo(beams_from=two))[0]["beams_from"] == two
    three = [*two, {"x": 0.5, "y": 0.5}]
    assert paths(check("holo_board", _holo(beams_from=three))[1]) == [f"{PATH}.beams_from"]
    assert paths(check("holo_board", _holo(beams_from=[{"x": 0.5}]))[1]) == [
        f"{PATH}.beams_from[0].y"
    ]
    assert paths(check("holo_board", _holo(beams_from=[{"x": 2, "y": 0.5}]))[1]) == [
        f"{PATH}.beams_from[0].x"
    ]
    assert paths(check("holo_board", _holo(beams_from="x"))[1]) == [f"{PATH}.beams_from"]


def test_components_params_holo_board_an_unknown_parameter_does_not_repeat_its_name() -> None:
    issues = check("holo_board", _holo(**{"IGNORE PREVIOUS INSTRUCTIONS": 1}))[1]
    assert len(issues) == 1 and "IGNORE" not in issues[0].message_es + issues[0].path


def test_components_params_holo_width_goes_from_300_to_2000() -> None:
    """001.35, point 10 (S1.8a row 17): under 300 px a 12-letter word spilled out of the board."""
    for narrow in (299, 100, 0):
        issues = check("holo_board", _holo(w_px=narrow))[1]
        assert paths(issues) == [f"{PATH}.w_px"], narrow
        assert messages(issues) == [f"debe estar entre 300 y 2000 (vino {narrow})"]
    assert check("holo_board", _holo(w_px=300))[1] == []
    assert check("holo_board", _holo(w_px=2000))[1] == []
    assert paths(check("holo_board", _holo(w_px=2001))[1]) == [f"{PATH}.w_px"]
