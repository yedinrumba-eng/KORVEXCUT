"""Parameters of what Claude writes in a JSON file, and their check (spec S1.6a, 001.15 T1).

A `ParamSpec` says what one parameter is; `check_params` applies a list of them to the `params`
object of a cue (graphics, code G03) or of an event (sfx, code A03). Neutral on purpose: it
imports nothing from `gfx` or `audio`, so they can both use it without importing each other.

Strict like `schema_util`: a `bool` is not a number, a whole number is a valid float, an unknown
parameter is an error. A message never repeats a text of the file (it says its length) nor the name
of an unknown parameter: the file is somebody else's and Claude reads what is printed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

from kcut.config.model import BrandSection
from kcut.errors import InternalError
from kcut.issues import Issue
from kcut.schema_util import UNKNOWN_KEY, describe_value, join_path

Kind = Literal["str", "int", "float", "bool", "color", "point", "path", "list", "object"]
BRAND_TOKENS = ("accent", "accent2", "dark", "light")
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")
_BAD = object()  # a value that did not pass: it is not put in the result


@dataclass(frozen=True)
class ParamSpec:
    """One parameter. `kind`:

    - `str` (at most `max_len` characters), `int`, `float` (a whole number is fine), `bool`;
    - `color`: `#RRGGBB` or a token of the brand (`accent accent2 dark light`), returned as hex;
    - `point`: an object `{"x": number, "y": number}`, each between `lo` and `hi`;
    - `path`: a text with a path relative to the project (the file is checked by whoever uses it);
    - `list`: between `lo` and `hi` objects, each one checked against the specs in `item`;
    - `object` (001.34): one object whose keys are checked against the specs in `item`, as an
      element of a `list` is; it comes back as a `dict` with its defaults applied, and a key that
      is not in `item` is the usual error.

    `lo` and `hi` bound a number (or the count of a list). An optional parameter whose `default`
    is `None` is left out of the result when it is not given. With `nullable` (001.34), a JSON
    `null` is a valid value of any kind and comes back as `None` in the result: that is not the
    same as not being given, which leaves the parameter out (or gives its default)."""

    name: str
    kind: Kind
    required: bool = False
    default: object = None
    lo: float | None = None
    hi: float | None = None
    max_len: int | None = None
    item: tuple[ParamSpec, ...] | None = None
    help_es: str = ""
    nullable: bool = False


def check_params(
    specs: tuple[ParamSpec, ...] | list[ParamSpec],
    params: object,
    path: str,
    code: str,
    brand: BrandSection | None,
) -> tuple[dict[str, object], list[Issue]]:
    """`params` against `specs`: the parameters with their defaults applied, and one `Issue`
    (with `code`, as an error) for each problem, located from `path` (`cues[2].params`).

    A color needs `brand` to turn a token into hex: with `brand=None` and a color to check it is
    an `InternalError`, a bug of whoever called, not a mistake in the file."""
    issues: list[Issue] = []
    if not isinstance(params, dict):
        issues.append(_issue(code, path, f"debe ser un objeto (vino {_shown(params)})"))
        return {}, issues
    known = {spec.name for spec in specs}
    for key in params:
        if key not in known:
            issues.append(_issue(code, join_path(path, UNKNOWN_KEY), "parámetro desconocido"))
    out: dict[str, object] = {}
    for spec in specs:
        where = join_path(path, spec.name)
        if spec.name in params:
            value = _check(spec, params[spec.name], where, code, brand, issues)
        elif spec.required:
            issues.append(_issue(code, where, "falta (es obligatorio)"))
            continue
        elif spec.default is None:
            continue
        else:
            value = _check(spec, spec.default, where, code, brand, issues)
        if value is not _BAD:
            out[spec.name] = value
    return out, issues


def _issue(code: str, path: str, message: str) -> Issue:
    return Issue(code, "error", path, message)


def _shown(value: object) -> str:
    """A value as it goes in a message: a text is only its length."""
    if isinstance(value, str):
        return f"<texto, {len(value)} car.>"
    return describe_value(value)


def _num(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


def _check(
    spec: ParamSpec,
    value: object,
    where: str,
    code: str,
    brand: BrandSection | None,
    issues: list[Issue],
) -> object:
    """`value` as the spec wants it, or `_BAD` (and an issue) if it does not pass."""
    if value is None and spec.nullable:
        return None
    kind = spec.kind
    if kind in ("str", "path"):
        return _text(spec, value, where, code, issues)
    if kind in ("int", "float"):
        return _number(spec, value, where, code, issues)
    if kind == "bool":
        if isinstance(value, bool):
            return value
        issues.append(_issue(code, where, f"debe ser verdadero o falso (vino {_shown(value)})"))
        return _BAD
    if kind == "color":
        return _color(value, where, code, brand, issues)
    if kind == "point":
        return _point(spec, value, where, code, issues)
    if kind == "object":
        return _object(spec, value, where, code, brand, issues)
    return _items(spec, value, where, code, brand, issues)


def _text(spec: ParamSpec, value: object, where: str, code: str, issues: list[Issue]) -> object:
    if not isinstance(value, str):
        issues.append(_issue(code, where, f"debe ser texto (vino {_shown(value)})"))
        return _BAD
    if spec.max_len is not None and len(value) > spec.max_len:
        message = f"debe tener como máximo {spec.max_len} caracteres (tiene {len(value)})"
        issues.append(_issue(code, where, message))
        return _BAD
    return value


def _number(spec: ParamSpec, value: object, where: str, code: str, issues: list[Issue]) -> object:
    whole = spec.kind == "int"
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or (whole and not isinstance(value, int))
    ):
        kind = "un entero" if whole else "un número"
        issues.append(_issue(code, where, f"debe ser {kind} (vino {_shown(value)})"))
        return _BAD
    if not _finite(value):
        issues.append(_issue(code, where, f"debe ser un número finito (vino {_shown(value)})"))
        return _BAD
    if not _in_range(value, spec.lo, spec.hi):
        issues.append(_issue(code, where, _range_message(spec, value)))
        return _BAD
    return value if whole else float(value)


def _finite(value: float) -> bool:
    try:
        return math.isfinite(value)
    except OverflowError:  # an integer too big for a float
        return False


def _in_range(value: float, lo: float | None, hi: float | None) -> bool:
    return (lo is None or value >= lo) and (hi is None or value <= hi)


def _range_message(spec: ParamSpec, value: float) -> str:
    seen = _shown(value)
    if spec.lo is not None and spec.hi is not None:
        return f"debe estar entre {_num(spec.lo)} y {_num(spec.hi)} (vino {seen})"
    if spec.lo is not None:
        return f"debe ser como mínimo {_num(spec.lo)} (vino {seen})"
    return f"debe ser como máximo {_num(spec.hi or 0)} (vino {seen})"


def _color(
    value: object, where: str, code: str, brand: BrandSection | None, issues: list[Issue]
) -> object:
    if brand is None:
        raise InternalError("check_params: un parámetro color necesita la marca (brand)")
    if isinstance(value, str) and value in BRAND_TOKENS:
        return str(getattr(brand, value))
    if isinstance(value, str) and _HEX.fullmatch(value):
        return value.upper()
    message = f"debe ser un color #RRGGBB o uno de {', '.join(BRAND_TOKENS)}"
    issues.append(_issue(code, where, message))
    return _BAD


def _point(spec: ParamSpec, value: object, where: str, code: str, issues: list[Issue]) -> object:
    if not isinstance(value, dict) or set(value) != {"x", "y"}:
        issues.append(_issue(code, where, 'debe ser un objeto con "x" y "y"'))
        return _BAD
    axis = ParamSpec("", "float", True, None, spec.lo, spec.hi)
    xy = {k: _number(axis, value[k], join_path(where, k), code, issues) for k in ("x", "y")}
    return _BAD if _BAD in xy.values() else xy


def _object(
    spec: ParamSpec,
    value: object,
    where: str,
    code: str,
    brand: BrandSection | None,
    issues: list[Issue],
) -> object:
    """An object against the specs in `item`, as an element of a list is (001.34): its keys are
    located under `where`, and what it gives back has the defaults applied."""
    if spec.item is None:
        raise InternalError("check_params: un objeto necesita sus ParamSpec en item")
    checked, problems = check_params(spec.item, value, where, code, brand)
    issues.extend(problems)
    return checked


def _items(
    spec: ParamSpec,
    value: object,
    where: str,
    code: str,
    brand: BrandSection | None,
    issues: list[Issue],
) -> object:
    if spec.item is None:
        raise InternalError("check_params: una lista necesita sus ParamSpec en item")
    if not isinstance(value, list):
        issues.append(_issue(code, where, f"debe ser una lista (vino {_shown(value)})"))
        return _BAD
    if not _in_range(len(value), spec.lo, spec.hi):
        issues.append(_issue(code, where, _count_message(spec, len(value))))
        return _BAD
    found: list[object] = []
    for i, element in enumerate(value):
        checked, problems = check_params(spec.item, element, f"{where}[{i}]", code, brand)
        issues.extend(problems)
        found.append(checked)
    return found


def _count_message(spec: ParamSpec, count: int) -> str:
    if spec.lo is not None and spec.hi is not None:
        wanted = f"entre {_num(spec.lo)} y {_num(spec.hi)} elementos"
    elif spec.lo is not None:
        wanted = f"al menos {_num(spec.lo)} elementos"
    else:
        wanted = f"como máximo {_num(spec.hi or 0)} elementos"
    return f"debe tener {wanted} (tiene {count})"
