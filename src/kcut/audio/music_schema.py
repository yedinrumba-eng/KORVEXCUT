"""The schema of `edit/music.json` (spec S1.8b, 001.15): `parse_music` reads what `read_json` gave
and says, as `Issue`s, what is wrong with it.

- M01 the shape of the file: `schema`, a type, a key that is not known, one that is missing, an
  unknown `mode`, `gain_db` out of -40...+6, a range of `duck`, `mode: synth` with no `synth`,
  `mode: file` with no `file`, more windows than `MAX_WINDOWS`;
- M02 the `synth`: `bpm` out of 60...180, an empty `progression` or one of more than 16 chords, a
  chord that is not a root of the list and an optional `m`;
- M03 the `file`: a `path` that does not pass `resolve_in_project`, does not begin with
  `recursos/`, does not exist or has an extension that is not audio; a negative `src_in_f`,
  `fade_in_f` or `fade_out_f`;
- M04 the same `path`, if it is not in the manifest or has no `approved_by` (DS9): exit 5;
- M05 a window of `windows` or of `mute_drums` that is not `0 <= start < end <= frames`, and a
  `stop_drums_f` or an `origin_f` outside `[0, frames]`.

A message never repeats text of the file (it is Claude's, and Claude reads what is printed): not the
path of the song, which can be a person's, either. M06 is not here: `mix` is who decodes the file.
"""

from typing import Any, TypeGuard

from kcut.audio.chords import is_chord
from kcut.audio.music_model import (
    DEFAULT_DUCK,
    DEFAULT_GAIN_DB,
    DuckCfg,
    Mode,
    MusicDoc,
    SynthCfg,
    Window,
)
from kcut.audio.music_schema_file import file_problems, parse_file_section
from kcut.audio.sfx_schema import GAIN_DB_RANGE as WINDOW_DB_RANGE
from kcut.audio.sfx_schema import MAX_WINDOWS
from kcut.errors import InternalError
from kcut.issues import Issue
from kcut.params import ParamSpec, _shown, check_params
from kcut.project import Project
from kcut.schema_util import UNKNOWN_KEY, describe_value, join_path

SCHEMA = "kcut.music/1"
MODE_OF: dict[str, Mode] = {"synth": "synth", "file": "file", "none": "none"}
GAIN_DB_RANGE = (-40.0, 6.0)  # `gain_db` of the music
BPM_RANGE = (60.0, 180.0)
DEFAULT_BPM = 120.0
MAX_CHORDS = 16
_TOP = frozenset({"schema", "mode", "gain_db", "synth", "file", "duck", "windows"})
_SYNTH = frozenset({"bpm", "progression", "drums", "mute_drums", "stop_drums_f", "origin_f"})
_MISSING = object()
_DUCK_SPECS = (
    ParamSpec("enabled", "bool", default=DEFAULT_DUCK.enabled),
    ParamSpec("threshold", "float", default=DEFAULT_DUCK.threshold, lo=0.001, hi=1.0),
    ParamSpec("ratio", "float", default=DEFAULT_DUCK.ratio, lo=1.0, hi=20.0),
    ParamSpec("attack_ms", "float", default=DEFAULT_DUCK.attack_ms, lo=1.0, hi=200.0),
    ParamSpec("release_ms", "float", default=DEFAULT_DUCK.release_ms, lo=10.0, hi=2000.0),
    ParamSpec("makeup", "float", default=DEFAULT_DUCK.makeup, lo=1.0, hi=4.0),
    ParamSpec("knee", "float", default=DEFAULT_DUCK.knee, lo=1.0, hi=8.0),
)


