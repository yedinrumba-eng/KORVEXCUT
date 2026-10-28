"""The showpiece graphic components: what each one is, which parameters it takes and what it costs
(spec S1.7, 001.15). The code that draws them is in `web/components/<id>.js`.

Same shape as `components_base.py` (`ComponentDef` lives there, so this module never imports
`components.py`, which imports it): `components.py` registers `SHOWPIECE` next to `BASE`, and
`kcut catalog` publishes these texts (D8: one source of truth). Positions `x`, `y` are the center of
the element as a fraction of the width or of the height of the picture, and every `at_f` is
relative to the start of the cue (spec S1.6, `graphics.json`).
"""

from kcut.gfx.components_base import ComponentDef
from kcut.params import ParamSpec

_COLOR_HELP = "color: #RRGGBB o accent, accent2, dark, light"


def _frac(name: str, default: float, help_es: str) -> ParamSpec:
    """A position as a fraction of the width or of the height of the picture."""
    return ParamSpec(name, "float", default=default, lo=0.0, hi=1.0, help_es=help_es)


_STEP = (
    ParamSpec(
        "at_f",
        "int",
        True,
        lo=0,
        help_es="frame del cue en que entra el paso (cada paso mayor que el anterior)",
    ),
    ParamSpec(
        "label", "str", True, max_len=12, help_es="la etiqueta del paso (hasta 12 caracteres)"
    ),
    ParamSpec("text", "str", True, max_len=40, help_es="lo que dice el paso (hasta 40 caracteres)"),
)

STEPS = ComponentDef(
    id="steps",
    js_files=("steps.js",),
    big=False,
    params=(
        ParamSpec(
            "items",
            "list",
            True,
            lo=1,
            hi=8,
            item=_STEP,
            help_es="de 1 a 8 pasos, en orden de at_f",
        ),
        _frac("y", 0.136, "centro vertical del panel, fraccion del alto"),
        ParamSpec(
            "badge", "color", default="accent", help_es=f"color de la etiqueta; {_COLOR_HELP}"
        ),
        ParamSpec("panel", "color", default="dark", help_es=f"color del panel; {_COLOR_HELP}"),
        ParamSpec("ring", "color", default="accent", help_es=f"color del anillo; {_COLOR_HELP}"),
    ),
    name_es="Pasos",
    purpose_es=(
        "Los pasos de un proceso, uno a la vez, en un panel arriba mientras se ve la pantalla"
    ),
    avoid_es="No lo uses sin una pantalla debajo que muestre el paso: solo, no explica nada",
    cost="bajo",
    cost_note_es="captura HTML ~35 ms por frame mientras esta en pantalla",
    since="S1.7",
)


def _req_frac(name: str, help_es: str) -> ParamSpec:
    """A required position (inside an object or an element of a list), a fraction of the picture."""
    return ParamSpec(name, "float", True, lo=0.0, hi=1.0, help_es=help_es)


_PATH_POINT = (
    ParamSpec(
        "at_f",
        "int",
        True,
        lo=0,
        help_es="frame del cue en que los pies pasan por aqui (cada punto, mayor que el anterior)",
    ),
    _req_frac("x", "pies: centro horizontal, fraccion del ancho"),
    _req_frac("y", "pies: vertical, fraccion del alto"),
)
_FLY_TO = (
    _req_frac("x", "donde cae: horizontal, fraccion del ancho"),
    _req_frac("y", "donde cae: vertical, fraccion del alto"),
    ParamSpec("at_f", "int", True, lo=0, help_es="frame del cue en que sale volando"),
)

STICKER = ComponentDef(
    id="sticker",
    js_files=("sticker.js",),
    big=False,
    params=(
        ParamSpec(
            "image",
            "path",
            True,
            help_es="imagen en recursos/ (.png .webp .jpg), aprobada en recursos/recursos.json",
        ),
        ParamSpec("w_px", "int", default=280, lo=40, hi=900, help_es="ancho de la imagen en px"),
        _frac("x", 0.5, "pies: centro horizontal, fraccion del ancho"),
        _frac("y", 0.6, "pies: punto vertical, fraccion del alto"),
        ParamSpec(
            "path",
            "list",
            item=_PATH_POINT,
            help_es="camino de los pies: puntos {at_f, x, y}, en linea recta de uno a otro",
        ),
        ParamSpec("enter", "str", default="drop", help_es="como entra: drop (cae y rebota) o pop"),
        ParamSpec("idle", "str", default="bob", help_es="mientras esta: bob (flota) o none"),
        ParamSpec("exit", "str", default="pop", help_es="como sale: none, pop o fly_to"),
        ParamSpec(
            "fly_to",
            "object",
            item=_FLY_TO,
            help_es="adonde vuela {x, y, at_f}; obligatorio con exit=fly_to, sobra con otro exit",
        ),
        ParamSpec("glow", "bool", default=True, help_es="brillo bajo los pies y halo de color"),
        ParamSpec(
            "glow_color", "color", default="accent", help_es=f"color del brillo; {_COLOR_HELP}"
        ),
        ParamSpec("sparkles", "bool", default=True, help_es="siete destellos alrededor"),
        ParamSpec("seed", "int", default=7, lo=1, help_es="semilla de los destellos (1 o mas)"),
    ),
    name_es="Sticker",
    purpose_es=(
        "Una imagen aprobada (mascota, logo) que cae sobre un punto, flota "
        "y se va o vuela a otro lado"
    ),
    avoid_es=(
        "No lo pongas encima de la cara ni uses una imagen que no este en recursos.json; "
        "elige el punto mirando kcut frames y compruebalo con kcut graphics still"
    ),
    cost="medio",
    cost_note_es="captura HTML con imagen y sombras ~55 ms por frame mientras esta en pantalla",
    since="S1.7",
)

