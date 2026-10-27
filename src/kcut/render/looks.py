"""The looks: ffmpeg chains of RGB-only filters that give a shot its color (spec S1.5b, DS3, D10).

A look runs in the frame reader, between the explicit bt709 conversion to RGB and the one to BGR
(`ff.reader.reader_args`). A filter that only takes YUV would make ffmpeg add a hidden conversion
with the bt601 matrix, so every chain here works on RGB.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from kcut.config.model import BrandSection

_HEX = re.compile(r"#([0-9A-Fa-f]{6})")


@dataclass(frozen=True)
class LookDef:
    """One look: its id, its chain (`RRGGBB` stands for the accent in `bn-acento`), what Claude
    reads in the catalog, and how much it costs to render (`bajo`, `medio` or `alto`)."""

    id: str
    chain: str
    name_es: str
    purpose_es: str
    avoid_es: str
    cost: str


LOOKS: Mapping[str, LookDef] = {
    look.id: look
    for look in (
        LookDef(
            "neutro",
            "",
            "Neutro",
            "sin look",
            "Nada: es el punto de partida",
            "bajo",
        ),
        LookDef(
            "contraste",
            "curves=all='0/0 0.25/0.20 0.5/0.5 0.75/0.80 1/1',vibrance=intensity=0.12",
            "Contraste",
            "más punch y color",
            "No lo uses sobre piel con mucho sol: las luces se queman",
            "bajo",
        ),
        LookDef(
            "calido",
            "colorbalance=rs=0.04:bs=-0.04:rm=0.03:bm=-0.03:rh=0.02:bh=-0.02,"
            "vibrance=intensity=0.05",
            "Cálido",
            "piel cálida, interiores",
            "No lo uses con luz ya anaranjada: la piel se ve quemada",
            "bajo",
        ),
        LookDef(
            "frio",
            "colorbalance=rs=-0.04:bs=0.05:rm=-0.03:bm=0.04:rh=-0.01:bh=0.02",
            "Frío",
            "tech, noche",
            "No lo uses sobre caras en exteriores: se ven enfermas",
            "bajo",
        ),
        LookDef(
            "cinematico",
            "curves=all='0/0.02 0.25/0.21 0.5/0.5 0.75/0.79 1/0.98',"
            "colorbalance=rs=-0.05:gs=0.01:bs=0.05:rh=0.05:gh=0.01:bh=-0.04,"
            "vibrance=intensity=-0.08,vignette=angle=0.5",
            "Cinemático",
            "teal-naranja suave con viñeta",
            "No lo uses en el fondo de una pantalla ni en tomas ya oscuras",
            "medio",
        ),
        LookDef(
            "bn-acento",
            "colorhold=color=0xRRGGBB:similarity=0.25:blend=0.10",
            "Blanco y negro con acento",
            "blanco y negro salvo el color de marca",
            "No lo uses si el color de marca no aparece en la toma: queda todo gris",
            "bajo",
        ),
    )
}


def look_chain(look_id: str, brand: BrandSection) -> str:
    """The chain of look `look_id` for the brand of the project. `bn-acento` holds the accent of
    the brand, which has to be `#RRGGBB`. An id that is not a look is a ValueError: the EDL is
    checked (E14) before anything renders."""
    look = LOOKS.get(look_id)
    if look is None:
        raise ValueError(f"look desconocido: {look_id!r}")
    if "RRGGBB" not in look.chain:
        return look.chain
    found = _HEX.fullmatch(brand.accent)
    if found is None:
        raise ValueError(f"el acento de la marca no es #RRGGBB: {brand.accent!r}")
    return look.chain.replace("RRGGBB", found.group(1).upper())