def parse_music(data: object, project: Project, frames: int) -> tuple[MusicDoc | None, list[Issue]]:
    """`data` as a `MusicDoc`, or `None` and the M01-M05 issues if it has errors. `frames` is the
    length of the EDL (M05) and `project` is where `file.path` is looked up and its approval asked
    (M03, M04). Only `schema` and `mode` are needed; `synth.progression` is needed in `synth` and
    `file.path` in `file`; every other key has the value of the example of the spec."""
    issues: list[Issue] = []
    if not isinstance(data, dict):
        return None, [_m("M01", "", "el documento debe ser un objeto")]
    _unknown(data, _TOP, "", issues)
    if data.get("schema") != SCHEMA:
        issues.append(_m("M01", "schema", f"debe ser {SCHEMA}"))
    mode = _mode(data.get("mode", _MISSING), issues)
    gain = DEFAULT_GAIN_DB
    if "gain_db" in data:
        given = _number(data["gain_db"], "gain_db", GAIN_DB_RANGE, issues, "M01")
        gain = gain if given is None else given
    synth = _synth(data.get("synth"), frames, issues)
    file = parse_file_section(data.get("file"), issues)
    if mode == "synth" and data.get("synth") is None:
        issues.append(_m("M01", "synth", "falta (el modo synth lo necesita)"))
    if mode == "file":
        if data.get("file") is None:
            issues.append(_m("M01", "file", "falta (el modo file lo necesita)"))
        elif file is not None:
            issues += file_problems(file, project)
    duck = _duck(data.get("duck", _MISSING), issues)
    windows = _windows(data.get("windows", []), "windows", frames, issues)
    if issues or mode is None:
        return None, issues
    return MusicDoc(mode, gain, synth, file, duck, tuple(Window(*w) for w in windows)), issues


def _m(code: str, path: str, message: str) -> Issue:
    return Issue(code, "error", path, message)


def _unknown(d: dict[str, Any], allowed: frozenset[str], path: str, issues: list[Issue]) -> None:
    for key in d:
        if key not in allowed:
            issues.append(_m("M01", join_path(path, UNKNOWN_KEY), "clave desconocida"))