_BEAM = (
    _req_frac("x", "origen del rayo: horizontal, fraccion del ancho"),
    _req_frac("y", "origen del rayo: vertical, fraccion del alto"),
)

HOLO_BOARD = ComponentDef(
    id="holo_board",
    js_files=("holo_board.js",),
    big=True,
    params=(
        ParamSpec("label", "str", default="", max_len=24, help_es="etiqueta arriba a la izquierda"),
        ParamSpec(
            "corner_text", "str", default="", max_len=24, help_es="texto arriba a la derecha"
        ),
        ParamSpec(
            "text",
            "str",
            True,
            max_len=12,
            help_es="lo que se escribe en el tablero (1 a 12 letras)",
        ),
        ParamSpec(
            "type_at_f",
            "int",
            True,
            lo=0,
            help_es="frame del cue en que cae la ultima letra (las otras caen antes)",
        ),
        ParamSpec(
            "type_step_f",
            "int",
            default=4,
            lo=1,
            hi=15,
            help_es="frames entre una letra y la siguiente",
        ),
        ParamSpec(
            "accent_index",
            "int",
            lo=0,
            hi=11,
            nullable=True,
            help_es="letra en color de acento: sin ponerlo, la ultima; null, ninguna",
        ),
        ParamSpec(
            "born",
            "point",
            default={"x": 0.479, "y": 0.199},
            lo=0.0,
            hi=1.0,
            help_es="de donde nace el tablero {x, y}, fraccion de la imagen",
        ),
        ParamSpec(
            "center",
            "point",
            default={"x": 0.5, "y": 0.448},
            lo=0.0,
            hi=1.0,
            help_es="donde queda el centro del tablero {x, y}, fraccion de la imagen",
        ),
        ParamSpec("w_px", "int", default=860, lo=100, hi=2000, help_es="ancho del tablero en px"),
        ParamSpec("h_px", "int", default=500, lo=100, hi=2000, help_es="alto del tablero en px"),
        ParamSpec("color", "color", default="#6FF6FF", help_es=f"color del tablero; {_COLOR_HELP}"),
        ParamSpec(
            "beams_from",
            "list",
            default=[],
            lo=0,
            hi=2,
            item=_BEAM,
            help_es="de 0 a 2 puntos {x, y} de donde salen rayos a las esquinas del tablero",
        ),
    ),
    name_es="Tablero holografico",
    purpose_es=(
        "Un tablero que nace entre las manos, con rejilla y barrido, "
        "y en el que se escribe una palabra"
    ),
    avoid_es=(
        "No lo uses mas de una vez por video ni con palabras de mas de 12 letras: tapa la pantalla"
    ),
    cost="alto",
    cost_note_es="captura HTML con sombras grandes y 3D ~85 ms por frame mientras esta en pantalla",
    since="S1.7",
)

GLOBE = ComponentDef(
    id="globe",
    js_files=("globe.js",),
    big=False,
    params=(
        _frac("x", 0.306, "centro horizontal, fraccion del ancho"),
        _frac("y", 0.396, "centro vertical, fraccion del alto"),
        ParamSpec("r_px", "int", default=190, lo=40, hi=500, help_es="radio del globo en px"),
        ParamSpec("color", "color", default="accent", help_es=f"color del globo; {_COLOR_HELP}"),
        ParamSpec(
            "spin", "float", default=1.4, lo=0.0, hi=6.0, help_es="giro en radianes por segundo"
        ),
        ParamSpec(
            "tilt", "float", default=0.38, lo=0.0, hi=1.2, help_es="inclinacion del eje, rad"
        ),
        ParamSpec("dots", "int", default=70, lo=0, hi=200, help_es="puntos sobre la superficie"),
        ParamSpec("seed", "int", default=7, lo=1, help_es="semilla de los puntos (1 o mas)"),
    ),
    name_es="Globo",
    purpose_es="Un globo que gira: lo global, internet, un alcance, un lugar en el mundo",
    avoid_es="No lo pongas sobre la cara ni lo repitas: es un adorno, no la idea",
    cost="medio",
    cost_note_es="captura HTML con canvas ~70 ms por frame mientras esta en pantalla",
    since="S1.7",
)

SHOWPIECE: tuple[ComponentDef, ...] = (STEPS, STICKER, HOLO_BOARD, GLOBE)
