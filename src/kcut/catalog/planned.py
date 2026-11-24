"""What the engine does not do yet but the spec plans (spec S1.9a): `status: planned`, with the
phase that will make it. Claude does not offer these as ideas: they are here so that the catalog
says what is missing and not only what is there. `face_follow`, `hand_track` and `privacy_blur`
are not here on purpose: Yedin discarded them on 26/10/2026 (D22, spec 001.39), and so is
`matte_captions` (23/11/2026, D24, spec 001.42: it needs to segment the person, the same class).
What is discarded is not proposed again.
"""

from kcut.catalog.model import CatalogItem, Category, Cost

_NOT_YET = "Todavía no existe"


def _planned(
    category: Category, id_: str, since: str, cost: Cost, name: str, purpose: str
) -> CatalogItem:
    return CatalogItem(
        category=category,
        id=id_,
        name_es=name,
        purpose_es=purpose,
        avoid_es=_NOT_YET,
        status="planned",
        since=since,
        cost=cost,
    )


PLANNED: tuple[CatalogItem, ...] = (
    _planned(
        "transition", "crossfade", "F2", "medio",
        "Fundido cruzado", "Pasar de una toma a otra mezclando las dos",
    ),
    _planned(
        "transition", "whip", "F2", "bajo",
        "Barrido", "Pasar de una toma a otra con un giro rápido de cámara",
    ),
    _planned(
        "graphic", "lower_third", "F2", "bajo",
        "Tercio inferior", "El nombre y el cargo de quien habla, en la parte baja",
    ),
    _planned(
        "music", "beat_cut", "F4", "medio",
        "Cortes al ritmo", "Alinear los cortes con los golpes de la música",
    ),
)  # fmt: skip
