"""The registry of graphic components and the check of their parameters (spec S1.6a, 001.15).

`COMPONENTS` is what Claude may write in `graphics.json`: `title`, `label`, `kinetic` and
`endcard`, and the showpieces of S1.7 (`components_showpiece.py`). `captions` is internal: kcut
draws it from the words of the cut, and writing it as a cue is a G02. The page and the catalog do
need it, so `page_component` finds it too.
"""

from collections.abc import Callable
from typing import Any

from kcut.config.model import BrandSection
from kcut.gfx.components_base import BASE, CAPTIONS, ComponentDef
from kcut.gfx.components_showpiece import SHOWPIECE
from kcut.issues import Issue
from kcut.params import check_params
from kcut.schema_util import join_path

__all__ = [
    "CAPTIONS",
    "COMPONENTS",
    "ComponentDef",
    "page_component",
    "validate_params",
]
CODE = "G03"
COMPONENTS: dict[str, ComponentDef] = {c.id: c for c in (*BASE, *SHOWPIECE) if c.id != CAPTIONS.id}


def page_component(component_id: str) -> ComponentDef | None:
    """The component a page may include: any registered one, and the internal `captions`."""
    if component_id == CAPTIONS.id:
        return CAPTIONS
    return COMPONENTS.get(component_id)


def validate_params(
    component: ComponentDef, params: object, path: str, brand: BrandSection
) -> tuple[dict[str, object], list[Issue]]:
    """The `params` of a cue of `component` with their defaults applied and their colors in hex,
    and the G03 issues: those of `check_params` and the rules of the component itself."""
    checked, issues = check_params(component.params, params, path, CODE, brand)
    rule = _RULES.get(component.id)
    if rule is not None:
        issues.extend(rule(checked, path, brand))
    return checked, issues


def _title(params: dict[str, Any], _path: str, brand: BrandSection) -> list[Issue]:
    """The text is dark over a bar and light without it, and only the one without a bar has the
    dark border (the bar is already what makes it readable)."""
    bar = params.get("bar", True) is True
    params.setdefault("color", brand.dark if bar else brand.light)
    params.setdefault("stroke", not bar)
    return []


def _growing(params: dict[str, Any], key: str, path: str, what: str) -> list[Issue]:
    """The elements of the list `key` come in order: the `at_f` of each one is larger than the one
    of the element before (`what` names it in the message), so every one has a time of its own (a
    G03 on each one that is not; the next one is compared with the last good one)."""
    issues: list[Issue] = []
    items = params.get(key)
    previous = -1
    for i, item in enumerate(items if isinstance(items, list) else []):
        at_f = item.get("at_f") if isinstance(item, dict) else None
        if not isinstance(at_f, int):
            continue  # it did not pass `check_params`: that already said so
        if at_f <= previous:
            where = join_path(join_path(join_path(path, key), i), "at_f")
            message = f"debe ser mayor que el at_f del {what} anterior"
            issues.append(Issue(CODE, "error", where, message))
        else:
            previous = at_f
    return issues


def _steps(params: dict[str, Any], path: str, _brand: BrandSection) -> list[Issue]:
    """The steps come in order, each with a time of its own on screen (`_growing`)."""
    return _growing(params, "items", path, "paso")


# What a sticker may do on the way in, while it is there and on the way out (S1.7). `ParamSpec` has
# no kind for a choice, so each one is a text and the choice is checked here, as a G03.
_STICKER_CHOICES = (
    ("enter", ("drop", "pop")),
    ("idle", ("bob", "none")),
    ("exit", ("none", "pop", "fly_to")),
)


def _sticker(params: dict[str, Any], path: str, _brand: BrandSection) -> list[Issue]:
    """The points of `path` come in order (`_growing`); `enter`, `idle` and `exit` are one of their
    choices; and `fly_to` goes with `exit = fly_to` and with no other (001.34, point 2): it is
    required then (`falta`) and it is left over otherwise (`sobra`). With an `exit` that is not one
    of the choices there is already a G03 and `fly_to` is not judged."""
    issues = _growing(params, "path", path, "punto")
    for name, allowed in _STICKER_CHOICES:
        value = params.get(name)
        if isinstance(value, str) and value not in allowed:
            message = f"debe ser uno de: {', '.join(allowed)}"
            issues.append(Issue(CODE, "error", join_path(path, name), message))
    leaving = params.get("exit")
    if leaving in ("none", "pop", "fly_to"):
        where = join_path(path, "fly_to")
        given = "fly_to" in params
        if leaving == "fly_to" and not given:
            issues.append(Issue(CODE, "error", where, "falta (es obligatorio con exit=fly_to)"))
        elif leaving != "fly_to" and given:
            issues.append(Issue(CODE, "error", where, "sobra (solo va con exit=fly_to)"))
    return issues


def _holo_board(params: dict[str, Any], path: str, _brand: BrandSection) -> list[Issue]:
    """`text` has at least one character (`ParamSpec` bounds the length above only), and
    `accent_index` falls inside it (001.34, point 2): an index that does not is a G03."""
    issues: list[Issue] = []
    text = params.get("text")
    if not isinstance(text, str):
        return issues  # it did not pass `check_params`: that already said so
    if not text:
        message = "debe tener al menos 1 carácter (tiene 0)"
        issues.append(Issue(CODE, "error", join_path(path, "text"), message))
    index = params.get("accent_index")  # a number, `None` (null) or not there at all
    if isinstance(index, int) and index >= len(text):
        message = "accent_index apunta fuera del texto"
        issues.append(Issue(CODE, "error", join_path(path, "accent_index"), message))
    return issues


_RULES: dict[str, Callable[[dict[str, Any], str, BrandSection], list[Issue]]] = {
    "title": _title,
    "steps": _steps,
    "sticker": _sticker,
    "holo_board": _holo_board,
}
