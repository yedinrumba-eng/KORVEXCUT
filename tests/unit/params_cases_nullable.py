"""`ParamSpec.nullable` (spec S1.7 row 19, 001.34 point 2): with it a JSON `null` is a valid
value and comes back as `None`, which is not the same as not being given. Collected by
`test_params.py` (300-line rule)."""

from kcut.config.model import BrandSection
from kcut.issues import Issue
from kcut.params import ParamSpec, check_params

BRAND = BrandSection("#E5FF1F", "#2FA8FF", "#0B0B0E", "#FFFFFF")
ITEM = (ParamSpec("x", "float", True, lo=0.0, hi=1.0), ParamSpec("at_f", "int", True, lo=0))
NULLABLE = (
    ParamSpec("n", "int", lo=0, hi=11, nullable=True),
    ParamSpec("m", "int", lo=0),
    ParamSpec("r", "int", True, nullable=True),
    ParamSpec("d", "int", default=5, nullable=True),
)


def _nullable(params: dict[str, object]) -> tuple[dict[str, object], list[Issue]]:
    return check_params(NULLABLE, {"r": 1, **params}, "p", "G03", BRAND)


def test_params_a_null_with_nullable_is_valid_and_comes_back_as_none() -> None:
    out, issues = _nullable({"n": None})
    assert issues == [] and "n" in out and out["n"] is None


def test_params_a_nullable_that_is_not_given_is_left_out_and_not_none() -> None:
    out, issues = _nullable({})
    assert issues == [] and "n" not in out  # not given is not null
    assert out == {"r": 1, "d": 5}


def test_params_a_null_without_nullable_is_an_issue_as_before() -> None:
    out, issues = _nullable({"m": None})
    assert [i.path for i in issues] == ["p.m"] and "m" not in out


def test_params_a_nullable_still_checks_what_is_not_null() -> None:
    assert _nullable({"n": 0})[0]["n"] == 0 and _nullable({"n": 11})[0]["n"] == 11
    assert [i.path for i in _nullable({"n": 12})[1]] == ["p.n"]
    assert [i.path for i in _nullable({"n": -1})[1]] == ["p.n"]
    assert [i.path for i in _nullable({"n": "3"})[1]] == ["p.n"]
    assert [i.path for i in _nullable({"n": 1.5})[1]] == ["p.n"]


def test_params_a_required_nullable_needs_to_be_given_but_may_be_null() -> None:
    _, issues = check_params(NULLABLE, {}, "p", "G03", BRAND)
    assert [(i.path, i.message_es) for i in issues] == [("p.r", "falta (es obligatorio)")]
    out, issues = check_params(NULLABLE, {"r": None}, "p", "G03", BRAND)
    assert issues == [] and out["r"] is None


def test_params_a_null_with_nullable_beats_a_default_that_is_not_none() -> None:
    out, issues = _nullable({"d": None})
    assert issues == [] and out["d"] is None


def test_params_a_nullable_works_for_every_kind() -> None:
    specs = (
        ParamSpec("o", "object", item=ITEM, nullable=True),
        ParamSpec("l", "list", item=ITEM, nullable=True),
        ParamSpec("p", "point", nullable=True),
        ParamSpec("c", "color", nullable=True),
        ParamSpec("s", "str", nullable=True),
        ParamSpec("b", "bool", nullable=True),
    )
    given = {"o": None, "l": None, "p": None, "c": None, "s": None, "b": None}
    assert check_params(specs, given, "p", "G03", BRAND) == (given, [])
