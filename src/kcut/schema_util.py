"""Hand-written strict validation helpers. Every message names the data path (Spanish)."""

import decimal
import math
import re
from collections.abc import Iterable
from typing import Any

from kcut.errors import ProjectError

_HEX = re.compile(r"#[0-9A-Fa-f]{6}")
_SHOWN_DIGITS = 20  # an integer out of range with more digits is cut to this many in messages
_KINDS = {
    bool: "booleano",
    int: "entero",
    float: "número",
    str: "texto",
    list: "lista",
    dict: "objeto",
    type(None): "nulo",
}


class SchemaError(ProjectError):
    """A value does not match its schema; `path` locates it, e.g. `spans[3].zoom`."""

    def __init__(self, path: str, detail_es: str) -> None:
        super().__init__(f"{path}: {detail_es}" if path else detail_es)
        self.path = path
        self.detail_es = detail_es


def join_path(path: str, key: str | int) -> str:
    """`spans` + 3 -> `spans[3]`; `spans[3]` + `zoom` -> `spans[3].zoom`."""
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else key


def obj(v: object, path: str) -> dict[str, Any]:
    """`v` must be a JSON object."""
    if not isinstance(v, dict):
        raise SchemaError(path, f"debe ser un objeto (vino {_describe(v)})")
    return v


def only_keys(d: dict[str, Any], allowed: set[str], path: str) -> None:
    """Reject any key that is not in `allowed`, naming it."""
    for key in sorted(d):
        if key not in allowed:
            raise SchemaError(join_path(path, key), "clave desconocida")


def req_int(
    d: dict[str, Any], key: str, path: str, lo: int | None = None, hi: int | None = None
) -> int:
    where = join_path(path, key)
    if key not in d:
        raise SchemaError(where, "falta (es obligatorio)")
    return _int(d[key], where, lo, hi)


def opt_int[D](
    d: dict[str, Any],
    key: str,
    path: str,
    default: D,
    lo: int | None = None,
    hi: int | None = None,
) -> int | D:
    if key not in d:
        return default
    return _int(d[key], join_path(path, key), lo, hi)


def req_float(
    d: dict[str, Any], key: str, path: str, lo: float | None = None, hi: float | None = None
) -> float:
    where = join_path(path, key)
    if key not in d:
        raise SchemaError(where, "falta (es obligatorio)")
    return _float(d[key], where, lo, hi)


def opt_float[D](
    d: dict[str, Any],
    key: str,
    path: str,
    default: D,
    lo: float | None = None,
    hi: float | None = None,
) -> float | D:
    if key not in d:
        return default
    return _float(d[key], join_path(path, key), lo, hi)


def req_str(
    d: dict[str, Any], key: str, path: str, max_len: int | None = None, min_len: int = 0
) -> str:
    where = join_path(path, key)
    if key not in d:
        raise SchemaError(where, "falta (es obligatorio)")
    return _str(d[key], where, max_len, min_len)


def opt_str[D](
    d: dict[str, Any],
    key: str,
    path: str,
    default: D,
    max_len: int | None = None,
    min_len: int = 0,
) -> str | D:
    if key not in d:
        return default
    return _str(d[key], join_path(path, key), max_len, min_len)


def req_bool(d: dict[str, Any], key: str, path: str) -> bool:
    where = join_path(path, key)
    if key not in d:
        raise SchemaError(where, "falta (es obligatorio)")
    return _bool(d[key], where)


def opt_bool[D](d: dict[str, Any], key: str, path: str, default: D) -> bool | D:
    if key not in d:
        return default
    return _bool(d[key], join_path(path, key))


def req_list(d: dict[str, Any], key: str, path: str) -> list[Any]:
    where = join_path(path, key)
    if key not in d:
        raise SchemaError(where, "falta (es obligatorio)")
    return _list(d[key], where)


def opt_list[D](d: dict[str, Any], key: str, path: str, default: D) -> list[Any] | D:
    if key not in d:
        return default
    return _list(d[key], join_path(path, key))


def hex_color(v: object, path: str) -> str:
    """Validate `#RRGGBB` and normalize it to upper case."""
    if not isinstance(v, str) or _HEX.fullmatch(v) is None:
        raise SchemaError(path, f"debe ser un color #RRGGBB (vino {_describe(v)})")
    return v.upper()


def one_of[T](v: T, choices: Iterable[T], path: str) -> T:
    """`v` must be one of `choices`."""
    options = list(choices)
    if v not in options:
        listed = ", ".join(str(c) for c in options)
        raise SchemaError(path, f"debe ser uno de: {listed} (vino {_describe(v)})")
    return v


def _int(v: object, where: str, lo: int | None, hi: int | None) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        raise SchemaError(where, f"debe ser un entero (vino {_describe(v)})")
    _check_range(v, where, lo, hi)
    return v


def _float(v: object, where: str, lo: float | None, hi: float | None) -> float:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        raise SchemaError(where, f"debe ser un número finito (vino {_describe(v)})")
    _check_range(v, where, lo, hi)
    return float(v)


def _str(v: object, where: str, max_len: int | None, min_len: int) -> str:
    if not isinstance(v, str):
        raise SchemaError(where, f"debe ser texto (vino {_describe(v)})")
    if len(v) < min_len or (max_len is not None and len(v) > max_len):
        if max_len is None:
            span = f"al menos {min_len} caracteres"
        else:
            span = f"entre {min_len} y {max_len} caracteres"
        raise SchemaError(where, f"debe tener {span} (tiene {len(v)})")
    return v


def _bool(v: object, where: str) -> bool:
    if not isinstance(v, bool):
        raise SchemaError(where, f"debe ser verdadero o falso (vino {_describe(v)})")
    return v


def _list(v: object, where: str) -> list[Any]:
    if not isinstance(v, list):
        raise SchemaError(where, f"debe ser una lista (vino {_describe(v)})")
    return v


def _check_range(v: float, where: str, lo: float | None, hi: float | None) -> None:
    if lo is not None and hi is not None:
        if not lo <= v <= hi:
            raise SchemaError(where, f"debe estar entre {lo} y {hi} (vino {_shown(v)})")
    elif lo is not None and v < lo:
        raise SchemaError(where, f"debe ser como mínimo {lo} (vino {_shown(v)})")
    elif hi is not None and v > hi:
        raise SchemaError(where, f"debe ser como máximo {hi} (vino {_shown(v)})")


def _shown(v: float) -> str:
    """A value out of range as it goes into the message. An integer of more than 20 digits shows
    its first 20 and how many it has (`str()` of one over 4300 digits raises ValueError, and a
    hostile file could carry thousands of digits)."""
    if isinstance(v, int):
        digits = decimal.Decimal(abs(v)).as_tuple().digits  # exact; no str() of the whole number
        if len(digits) > _SHOWN_DIGITS:
            head = "".join(str(d) for d in digits[:_SHOWN_DIGITS])
            return f"{'-' if v < 0 else ''}{head}… ({len(digits)} dígitos)"
    return str(v)


def _describe(v: object) -> str:
    """Short rendering of a bad value for messages: its type for containers, repr otherwise."""
    kind = _KINDS.get(type(v), type(v).__name__)
    if isinstance(v, list | dict):
        return kind
    text = repr(v)
    return text if len(text) <= 40 else text[:37] + "..."
