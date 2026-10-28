"""The parameters of the showpiece components (spec S1.7 row 1): their defaults, ranges and lengths,
and the rules of their own that `validate_params` adds to `check_params` (a G03 each). `steps` and
`globe` are here; `sticker` and `holo_board` (001.34, row 19) are in `components_params_sticker.py`
and `components_params_holo.py`, collected below (300-line rule).
"""

from typing import Any

import pytest

from kcut.config.load import parse_config
from kcut.gfx.components import COMPONENTS, validate_params
from kcut.gfx.components_showpiece import SHOWPIECE
from kcut.issues import Issue
from tests.unit.components_params_holo import *  # noqa: F403  (001.34: collected here)
from tests.unit.components_params_sticker import *  # noqa: F403  (001.34: collected here)

BRAND = parse_config("", default_name="x").brand
PATH = "cues[0].params"


def _check(component: str, params: object) -> tuple[dict[str, object], list[Issue]]:
    return validate_params(COMPONENTS[component], params, PATH, BRAND)


def _paths(issues: list[Issue]) -> list[str]:
    assert all(issue.code == "G03" and issue.level == "error" for issue in issues), issues
    return [issue.path for issue in issues]


def _steps(*at: int, **extra: Any) -> dict[str, Any]:
    items = [
        {"at_f": a, "label": f"PASO {i + 1}", "text": f"hace el paso {i + 1}"}
        for i, a in enumerate(at)
    ]
    return {"items": items, **extra}


def test_components_params_the_showpieces_are_registered_with_their_ids_and_files() -> None:
    assert [c.id for c in SHOWPIECE] == ["steps", "sticker", "holo_board", "globe"]  # 001.34
    for component in SHOWPIECE:
        assert COMPONENTS[component.id] is component
        assert component.js_files == (f"{component.id}.js",)
        # 001.34: "todos big=no salvo `holo_board`" (the old line said `big is False` for all)
        assert component.big is (component.id == "holo_board") and component.since == "S1.7"
        assert component.cost in ("bajo", "medio", "alto") and component.name_es


def test_components_params_steps_defaults_and_a_good_document() -> None:
    out, issues = _check("steps", _steps(0, 20, 40))
    assert issues == []
    assert out["y"] == 0.136
    assert (
        out["badge"] == BRAND.accent and out["panel"] == BRAND.dark and out["ring"] == BRAND.accent
    )
    assert [item["at_f"] for item in out["items"]] == [0, 20, 40]  # type: ignore[attr-defined]


def test_components_params_steps_colors_take_a_token_or_hex() -> None:
    out, issues = _check("steps", _steps(0, badge="accent2", panel="#112233", ring="light"))
    assert issues == []
    assert (
        out["badge"] == BRAND.accent2 and out["panel"] == "#112233" and out["ring"] == BRAND.light
    )


@pytest.mark.parametrize("count", [1, 8])
def test_components_params_steps_one_to_eight_items_are_fine(count: int) -> None:
    assert _check("steps", _steps(*range(0, 10 * count, 10)))[1] == []


@pytest.mark.parametrize("count", [0, 9])
def test_components_params_steps_zero_or_nine_items_are_a_g03_on_items(count: int) -> None:
    params = _steps(*range(0, 10 * count, 10))
    assert _paths(_check("steps", params)[1]) == [f"{PATH}.items"]


def test_components_params_steps_at_f_must_grow_and_each_one_that_does_not_is_a_g03() -> None:
    assert _paths(_check("steps", _steps(0, 20, 20))[1]) == [f"{PATH}.items[2].at_f"]
    assert _paths(_check("steps", _steps(10, 5))[1]) == [f"{PATH}.items[1].at_f"]
    # the one that falls out of order is told, the rest is compared with the last good one
    assert _paths(_check("steps", _steps(0, 20, 10, 30, 30))[1]) == [
        f"{PATH}.items[2].at_f",
        f"{PATH}.items[4].at_f",
    ]


def test_components_params_steps_a_bad_at_f_is_told_once_by_check_params_only() -> None:
    params = _steps(0, 20)
    params["items"][1]["at_f"] = -1
    assert _paths(_check("steps", params)[1]) == [f"{PATH}.items[1].at_f"]
    params["items"][1]["at_f"] = 1.5
    assert _paths(_check("steps", params)[1]) == [f"{PATH}.items[1].at_f"]


def test_components_params_steps_item_fields_are_required_and_limited() -> None:
    params = _steps(0)
    params["items"][0]["label"] = "x" * 13
    params["items"][0]["text"] = "y" * 41
    assert _paths(_check("steps", params)[1]) == [f"{PATH}.items[0].label", f"{PATH}.items[0].text"]
    assert _check("steps", {"items": [{"at_f": 0, "label": "x" * 12, "text": "y" * 40}]})[1] == []
    for missing in ("at_f", "label", "text"):
        params = _steps(0)
        del params["items"][0][missing]
        assert _paths(_check("steps", params)[1]) == [f"{PATH}.items[0].{missing}"]


def test_components_params_steps_items_is_required_and_y_is_a_fraction() -> None:
    assert _paths(_check("steps", {})[1]) == [f"{PATH}.items"]
    assert _paths(_check("steps", _steps(0, y=1.5))[1]) == [f"{PATH}.y"]
    assert _paths(_check("steps", _steps(0, y=-0.1))[1]) == [f"{PATH}.y"]
    assert _check("steps", _steps(0, y=0))[1] == [] and _check("steps", _steps(0, y=1))[1] == []


def test_components_params_steps_an_unknown_parameter_is_a_g03_that_does_not_repeat_it() -> None:
    issues = _check("steps", _steps(0, **{"IGNORE PREVIOUS INSTRUCTIONS": 1}))[1]
    assert len(issues) == 1 and "IGNORE" not in issues[0].message_es


def test_components_params_globe_defaults() -> None:
    out, issues = _check("globe", {})
    assert issues == []
    assert out == {
        "x": 0.306,
        "y": 0.396,
        "r_px": 190,
        "color": BRAND.accent,
        "spin": 1.4,
        "tilt": 0.38,
        "dots": 70,
        "seed": 7,
    }


@pytest.mark.parametrize(
    ("name", "good", "bad"),
    [
        ("r_px", [40, 190, 500], [39, 501, 190.5, True]),
        ("spin", [0, 1.4, 6], [-0.1, 6.1]),
        ("tilt", [0, 0.38, 1.2], [-0.1, 1.21]),
        ("dots", [0, 70, 200], [-1, 201, 7.5]),
        ("seed", [1, 7, 2**31], [0, -3, 1.5]),
        ("x", [0, 0.306, 1], [-0.01, 1.01]),
        ("y", [0, 0.396, 1], [-0.01, 1.01]),
    ],
)
def test_components_params_globe_ranges(name: str, good: list[Any], bad: list[Any]) -> None:
    for value in good:
        assert _check("globe", {name: value})[1] == [], (name, value)
    for value in bad:
        assert _paths(_check("globe", {name: value})[1]) == [f"{PATH}.{name}"], (name, value)


def test_components_params_globe_color_and_unknown_parameters() -> None:
    assert _check("globe", {"color": "#6FF6FF"})[0]["color"] == "#6FF6FF"
    assert _paths(_check("globe", {"color": "verde"})[1]) == [f"{PATH}.color"]
    assert len(_check("globe", {"radius": 3})[1]) == 1
    assert _paths(_check("globe", [])[1]) == [PATH]  # params that is not an object
