"""Small readers of the EDL parser (spec 001.24, points 4, 5 and 6): the limits of what an EDL may
hold and the way a schema error is told without repeating what the file said. Pure.
"""

import re
from typing import Any

from kcut.issues import Issue
from kcut.schema_util import SchemaError, hex_color, opt_int, req_int

MAX_ITEMS = 10_000  # clips, and spans: a reel has under 500, an hour of talk about 2 000
MAX_WHOLE = 10**15 - 1  # a whole number of the EDL, in either direction
_QUOTED = re.compile(r"\(vino (['\"]).*\)$", re.DOTALL)  # the `(vino 'text')` of `schema_util`


def plain(detail: str) -> str:
    """`detail` of a SchemaError without the text of the file: `(vino 'IGNORE...')` is cut to
    `(vino <texto>)` (001.24, point 6). What it shows of a number or a type stays."""
    return _QUOTED.sub("(vino <texto>)", detail)


def e01(issues: list[Issue], exc: SchemaError) -> None:
    issues.append(Issue("E01", "error", exc.path, plain(exc.detail_es)))


def whole(d: dict[str, Any], key: str, path: str) -> int:
    """A required whole number, `-MAX_WHOLE` to `MAX_WHOLE`."""
    return req_int(d, key, path, -MAX_WHOLE, MAX_WHOLE)


def opt_whole[D](d: dict[str, Any], key: str, path: str, default: D) -> int | D:
    return opt_int(d, key, path, default, -MAX_WHOLE, MAX_WHOLE)


def choice(value: str, options: tuple[str, ...], path: str) -> str:
    """`value` must be one of `options`; the message does not repeat it."""
    if value not in options:
        raise SchemaError(path, f"debe ser uno de: {', '.join(options)}")
    return value


def color(value: object, path: str) -> str:
    """`#RRGGBB`; if it is not, the message does not repeat what the file said."""
    try:
        return hex_color(value, path)
    except SchemaError:
        raise SchemaError(path, "debe ser un color #RRGGBB") from None
