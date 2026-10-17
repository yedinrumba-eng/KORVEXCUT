"""Small field validators shared by the `kcut.toml` section loaders."""

import re
from datetime import date
from typing import Any

from kcut.schema_util import SchemaError, hex_color, join_path, opt_list

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def hex_or_empty(d: dict[str, Any], key: str, path: str) -> str:
    """`#RRGGBB` or the empty string (meaning "use the brand color")."""
    value = d.get(key, "")
    return "" if value == "" else hex_color(value, join_path(path, key))


def string_list(
    d: dict[str, Any],
    key: str,
    path: str,
    *,
    max_items: int,
    max_len: int | None = None,
    default: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """A list of strings with at most `max_items` entries (each `1..max_len` long if given)."""
    raw = opt_list(d, key, path, None)
    where = join_path(path, key)
    if raw is None:
        return default
    if len(raw) > max_items:
        raise SchemaError(where, f"admite como máximo {max_items} elementos (vinieron {len(raw)})")
    for i, item in enumerate(raw):
        item_path = join_path(where, i)
        if not isinstance(item, str):
            raise SchemaError(item_path, f"debe ser texto (vino {item!r})")
        if max_len is not None and not 1 <= len(item) <= max_len:
            raise SchemaError(item_path, f"debe tener entre 1 y {max_len} caracteres")
    return tuple(raw)


def valid_date(text: str) -> bool:
    """`YYYY-MM-DD` and a real calendar day (matched with `fullmatch`)."""
    if _DATE.fullmatch(text) is None:
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True
