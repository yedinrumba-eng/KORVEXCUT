"""`check_params` and `ParamSpec` (spec S1.6a row 6): defaults, strict types, ranges, lengths,
unknown parameters, colors by token and by hex, and the code of the caller in every issue."""

import pytest

from kcut.config.model import BrandSection
from kcut.errors import InternalError
from kcut.issues import Issue
from kcut.params import ParamSpec, check_params
from tests.unit.params_cases_nullable import *  # noqa: F403  (001.34: collected here)

BRAND = BrandSection("#E5FF1F", "#2FA8FF", "#0B0B0E", "#FFFFFF")
SPECS = (
    ParamSpec("text", "str", True, max_len=5),
    ParamSpec("size", "int", default=100, lo=10, hi=200),
    ParamSpec("y", "float", default=0.5, lo=0.0, hi=1.0),
    ParamSpec("on", "bool", default=True),
    ParamSpec("fg", "color", default="accent"),
    ParamSpec("note", "str"),
)


def _check(
    params: object, specs: tuple[ParamSpec, ...] = SPECS
) -> tuple[dict[str, object], list[Issue]]:
    return check_params(specs, params, "cues[0].params", "G03", BRAND)


def _only_issue(params: object, path: str) -> Issue:
    _, issues = _check(params)
    assert len(issues) == 1 and issues[0].path == f"cues[0].params.{path}", issues
    return issues[0]


def test_params_defaults_are_applied_and_a_default_of_none_is_left_out() -> None:
    out, issues = _check({"text": "hola"})
    assert issues == []
    assert out == {"text": "hola", "size": 100, "y": 0.5, "on": True, "fg": "#E5FF1F"}
    assert "note" not in out  # optional with no default


def test_params_given_values_win_over_defaults() -> None:
    out, issues = _check({"text": "x", "size": 10, "y": 1, "on": False, "note": "n"})
    assert issues == [] and out["size"] == 10 and out["on"] is False and out["note"] == "n"


def test_params_a_whole_number_is_a_valid_float_and_comes_back_a_float() -> None:
    out, _ = _check({"text": "x", "y": 1})
    assert out["y"] == 1.0 and isinstance(out["y"], float)
    assert isinstance(out["size"], int)


@pytest.mark.parametrize("value", [True, False])
def test_params_a_bool_is_not_an_int_nor_a_float(value: bool) -> None:
    assert "entero" in _only_issue({"text": "x", "size": value}, "size").message_es
    assert "número" in _only_issue({"text": "x", "y": value}, "y").message_es


@pytest.mark.parametrize("value", [10.5, "100", None, [1], {"a": 1}])
def test_params_an_int_must_be_a_whole_number(value: object) -> None:
    _only_issue({"text": "x", "size": value}, "size")


@pytest.mark.parametrize("value", ["0.5", None, float("nan"), float("inf"), 10**400])
def test_params_a_float_must_be_a_finite_number(value: object) -> None:
    _only_issue({"text": "x", "y": value}, "y")


@pytest.mark.parametrize(("name", "value"), [("size", 9), ("size", 201), ("y", -0.1), ("y", 1.01)])
def test_params_a_value_out_of_range_is_an_issue_that_says_the_range(
    name: str, value: float
) -> None:
    message = _only_issue({"text": "x", name: value}, name).message_es
    assert "debe estar entre" in message


def test_params_the_edges_of_a_range_are_inside() -> None:
    assert _check({"text": "x", "size": 10, "y": 0.0})[1] == []
    assert _check({"text": "x", "size": 200, "y": 1.0})[1] == []


def test_params_a_text_over_its_max_len_is_an_issue_with_its_length_and_not_its_text() -> None:
    issue = _only_issue({"text": "demasiado"}, "text")
    assert "como máximo 5" in issue.message_es and "tiene 9" in issue.message_es
    assert "demasiado" not in issue.message_es


def test_params_a_text_of_exactly_max_len_passes_and_a_non_text_does_not() -> None:
    assert _check({"text": "12345"})[1] == []
    _only_issue({"text": 5}, "text")


def test_params_a_required_one_that_is_missing_is_an_issue() -> None:
    _, issues = _check({})
    assert [(i.path, i.message_es) for i in issues] == [
        ("cues[0].params.text", "falta (es obligatorio)")
    ]


