"""The library of sound effects: what each one is, how long it lasts, which parameters it takes and
how loud it is by default (spec S1.8a, 001.15). The code that makes them is `sfx_synth.py`.

`SFX` is what Claude may write as a `type` in `edit/sfx.json`. A type either has a fixed length
(`fixed_n`, in samples at 48 kHz), or lasts what `dur_f` says: with a default (`default_dur_ms`:
`whoosh` and `shimmer`) or with no default (`requires_dur`: `pad`, `typing` and `riser`). The
parameters that a type takes besides `gain`, `dur_f` and `align` (which every type has) are its
`params`, the seed of its chance included: `kcut catalog` publishes these texts (D8: one source of
truth), and `sfx_schema` and `sfx_events` read the ranges and the defaults from here.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from kcut.audio import sfx_synth as synth
from kcut.params import ParamSpec

SynthFn = Callable[..., NDArray[np.float32]]


@dataclass(frozen=True)
class SfxDef:
    """One sound effect. `fn(n, sr, **params)` makes `n` samples. `fixed_n` is its length in
    samples at 48 kHz if it has one; `default_dur_ms` its duration when `dur_f` is not given (`None`
    if it has none); `requires_dur` says that `dur_f` is obligatory. `params` are the parameters it
    takes besides `gain`, `dur_f` and `align`, with their ranges and defaults. `cost` is `bajo` or
    `medio`: how much the synthesis weighs (it grows with the duration in the `medio` ones)."""

    id: str
    fn: SynthFn
    fixed_n: int | None
    default_dur_ms: int | None
    requires_dur: bool
    params: tuple[ParamSpec, ...]
    default_gain: float
    name_es: str
    purpose_es: str
    avoid_es: str
    cost: str


def _seed(default: int, what: str) -> ParamSpec:
    help_es = f"semilla del azar de {what} (0 o más; por defecto {default})"
    return ParamSpec("seed", "int", default=default, lo=0, help_es=help_es)


_FREQ = ParamSpec(
    "freq",
    "float",
    default=820.0,
    lo=100.0,
    hi=4000.0,
    help_es="frecuencia final del pop en Hz (de 100 a 4000; por defecto 820)",
)
_RATE = ParamSpec(
    "rate",
    "float",
    default=13.0,
    lo=4.0,
    hi=25.0,
    help_es="teclas por segundo (de 4 a 25; por defecto 13)",
)

_DEFS: tuple[SfxDef, ...] = (
    SfxDef(
        "whoosh",
        synth.whoosh,
        None,
        450,
        False,
        (_seed(1, "la ráfaga"),),
        0.45,
        "Whoosh",
        "cambio de plano, entrada de gráfico",
        "No lo pongas sobre una palabra clave de la voz: tapa las frecuencias de la dicción",
        "bajo",
    ),
    SfxDef(
        "boom",
        synth.boom,
        43200,
        None,
        False,
        (_seed(7, "el clic del golpe"),),
        0.75,
        "Boom",
        "golpe de gancho o cierre",
        "No lo repitas en un mismo video más de dos veces: pierde fuerza",
        "bajo",
    ),
    SfxDef(
        "pop",
        synth.pop,
        5760,
        None,
        False,
        (_FREQ,),
        0.6,
        "Pop",
        "aparición de texto",
        "No lo uses con cada palabra: cansa; reserva uno por gráfico",
        "bajo",
    ),
    SfxDef(
        "shimmer",
        synth.shimmer,
        None,
        1100,
        False,
        (),
        0.6,
        "Brillo",
        "brillo, revelación",
        "No lo mezcles con una música aguda: se pierde",
        "bajo",
    ),
    SfxDef(
        "key",
        synth.key,
        2400,
        None,
        False,
        (_seed(0, "la tecla"),),
        0.6,
        "Tecla",
        "tecla suelta",
        "Para teclear de corrido usa typing, no muchas teclas sueltas",
        "bajo",
    ),
    SfxDef(
        "click",
        synth.click,
        2880,
        None,
        False,
        (),
        0.7,
        "Clic",
        "clic de interfaz",
        "No lo uses sin que se vea un botón o un cursor que lo explique",
        "bajo",
    ),
    SfxDef(
        "kick",
        synth.kick,
        15360,
        None,
        False,
        (),
        0.9,
        "Bombo",
        "bombo para beat",
        "Sin hat ni más golpes no hace ritmo; no lo dejes solo bajo una voz grave",
        "bajo",
    ),
    SfxDef(
        "hat",
        synth.hat,
        2160,
        None,
        False,
        (_seed(0, "el soplido"),),
        0.95,
        "Hi-hat",
        "hi-hat",
        "Sin bombo no hace ritmo; a ganancia alta pica en los oídos",
        "bajo",
    ),
    SfxDef(
        "pad",
        synth.pad,
        None,
        None,
        True,
        (),
        0.55,
        "Colchón",
        "colchón armónico corto",
        "No lo pongas bajo una música con acordes: choca; dura lo que dura la escena",
        "medio",
    ),
    SfxDef(
        "typing",
        synth.typing,
        None,
        None,
        True,
        (_RATE, _seed(55, "el ritmo del tecleo")),
        0.85,
        "Tecleo",
        "tecleo",
        "Ponlo solo mientras se ve texto que se escribe: sin eso confunde",
        "medio",
    ),
    SfxDef(
        "riser",
        synth.riser,
        None,
        None,
        True,
        (_seed(77, "el ruido de la subida"),),
        0.45,
        "Subida",
        "subida antes de un golpe",
        "Hazlo terminar justo en el golpe (align end); si termina antes queda un silencio raro",
        "medio",
    ),
    SfxDef(
        "blip8",
        synth.blip8,
        10560,
        None,
        False,
        (),
        0.7,
        "Arpegio 8-bit",
        "arpegio 8-bit",
        "Solo va en videos de estilo retro o de juegos: en otro tono desentona",
        "bajo",
    ),
    SfxDef(
        "powerup",
        synth.powerup,
        26400,
        None,
        False,
        (),
        0.7,
        "Aparición mágica",
        "aparición mágica",
        "No lo uses para algo serio o triste: suena a premio de juego",
        "bajo",
    ),
)

SFX: Mapping[str, SfxDef] = {d.id: d for d in _DEFS}
