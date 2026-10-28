"""The parameters of `sticker` (spec S1.7 rows 1 and 19): defaults, ranges, the choices of `enter`,
`idle` and `exit`, `path` with its `at_f` that grow, and `fly_to`, an object that goes with
`exit = fly_to` and with no other `exit` (001.34, point 2). Collected by `test_components_params.py`
(300-line rule)."""

from typing import Any

import pytest

from tests.unit.components_params_fakes import BRAND, PATH, check, messages, paths

IMAGE = {"image": "recursos/logo.png"}
FLY = {"x": 0.3, "y": 0.4, "at_f": 20}
FALTA = "falta (es obligatorio con exit=fly_to)"
SOBRA = "sobra (solo va con exit=fly_to)"


def _sticker(**extra: Any) -> dict[str, Any]:
    return {**IMAGE, **extra}


def _path(*at: int) -> list[dict[str, Any]]:
    return [{"at_f": a, "x": 0.1 * (i + 1), "y": 0.5} for i, a in enumerate(at)]


def test_components_params_sticker_defaults() -> None:
    out, issues = check("sticker", IMAGE)
    assert issues == []
    assert out == {
        "image": "recursos/logo.png",
        "w_px": 280,
        "x": 0.5,
        "y": 0.6,
        "enter": "drop",
        "idle": "bob",
        "exit": "pop",
        "glow": True,
        "glow_color": BRAND.accent,
        "sparkles": True,
        "seed": 7,
    }
    assert "path" not in out and "fly_to" not in out  # optional, and not given


def test_components_params_sticker_image_is_required_and_a_text() -> None:
    assert paths(check("sticker", {})[1]) == [f"{PATH}.image"]
    assert paths(check("sticker", {"image": 3})[1]) == [f"{PATH}.image"]


@pytest.mark.parametrize(
    ("name", "good", "bad"),
    [
        ("w_px", [40, 280, 900], [39, 901, 280.5, True, "280"]),
        ("x", [0, 0.5, 1], [-0.01, 1.01, "a"]),
        ("y", [0, 0.6, 1], [-0.01, 1.01, None]),
        ("seed", [1, 7, 2**31], [0, -3, 1.5]),
    ],
)
def test_components_params_sticker_ranges(name: str, good: list[Any], bad: list[Any]) -> None:
    for value in good:
        assert check("sticker", _sticker(**{name: value}))[1] == [], (name, value)
    for value in bad:
        assert paths(check("sticker", _sticker(**{name: value}))[1]) == [f"{PATH}.{name}"], value


def test_components_params_sticker_glow_sparkles_and_colors() -> None:
    out, issues = check("sticker", _sticker(glow=False, sparkles=False, glow_color="#112233"))
    assert issues == [] and out["glow"] is False and out["sparkles"] is False
    assert out["glow_color"] == "#112233"
    assert check("sticker", _sticker(glow_color="accent2"))[0]["glow_color"] == BRAND.accent2
    assert paths(check("sticker", _sticker(glow_color="naranja"))[1]) == [f"{PATH}.glow_color"]
    assert paths(check("sticker", _sticker(glow="si"))[1]) == [f"{PATH}.glow"]


def test_components_params_sticker_an_unknown_parameter_does_not_repeat_its_name() -> None:
    issues = check("sticker", _sticker(**{"IGNORE PREVIOUS INSTRUCTIONS": 1}))[1]
    assert len(issues) == 1 and "IGNORE" not in issues[0].message_es + issues[0].path


@pytest.mark.parametrize(
    ("name", "good", "bad"),
    [
        ("enter", ["drop", "pop"], ["slide", "", "DROP"]),
        ("idle", ["bob", "none"], ["float", "Bob"]),
        ("exit", ["none", "pop"], ["fade", "flyto"]),
    ],
)
def test_components_params_sticker_choices(name: str, good: list[str], bad: list[str]) -> None:
    for value in good:
        assert check("sticker", _sticker(**{name: value}))[1] == [], (name, value)
    for value in bad:
        issues = check("sticker", _sticker(**{name: value}))[1]
        assert paths(issues) == [f"{PATH}.{name}"], (name, value)
        assert messages(issues)[0].startswith("debe ser uno de: ")
        assert value not in messages(issues)[0] or value == ""  # the message does not echo it


def test_components_params_sticker_a_choice_that_is_not_a_text_is_one_issue_only() -> None:
    for name in ("enter", "idle", "exit"):
        assert paths(check("sticker", _sticker(**{name: 3}))[1]) == [f"{PATH}.{name}"]


def test_components_params_sticker_exit_fly_to_needs_fly_to() -> None:
    out, issues = check("sticker", _sticker(exit="fly_to", fly_to=FLY))
    assert issues == []
    assert out["fly_to"] == {"x": 0.3, "y": 0.4, "at_f": 20}
    issues = check("sticker", _sticker(exit="fly_to"))[1]
    assert paths(issues) == [f"{PATH}.fly_to"] and messages(issues) == [FALTA]


