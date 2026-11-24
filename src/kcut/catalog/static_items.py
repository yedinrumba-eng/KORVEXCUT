"""The catalog items that no registry holds: music, camera, transition and workflow (spec S1.9a).

Each camera and transition names the field of `edl/model.py` that makes it (`edl_field`), and a
test checks that it exists. The ranges are the ones the checks of the engine enforce: those of
`edl/fields.py` (E13) for the camera and those of `audio/music_schema.py` for the music. Graphics,
looks and sound effects are not here: they come from their own registries.
"""

from kcut.audio.music_model import DEFAULT_GAIN_DB
from kcut.audio.music_schema import BPM_RANGE, DEFAULT_BPM, GAIN_DB_RANGE, MAX_CHORDS
from kcut.catalog.model import CatalogItem, Cost, params_of
from kcut.params import ParamSpec

_MUSIC_GAIN = ParamSpec(
    "gain_db",
    "float",
    default=DEFAULT_GAIN_DB,
    lo=GAIN_DB_RANGE[0],
    hi=GAIN_DB_RANGE[1],
    help_es="volumen de toda la música en dB",
)
_MUSIC: tuple[CatalogItem, ...] = (
    CatalogItem(
        category="music",
        id="synth",
        name_es="Música sintetizada",
        purpose_es="Una base de acordes y batería que kcut genera sola, sin archivos ni derechos",
        avoid_es="No la uses si quieres una canción real, con voz o con un sonido de estudio",
        status="available",
        since="S1.8",
        cost="bajo",
        cost_note_es="se sintetiza en unos segundos",
        params=params_of(
            (
                _MUSIC_GAIN,
                ParamSpec(
                    "synth.bpm",
                    "float",
                    default=DEFAULT_BPM,
                    lo=BPM_RANGE[0],
                    hi=BPM_RANGE[1],
                    help_es="pulsos por minuto",
                ),
                ParamSpec(
                    "synth.progression",
                    "list",
                    True,
                    lo=1,
                    hi=MAX_CHORDS,
                    help_es="un acorde por compás, en bucle (Am, F, C, G...)",
                ),
                ParamSpec("synth.drums", "bool", default=True, help_es="con batería"),
            )
        ),
    ),
    CatalogItem(
        category="music",
        id="file",
        name_es="Canción de un archivo",
        purpose_es="Una canción de recursos/ aprobada en el manifiesto, con fundidos y bucle",
        avoid_es="No uses una canción que no esté aprobada en recursos.json: kcut se niega",
        status="available",
        since="S1.8",
        cost="bajo",
        cost_note_es="solo decodifica lo que el video necesita",
        params=params_of(
            (
                _MUSIC_GAIN,
                ParamSpec("file.path", "path", True, help_es="archivo dentro de recursos/"),
                ParamSpec(
                    "file.src_in_f", "int", default=0, help_es="frame del archivo donde empieza"
                ),
                ParamSpec("file.loop", "bool", default=False, help_es="repetirla si es más corta"),
                ParamSpec("file.fade_out_f", "int", default=36, help_es="frames de fundido final"),
            )
        ),
    ),
    CatalogItem(
        category="music",
        id="none",
        name_es="Sin música",
        purpose_es="Solo la voz y los efectos de sonido",
        avoid_es="Nada: es lo que pasa cuando no existe edit/music.json",
        status="available",
        since="S1.8",
        cost="bajo",
    ),
)


def _camera(
    id_: str,
    name: str,
    purpose: str,
    avoid: str,
    edl_field: str,
    params: tuple[ParamSpec, ...],
    cost: Cost = "bajo",
    note: str = "",
) -> CatalogItem:
    return CatalogItem(
        category="camera",
        id=id_,
        name_es=name,
        purpose_es=purpose,
        avoid_es=avoid,
        status="available",
        since="S1.5",
        cost=cost,
        cost_note_es=note,
        params=params_of(params),
        edl_field=edl_field,
    )