def _whole(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _float(value: object) -> float:
    """A number that `check_params` already checked (anything else is a bug, not a mistake)."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    raise InternalError("music_schema: se esperaba un número ya revisado")


def _number(
    value: object, path: str, span: tuple[float, float], issues: list[Issue], code: str
) -> float | None:
    """`value` as a number between the two limits, or `None` and an issue: M01 when it is not a
    number, `code` when it is out of range."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        # 001.37, point 6: a text is only its length, as in `sfx_schema` (`describe_value` cut the
        # repr to 40 characters and so repeated up to 37 of the file)
        issues.append(_m("M01", path, f"debe ser un número (vino {_shown(value)})"))
        return None
    low, high = span
    if not low <= value <= high:
        text = f"debe estar entre {low:g} y {high:g} (vino {describe_value(value)})"
        issues.append(_m(code, path, text))
        return None
    return float(value)


def _mode(value: object, issues: list[Issue]) -> Mode | None:
    if value is _MISSING:
        issues.append(_m("M01", "mode", "falta (es obligatorio)"))
    elif isinstance(value, str) and value in MODE_OF:
        return MODE_OF[value]
    else:
        issues.append(_m("M01", "mode", f"debe ser uno de: {', '.join(MODE_OF)}"))
    return None


def _synth(raw: object, frames: int, issues: list[Issue]) -> SynthCfg | None:
    """The `synth` section (`None` if there is none, or if it has errors)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        issues.append(_m("M01", "synth", "debe ser un objeto o null"))
        return None
    before = len(issues)
    _unknown(raw, _SYNTH, "synth", issues)
    bpm = DEFAULT_BPM
    if "bpm" in raw:
        given = _number(raw["bpm"], "synth.bpm", BPM_RANGE, issues, "M02")
        bpm = bpm if given is None else given
    progression = _progression(raw.get("progression", _MISSING), issues)
    drums = raw.get("drums", True)
    if not isinstance(drums, bool):
        issues.append(_m("M01", "synth.drums", "debe ser verdadero o falso"))
    muted = _windows(raw.get("mute_drums", []), "synth.mute_drums", frames, issues, gain=False)
    stop = _frame(raw.get("stop_drums_f"), "synth.stop_drums_f", frames, issues)
    origin = _frame(raw.get("origin_f", 0), "synth.origin_f", frames, issues)
    if len(issues) > before or progression is None:
        return None
    return SynthCfg(
        bpm, progression, bool(drums), tuple((s, e) for s, e, _ in muted), stop, origin or 0
    )


def _progression(raw: object, issues: list[Issue]) -> tuple[str, ...] | None:
    where = "synth.progression"
    if raw is _MISSING:
        issues.append(_m("M01", where, "falta (es obligatorio)"))
        return None
    if not isinstance(raw, list):
        issues.append(_m("M01", where, "debe ser una lista de acordes"))
        return None
    if not 1 <= len(raw) <= MAX_CHORDS:
        text = f"debe tener entre 1 y {MAX_CHORDS} acordes (tiene {len(raw)})"
        issues.append(_m("M02", where, text))
        return None
    chords: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            issues.append(_m("M01", f"{where}[{i}]", "debe ser texto"))
        elif not is_chord(item):
            text = "no es un acorde: una raíz de la lista y una m opcional"
            issues.append(_m("M02", f"{where}[{i}]", text))
        else:
            chords.append(item)
    return tuple(chords) if len(chords) == len(raw) else None


def _frame(value: object, path: str, frames: int, issues: list[Issue]) -> int | None:
    """An optional frame of `[0, frames]` (M05 outside it, M01 if it is not a whole number)."""
    if value is None:
        return None
    if not _whole(value):
        issues.append(_m("M01", path, "debe ser un frame entero"))
        return None
    if not 0 <= value <= frames:
        text = f"queda en {describe_value(value)} y el video tiene {frames} frames: [0, frames]"
        issues.append(_m("M05", path, text))
        return None
    return value


def _windows(
    raw: object, path: str, frames: int, issues: list[Issue], *, gain: bool = True
) -> list[tuple[int, int, float]]:
    """The windows `{start, end[, gain_db]}` of a list, each one inside the video (M05)."""
    if not isinstance(raw, list):
        issues.append(_m("M01", path, "debe ser una lista"))
        return []
    if len(raw) > MAX_WINDOWS:  # one issue, and no window is looked at (as in sfx.json)
        issues.append(_m("M01", path, f"hay más de {MAX_WINDOWS} ventanas; kcut no las revisa"))
        return []
    found: list[tuple[int, int, float]] = []
    for i, item in enumerate(raw):
        window = _window(item, f"{path}[{i}]", frames, issues, gain)
        if window is not None:
            found.append(window)
    return found


def _window(
    item: object, path: str, frames: int, issues: list[Issue], gain: bool
) -> tuple[int, int, float] | None:
    if not isinstance(item, dict):
        text = "debe ser un objeto con start, end" + (" y gain_db" if gain else "")
        issues.append(_m("M01", path, text))
        return None
    before = len(issues)
    allowed = frozenset({"start", "end", "gain_db"} if gain else {"start", "end"})
    _unknown(item, allowed, path, issues)
    bounds: list[int] = []
    for key in ("start", "end"):
        if key not in item:
            issues.append(_m("M01", join_path(path, key), "falta (es obligatorio)"))
        elif _whole(item[key]):
            bounds.append(item[key])
        else:
            issues.append(_m("M01", join_path(path, key), "debe ser un frame entero"))
    db = 0.0
    if gain and "gain_db" not in item:
        issues.append(_m("M01", join_path(path, "gain_db"), "falta (es obligatorio)"))
    elif gain:
        where = join_path(path, "gain_db")
        given = _number(item["gain_db"], where, WINDOW_DB_RANGE, issues, "M01")
        db = 0.0 if given is None else given
    if len(issues) > before:
        return None
    start, end = bounds
    if not 0 <= start < end <= frames:
        text = (
            f"queda en [{describe_value(start)}, {describe_value(end)}) y el video tiene "
            f"{frames} frames: tiene que cumplirse 0 <= start < end <= frames"
        )
        issues.append(_m("M05", path, text))
        return None
    return start, end, db


def _duck(raw: object, issues: list[Issue]) -> DuckCfg:
    if raw is _MISSING:
        return DEFAULT_DUCK
    checked, found = check_params(_DUCK_SPECS, raw, "duck", "M01", None)
    issues.extend(found)
    if found:
        return DEFAULT_DUCK
    return DuckCfg(
        bool(checked["enabled"]),
        _float(checked["threshold"]),
        _float(checked["ratio"]),
        _float(checked["attack_ms"]),
        _float(checked["release_ms"]),
        _float(checked["makeup"]),
        _float(checked["knee"]),
    )