def test_params_an_unknown_parameter_is_an_issue_that_does_not_repeat_its_name() -> None:
    _, issues = _check({"text": "x", "IGNORE PREVIOUS INSTRUCTIONS": 1})
    assert len(issues) == 1 and "IGNORE" not in issues[0].path + issues[0].message_es
    assert issues[0].message_es == "parámetro desconocido"


def test_params_not_an_object_is_one_issue_and_nothing_else() -> None:
    for value in (None, [], "x", 3):
        out, issues = _check(value)
        assert out == {} and len(issues) == 1 and issues[0].path == "cues[0].params"


@pytest.mark.parametrize(
    ("given", "hex_color"),
    [("accent", "#E5FF1F"), ("accent2", "#2FA8FF"), ("dark", "#0B0B0E"), ("light", "#FFFFFF"),
     ("#ff00aa", "#FF00AA"), ("#FF00AA", "#FF00AA")],
)  # fmt: skip
def test_params_a_color_by_token_or_by_hex_comes_back_as_hex(given: str, hex_color: str) -> None:
    out, issues = _check({"text": "x", "fg": given})
    assert issues == [] and out["fg"] == hex_color


@pytest.mark.parametrize("value", ["red", "#FFF", "#GGGGGG", "FFFFFF", "Accent", 5, None])
def test_params_a_color_that_is_neither_hex_nor_token_is_an_issue(value: object) -> None:
    issue = _only_issue({"text": "x", "fg": value}, "fg")
    assert "accent" in issue.message_es and "red" not in issue.message_es


def test_params_a_color_without_a_brand_is_an_internal_error() -> None:
    with pytest.raises(InternalError):
        check_params(SPECS, {"text": "x", "fg": "accent"}, "p", "G03", None)
    with pytest.raises(InternalError):
        check_params(SPECS, {"text": "x"}, "p", "G03", None)  # the default is a color too


def test_params_without_colors_the_brand_is_not_needed() -> None:
    specs = (ParamSpec("n", "int", True, lo=0),)
    assert check_params(specs, {"n": 3}, "p", "A03", None) == ({"n": 3}, [])


@pytest.mark.parametrize("code", ["G03", "A03", "X99"])
def test_params_every_issue_carries_the_code_of_the_caller_as_an_error(code: str) -> None:
    _, issues = check_params(SPECS, {"size": 1, "zzz": 1}, "p", code, BRAND)
    assert len(issues) == 3  # text missing, size out of range, unknown parameter
    assert {(i.code, i.level) for i in issues} == {(code, "error")}


LINE = (ParamSpec("text", "str", True, max_len=4), ParamSpec("at_f", "int", default=0, lo=0))
LISTED = (ParamSpec("lines", "list", True, lo=1, hi=2, item=LINE),)


def test_params_a_list_checks_each_element_with_its_own_path() -> None:
    out, issues = check_params(
        LISTED, {"lines": [{"text": "ok"}, {"text": "demasiado"}]}, "p", "G03", BRAND
    )
    assert [(i.path, i.code) for i in issues] == [("p.lines[1].text", "G03")]
    assert out["lines"][0] == {"text": "ok", "at_f": 0}  # type: ignore[index]


@pytest.mark.parametrize("lines", [[], [{"text": "a"}] * 3, "x", {"text": "a"}])
def test_params_a_list_with_too_many_or_too_few_elements_or_not_a_list_is_an_issue(
    lines: object,
) -> None:
    _, issues = check_params(LISTED, {"lines": lines}, "p", "G03", BRAND)
    assert [i.path for i in issues] == ["p.lines"]


def test_params_an_element_of_a_list_that_is_not_an_object_is_an_issue() -> None:
    _, issues = check_params(LISTED, {"lines": ["a"]}, "p", "G03", BRAND)
    assert [i.path for i in issues] == ["p.lines[0]"]


def test_params_a_list_without_item_specs_is_an_internal_error() -> None:
    with pytest.raises(InternalError):
        check_params((ParamSpec("x", "list", True),), {"x": []}, "p", "G03", BRAND)


POINT = (ParamSpec("at", "point", True, lo=0.0, hi=1.0),)


