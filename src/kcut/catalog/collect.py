"""Build the catalog (spec S1.9a, D8): the registries of the engine plus the static and the
planned items. What the registries hold is not copied by hand: the texts, the costs and the
parameters of a graphic component, a look or a sound effect are the ones in their own definitions.
"""

from kcut.audio.sfx_library import SFX
from kcut.catalog.model import CATEGORIES, CatalogItem, Cost, params_of
from kcut.catalog.planned import PLANNED
from kcut.catalog.static_items import STATIC
from kcut.errors import InternalError
from kcut.gfx.components import CAPTIONS, COMPONENTS
from kcut.render.looks import LOOKS

_GRAPHICS_SLICE = "S1.6"  # only if a component forgets to say it; each one has its own `since`
_LOOKS_SINCE = "S1.5"
_SFX_SINCE = "S1.8"
_COSTS: dict[str, Cost] = {"bajo": "bajo", "medio": "medio", "alto": "alto"}


def collect() -> list[CatalogItem]:
    """Every item of the catalog, by category in the order of `CATEGORIES` and, inside it, the
    available ones in the order of their registry and then the planned ones. Two items with the
    same id in one category are an InternalError: the ids are what Claude writes in the files."""
    items = [*_graphics(), *_looks(), *_sfx(), *STATIC, *PLANNED]
    items.sort(key=lambda item: CATEGORIES.index(item.category))  # stable: keeps the order inside
    seen: set[tuple[str, str]] = set()
    for item in items:
        key = (item.category, item.id)
        if key in seen:
            raise InternalError(f"el catálogo repite {item.category}/{item.id}")
        seen.add(key)
    return items


def _graphics() -> list[CatalogItem]:
    return [
        CatalogItem(
            category="graphic",
            id=c.id,
            name_es=c.name_es,
            purpose_es=c.purpose_es,
            avoid_es=c.avoid_es,
            status="available",
            since=c.since or _GRAPHICS_SLICE,
            cost=c.cost,
            cost_note_es=c.cost_note_es,
            params=params_of(c.params),
        )
        for c in (CAPTIONS, *COMPONENTS.values())
    ]


def _looks() -> list[CatalogItem]:
    return [
        CatalogItem(
            category="look",
            id=look.id,
            name_es=look.name_es,
            purpose_es=look.purpose_es,
            avoid_es=look.avoid_es,
            status="available",
            since=_LOOKS_SINCE,
            cost=_cost(look.cost),
        )
        for look in LOOKS.values()
    ]


def _sfx() -> list[CatalogItem]:
    return [
        CatalogItem(
            category="sfx",
            id=effect.id,
            name_es=effect.name_es,
            purpose_es=effect.purpose_es,
            avoid_es=effect.avoid_es,
            status="available",
            since=_SFX_SINCE,
            cost=_cost(effect.cost),
            params=params_of(effect.params),
        )
        for effect in SFX.values()
    ]


def _cost(value: str) -> Cost:
    """The cost a registry gives, checked: it is `bajo`, `medio` or `alto` or it is a bug."""
    try:
        return _COSTS[value]
    except KeyError:
        raise InternalError(f"un costo del catálogo no es bajo, medio ni alto: {value!r}") from None
