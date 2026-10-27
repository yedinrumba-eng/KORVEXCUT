"""The registry of graphic components and the check of their parameters (spec S1.6a, 001.15).

`COMPONENTS` is what Claude may write in `graphics.json`: `title`, `label`, `kinetic` and
`endcard` (from S1.7 also the showpieces). `captions` is internal: kcut draws it from the words of
the cut, and writing it as a cue is a G02. The page and the catalog do need it, so
`page_component` finds it too.
"""

from collections.abc import Callable
from typing import Any

from kcut.config.model import BrandSection
from kcut.gfx.components_base import BASE, CAPTIONS, ComponentDef
from kcut.issues import Issue
from kcut.params import check_params

__all__ = [
    "CAPTIONS",
    "COMPONENTS",
    "ComponentDef",
    "page_component",
    "validate_params",
]
CODE = "G03"
COMPONENTS: dict[str, ComponentDef] = {c.id: c for c in BASE if c.id != CAPTIONS.id}


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


_RULES: dict[str, Callable[[dict[str, Any], str, BrandSection], list[Issue]]] = {"title": _title}
