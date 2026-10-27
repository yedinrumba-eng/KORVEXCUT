"""The base graphic components: what each one is, which parameters it takes and what it costs
(spec S1.6a, 001.15). The code that draws them is in `web/components/<id>.js`.

`ComponentDef` lives here and `components.py` re-exports it, so the modules that define components
(this one and, from S1.7, `components_showpiece.py`) never have to import `components.py`, which
imports them. `kcut catalog` publishes these texts (D8: one source of truth).
"""

from dataclasses import dataclass
from typing import Literal

from kcut.params import ParamSpec

_COLOR_HELP = "color: #RRGGBB o accent, accent2, dark, light"


@dataclass(frozen=True)
class ComponentDef:
    """A graphic component. `js_files` are the files of `gfx/web/components/` that draw it, in
    the order the page includes them (a big component may have several). `big` is true for text
    that takes the screen: it hides the subtitles by default (`hide_captions`). `cost` is
    `bajo`, `medio` or `alto`; `since` is the slice that made it."""

    id: str
    js_files: tuple[str, ...]
    big: bool
    params: tuple[ParamSpec, ...]
    name_es: str
    purpose_es: str
    avoid_es: str
    cost: Literal["bajo", "medio", "alto"]
    cost_note_es: str
    since: str


def _frac(name: str, default: float, help_es: str) -> ParamSpec:
    """A position as a fraction of the width or of the height of the picture."""
    return ParamSpec(name, "float", default=default, lo=0.0, hi=1.0, help_es=help_es)


_LINE = (
    ParamSpec("text", "str", True, max_len=24, help_es="texto de la línea (hasta 24 caracteres)"),
    ParamSpec("at_f", "int", default=0, lo=0, help_es="frame del cue en que entra la línea"),
    ParamSpec("size", "int", default=140, lo=24, hi=400, help_es="alto de la letra en px"),
    ParamSpec("color", "color", default="light", help_es=_COLOR_HELP),
)

TITLE = ComponentDef(
    id="title",
    js_files=("title.js",),
    big=True,
    params=(
        ParamSpec(
            "text", "str", True, max_len=40, help_es="texto del titulo (hasta 40 caracteres)"
        ),
        _frac("y", 0.6, "centro vertical, fraccion del alto"),
        _frac("x", 0.5, "centro horizontal, fraccion del ancho"),
        ParamSpec("size", "int", default=132, lo=24, hi=400, help_es="alto de la letra en px"),
        ParamSpec("bar", "bool", default=True, help_es="barra de color detras del texto"),
        ParamSpec("bar_color", "color", default="accent", help_es=_COLOR_HELP),
        ParamSpec(
            "color",
            "color",
            help_es=f"color del texto (dark con barra, light sin ella); {_COLOR_HELP}",
        ),
        ParamSpec(
            "stroke", "bool", help_es="borde oscuro en las letras (por defecto, solo sin barra)"
        ),
    ),
    name_es="Titulo grande",
    purpose_es="Nombra la marca o la idea clave en la palabra que la dice",
    avoid_es="No lo uses sobre una cara en primer plano ni dos veces seguidas",
    cost="bajo",
    cost_note_es="captura HTML ~55 ms por frame mientras esta en pantalla",
    since="S1.6",
)

LABEL = ComponentDef(
    id="label",
    js_files=("label.js",),
    big=False,
    params=(
        ParamSpec(
            "text", "str", True, max_len=48, help_es="texto de la pildora (hasta 48 caracteres)"
        ),
        _frac("y", 0.58, "centro vertical, fraccion del alto"),
        _frac("x", 0.5, "centro horizontal, fraccion del ancho"),
        ParamSpec("size", "int", default=40, lo=16, hi=120, help_es="alto de la letra en px"),
        ParamSpec("fg", "color", default="accent", help_es=f"color del texto; {_COLOR_HELP}"),
        ParamSpec("bg", "color", default="dark", help_es=f"color del fondo; {_COLOR_HELP}"),
        ParamSpec("ring", "color", default="accent", help_es=f"color del anillo; {_COLOR_HELP}"),
    ),
    name_es="Pildora de texto",
    purpose_es="Una frase corta como nota al margen: la fuente, el dato, el nombre",
    avoid_es="No la uses para frases largas: no se leen en lo que dura en pantalla",
    cost="bajo",
    cost_note_es="captura HTML ~40 ms por frame mientras esta en pantalla",
    since="S1.6",
)

KINETIC = ComponentDef(
    id="kinetic",
    js_files=("kinetic.js",),
    big=True,
    params=(
        ParamSpec(
            "lines", "list", True, lo=1, hi=4, item=_LINE, help_es="de 1 a 4 lineas de texto"
        ),
        _frac("y", 0.5, "centro vertical del bloque"),
        ParamSpec("gap_px", "int", default=10, lo=0, hi=200, help_es="espacio entre lineas en px"),
        ParamSpec("italic", "bool", default=False, help_es="letra inclinada"),
        ParamSpec("rotate_deg", "float", default=0, lo=-15, hi=15, help_es="giro de cada linea"),
        ParamSpec(
            "glitch", "bool", default=False, help_es="sombras de color que se juntan al entrar"
        ),
    ),
    name_es="Texto cinetico",
    purpose_es="El gancho o la frase que manda: varias lineas que entran una tras otra",
    avoid_es="No lo uses mas de una vez cada pocos segundos: cansa",
    cost="bajo",
    cost_note_es="captura HTML ~55 ms por frame mientras esta en pantalla",
    since="S1.6",
)

ENDCARD = ComponentDef(
    id="endcard",
    js_files=("endcard.js",),
    big=True,
    params=(
        ParamSpec(
            "lines", "list", True, lo=1, hi=3, item=_LINE, help_es="de 1 a 3 lineas de texto"
        ),
        ParamSpec("cta", "str", max_len=40, help_es="llamada a la accion bajo las lineas"),
        ParamSpec(
            "cta_at_f", "int", default=22, lo=0, help_es="frame del cue en que entra la llamada"
        ),
        _frac("y", 0.47, "centro vertical del bloque"),
    ),
    name_es="Cierre del video",
    purpose_es="Despide y pide la accion: las lineas finales y la llamada a seguir",
    avoid_es="No lo pongas antes de que termine la idea: tapa los subtitulos",
    cost="bajo",
    cost_note_es="captura HTML ~55 ms por frame mientras esta en pantalla",
    since="S1.6",
)

CAPTIONS = ComponentDef(
    id="captions",
    js_files=("captions.js",),
    big=False,
    params=(),
    name_es="Subtitulos",
    purpose_es="Las palabras que se dicen, de a pocas, con la activa resaltada",
    avoid_es="Es interno: se enciende en kcut.toml o en graphics.json, no se escribe como cue",
    cost="bajo",
    cost_note_es="captura HTML ~45 ms por frame mientras hay un subtitulo en pantalla",
    since="S1.6",
)

BASE: tuple[ComponentDef, ...] = (TITLE, LABEL, KINETIC, ENDCARD, CAPTIONS)