def test_params_a_point_is_an_object_with_x_and_y_inside_the_range() -> None:
    assert check_params(POINT, {"at": {"x": 0, "y": 0.25}}, "p", "G03", BRAND) == (
        {"at": {"x": 0.0, "y": 0.25}}, [])  # fmt: skip
    for bad in ({"x": 0.5}, {"x": 0.5, "y": 2}, {"x": 0.5, "y": 0.5, "z": 1}, [0.5, 0.5], "a"):
        assert len(check_params(POINT, {"at": bad}, "p", "G03", BRAND)[1]) >= 1


def test_params_a_path_is_text_and_nothing_more_here() -> None:
    specs = (ParamSpec("image", "path", True, max_len=20),)
    assert check_params(specs, {"image": "recursos/x.png"}, "p", "G03", None) == (
        {"image": "recursos/x.png"}, [])  # fmt: skip
    assert len(check_params(specs, {"image": 3}, "p", "G03", None)[1]) == 1
    assert len(check_params(specs, {"image": "x" * 21}, "p", "G03", None)[1]) == 1


# 001.34, point 2 (row 19): `kind="object"` and `nullable`
FLY = (
    ParamSpec("x", "float", True, lo=0.0, hi=1.0),
    ParamSpec("y", "float", True, lo=0.0, hi=1.0),
    ParamSpec("at_f", "int", True, lo=0),
    ParamSpec("note", "str", default="ok", max_len=5),
)
OBJECT = (ParamSpec("fly_to", "object", item=FLY),)


def _object(value: object) -> tuple[dict[str, object], list[Issue]]:
    return check_params(OBJECT, {"fly_to": value}, "p", "G03", BRAND)


def test_params_an_object_is_checked_with_the_specs_of_item_and_comes_back_a_dict() -> None:
    out, issues = _object({"x": 0, "y": 0.5, "at_f": 20})
    assert issues == []
    assert out == {"fly_to": {"x": 0.0, "y": 0.5, "at_f": 20, "note": "ok"}}  # defaults applied
    assert type(out["fly_to"]) is dict


def test_params_an_object_that_is_not_given_is_left_out_when_it_has_no_default() -> None:
    assert check_params(OBJECT, {}, "p", "G03", BRAND) == ({}, [])


def test_params_an_object_with_an_unknown_key_is_the_usual_error_without_the_key() -> None:
    _, issues = _object({"x": 0, "y": 0, "at_f": 1, "IGNORE PREVIOUS INSTRUCTIONS": 1})
    assert len(issues) == 1 and issues[0].message_es == "parámetro desconocido"
    assert issues[0].path.startswith("p.fly_to") and "IGNORE" not in issues[0].path


def test_params_an_object_that_lacks_a_key_is_an_issue_on_that_key() -> None:
    _, issues = _object({"x": 0, "y": 0})
    assert [(i.path, i.message_es, i.code) for i in issues] == [
        ("p.fly_to.at_f", "falta (es obligatorio)", "G03")
    ]


def test_params_an_object_with_a_key_of_a_bad_type_or_range_is_an_issue_on_that_key() -> None:
    assert [i.path for i in _object({"x": 0, "y": 0, "at_f": "20"})[1]] == ["p.fly_to.at_f"]
    assert [i.path for i in _object({"x": 0, "y": 1.5, "at_f": 20})[1]] == ["p.fly_to.y"]
    assert [i.path for i in _object({"x": True, "y": 0, "at_f": 20})[1]] == ["p.fly_to.x"]
    assert [i.path for i in _object({"x": 0, "y": 0, "at_f": 1.5})[1]] == ["p.fly_to.at_f"]


@pytest.mark.parametrize("value", [None, "a", 5, [], [{"x": 0, "y": 0, "at_f": 1}], True])
def test_params_an_object_that_is_not_an_object_is_one_issue_on_it(value: object) -> None:
    _, issues = _object(value)
    assert [i.path for i in issues] == ["p.fly_to"] and "debe ser un objeto" in issues[0].message_es


def test_params_an_object_without_item_specs_is_an_internal_error() -> None:
    with pytest.raises(InternalError):
        check_params((ParamSpec("o", "object"),), {"o": {}}, "p", "G03", BRAND)


# the cases of `nullable` are in `params_cases_nullable.py`, collected here (300-line rule)