_CAMERA: tuple[CatalogItem, ...] = (
    _camera(
        "zoom",
        "Zoom fijo",
        "Acerca la cámara en un tramo (de 1.0 a 3.0) para dar énfasis o esconder un corte",
        "No lo uses en cada corte: pierde el efecto",
        "zoom",
        (
            ParamSpec(
                "zoom", "float", default=1.0, lo=1.0, hi=3.0, help_es="factor de acercamiento"
            ),
        ),
        "medio",
        "un zoom alto pide un mezzanine de más píxeles",
    ),
    _camera(
        "push",
        "Empuje lento",
        "Acerca la cámara poco a poco durante el tramo (de 0 a 0.5)",
        "No lo mezcles con un zoom alto en el mismo tramo",
        "push",
        (ParamSpec("push", "float", default=0.0, lo=0.0, hi=0.5, help_es="cuánto se acerca"),),
    ),
    _camera(
        "reframe",
        "Reencuadre",
        "Mueve el centro del encuadre (cx, cy) o lo ancla arriba, al centro o abajo",
        "No lo uses para seguir a alguien que se mueve: el encuadre es fijo en el tramo",
        "cx",
        (
            ParamSpec("cx", "float", default=0.5, lo=0.0, hi=1.0, help_es="centro horizontal"),
            ParamSpec("cy", "float", default=0.5, lo=0.0, hi=1.0, help_es="centro vertical"),
            ParamSpec(
                "anchor",
                "str",
                default="center",
                help_es="top, center o bottom: dónde ancla el zoom",
            ),
        ),
    ),
    _camera(
        "screen_card",
        "Tarjeta de pantalla",
        "Muestra una grabación de pantalla en una tarjeta, con recortes y velocidad variable",
        "No pongas texto muy chico en la grabación: la tarjeta mide unos 1000 px de ancho",
        "keys",
        (
            ParamSpec(
                "keys", "list", True, lo=1, help_es="recorte y tamaño de la tarjeta por frame"
            ),
            ParamSpec(
                "card_y", "float", default=0.47, lo=0.0, hi=1.0, help_es="altura de la tarjeta"
            ),
        ),
        "medio",
        "compone el recorte de la pantalla en cada frame",
    ),
    _camera(
        "broll_push",
        "Inserto de apoyo con empuje",
        "Cubre la imagen con otra toma (b-roll) que se acerca despacio",
        "No cubras la cara de quien habla por más de unos segundos",
        "dim",
        (
            ParamSpec("src_f", "int", True, help_es="frame de la toma donde empieza"),
            ParamSpec("push", "float", default=0.07, lo=0.0, hi=0.5, help_es="cuánto se acerca"),
            ParamSpec("dim", "float", default=1.0, lo=0.0, hi=1.5, help_es="oscurece o aclara"),
        ),
    ),
    _camera(
        "color_card",
        "Tarjeta de color",
        "Un fondo de color liso para un gancho o un cierre",
        "No la dejes mucho tiempo: una imagen quieta parece un error",
        "color",
        (ParamSpec("color", "color", True, help_es="color #RRGGBB del fondo"),),
    ),
)

_TRANSITION: tuple[CatalogItem, ...] = (
    CatalogItem(
        category="transition",
        id="cut",
        name_es="Corte directo",
        purpose_es="Pasa de un tramo al siguiente sin ningún efecto",
        avoid_es="Nada: es lo normal, y por eso no tiene campo en el EDL",
        status="available",
        since="S1.5",
        cost="bajo",
    ),
    CatalogItem(
        category="transition",
        id="fade_black",
        name_es="Fundido a negro",
        purpose_es="El tramo entra desde negro o sale hacia negro, en los frames que se pidan",
        avoid_es="No lo uses en cada corte: sirve para abrir y para cerrar",
        status="available",
        since="S1.5",
        cost="bajo",
        params=params_of(
            (
                ParamSpec("fade_in_f", "int", default=0, lo=0, help_es="frames de entrada"),
                ParamSpec("fade_out_f", "int", default=0, lo=0, help_es="frames de salida"),
            )
        ),
        edl_field="fade_out_f",
    ),
)

_WORKFLOW: tuple[CatalogItem, ...] = (
    CatalogItem(
        category="workflow",
        id="qa",
        name_es="Auditoría del video",
        purpose_es="Mide el video terminado y compara lo que se oye con las palabras del EDL",
        avoid_es="No lo corras sobre el crudo: solo audita salida/vN.mp4",
        status="available",
        since="S1.9",
        cost="medio",
        cost_note_es="decodifica el video varias veces y transcribe su audio con Whisper en la CPU",
    ),
)

STATIC: tuple[CatalogItem, ...] = (*_MUSIC, *_CAMERA, *_TRANSITION, *_WORKFLOW)