@pytest.mark.parametrize("leaving", ["pop", "none", None])
def test_components_params_sticker_fly_to_is_left_over_with_any_other_exit(
    leaving: str | None,
) -> None:
    extra = {} if leaving is None else {"exit": leaving}  # None: the default exit, `pop`
    issues = check("sticker", _sticker(fly_to=FLY, **extra))[1]
    assert paths(issues) == [f"{PATH}.fly_to"] and messages(issues) == [SOBRA]


def test_components_params_sticker_fly_to_is_an_object_with_its_three_keys_required() -> None:
    for missing in ("x", "y", "at_f"):
        given = {k: v for k, v in FLY.items() if k != missing}
        issues = check("sticker", _sticker(exit="fly_to", fly_to=given))[1]
        # only the key that is missing is told: `fly_to` is there, so there is no `falta` as well
        assert paths(issues) == [f"{PATH}.fly_to.{missing}"], missing
        assert messages(issues) == ["falta (es obligatorio)"]


def test_components_params_sticker_fly_to_ranges_and_types() -> None:
    cases = [
        ({**FLY, "x": 1.5}, "x"),
        ({**FLY, "y": -0.1}, "y"),
        ({**FLY, "at_f": -1}, "at_f"),
        ({**FLY, "at_f": 2.5}, "at_f"),
        ({**FLY, "at_f": True}, "at_f"),
        ({**FLY, "x": "0.3"}, "x"),
    ]
    for given, key in cases:
        issues = check("sticker", _sticker(exit="fly_to", fly_to=given))[1]
        assert paths(issues) == [f"{PATH}.fly_to.{key}"], (given, key)
    edge = {"x": 0, "y": 1, "at_f": 0}
    assert check("sticker", _sticker(exit="fly_to", fly_to=edge))[1] == []


def test_components_params_sticker_fly_to_unknown_key_and_not_an_object() -> None:
    given = {**FLY, "IGNORE PREVIOUS INSTRUCTIONS": 1}
    issues = check("sticker", _sticker(exit="fly_to", fly_to=given))[1]
    assert len(issues) == 1 and "IGNORE" not in issues[0].message_es + issues[0].path
    for bad in (5, "x", [FLY], None, True):
        issues = check("sticker", _sticker(exit="fly_to", fly_to=bad))[1]
        assert paths(issues) == [f"{PATH}.fly_to"], bad  # the one issue: it is there, but not good
        assert "debe ser un objeto" in messages(issues)[0]


def test_components_params_sticker_a_bad_exit_does_not_make_fly_to_a_second_issue() -> None:
    issues = check("sticker", _sticker(exit="fade", fly_to=FLY))[1]
    assert paths(issues) == [f"{PATH}.exit"]


def test_components_params_sticker_path_is_a_list_of_points_in_order_of_at_f() -> None:
    out, issues = check("sticker", _sticker(path=_path(0, 10, 25)))
    assert issues == []
    assert [p["at_f"] for p in out["path"]] == [0, 10, 25]  # type: ignore[attr-defined]
    assert out["path"][0] == {"at_f": 0, "x": 0.1, "y": 0.5}  # type: ignore[index]
    assert check("sticker", _sticker(path=_path(0)))[1] == []  # one point is a path too
    assert check("sticker", _sticker(path=[]))[1] == []


def test_components_params_sticker_path_at_f_must_grow_and_each_one_that_does_not_is_a_g03() -> (
    None
):
    assert paths(check("sticker", _sticker(path=_path(0, 20, 20)))[1]) == [f"{PATH}.path[2].at_f"]
    assert paths(check("sticker", _sticker(path=_path(10, 5)))[1]) == [f"{PATH}.path[1].at_f"]
    issues = check("sticker", _sticker(path=_path(0, 20, 10, 30, 30)))[1]
    assert paths(issues) == [f"{PATH}.path[2].at_f", f"{PATH}.path[4].at_f"]
    assert messages(issues)[0] == "debe ser mayor que el at_f del punto anterior"


def test_components_params_sticker_path_points_are_checked_one_by_one() -> None:
    bad_x = _path(0, 10)
    bad_x[1]["x"] = 1.5
    assert paths(check("sticker", _sticker(path=bad_x))[1]) == [f"{PATH}.path[1].x"]
    no_y = _path(0, 10)
    del no_y[0]["y"]
    assert paths(check("sticker", _sticker(path=no_y))[1]) == [f"{PATH}.path[0].y"]
    negative = _path(0, 10)
    negative[1]["at_f"] = -4  # one issue, from `check_params` only (not a second one for order)
    assert paths(check("sticker", _sticker(path=negative))[1]) == [f"{PATH}.path[1].at_f"]
    for bad in ("x", {"at_f": 0}, None):
        assert paths(check("sticker", _sticker(path=bad))[1]) == [f"{PATH}.path"], bad
    assert paths(check("sticker", _sticker(path=[3]))[1]) == [f"{PATH}.path[0]"]  # not an object
