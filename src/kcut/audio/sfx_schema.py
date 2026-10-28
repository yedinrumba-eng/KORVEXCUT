"""The schema of `edit/sfx.json` (spec S1.8a, 001.15). Only the shape and the parameters of each
event: where an anchor points and whether the times fall inside the video are the checks of
`sfx_events.resolve_events`.

Every problem is an `Issue`: A01 for a mistake in the shape of the file (the schema, a type, a key
that is not known, one that is missing, `bus_gain_db` or a window's `gain_db` out of -24...+12, an
`at` that is neither a whole number nor an anchor), A02 for a `type` that does not exist and A03
for the parameters of an event (`gain`, `seed`, `freq`, `rate`, `dur_f`, `align`), which are
checked with the `ParamSpec` of `params.py` and of each type in `sfx_library.py`. A message never
repeats text of the file (it is Claude's, and Claude reads what is printed) and never names a key
that kcut does not know.
"""

from dataclasses import dataclass

from kcut.anchors import has_time_shape
from kcut.audio.sfx_library import SFX, SfxDef
from kcut.issues import Issue
from kcut.params import ParamSpec, check_params
from kcut.schema_util import UNKNOWN_KEY, join_path

SCHEMA = "kcut.sfx/1"
GAIN_DB_RANGE = (-24.0, 12.0)  # `bus_gain_db` and the `gain_db` of each window
ALIGNS = ("start", "center", "end")
_TOP = frozenset({"schema", "bus_gain_db", "events", "windows"})
_EVENT = frozenset({"type", "at", "dur_f", "align", "gain", "seed", "freq", "rate"})
_WINDOW = frozenset({"start", "end", "gain_db"})
_TIME_HELP = "un frame entero, o un ancla {word, edge} o {src, f}"
_GAIN = ParamSpec("gain", "float", lo=0.0, hi=2.0, help_es="ganancia lineal, de 0 a 2")
_DUR = ParamSpec("dur_f", "int", lo=1, help_es="duración en frames")
_ALIGN = ParamSpec("align", "str", help_es="start, center o end")
_MISSING = object()  # a key of the top level that the file does not have


@dataclass(frozen=True)
class SfxEventDoc:
    """An event as written. `at` is a frame or an anchor, unresolved. `align`, `dur_f`, `gain`,
    `seed`, `freq` and `rate` are `None` when the file does not give them (`resolve_events`
    puts in what each type has by default)."""

    index: int
    type: str
    at: object
    align: str | None
    dur_f: int | None
    gain: float | None
    seed: int | None
    freq: float | None
    rate: float | None


@dataclass(frozen=True)
class SfxWindowDoc:
    """A window of gain as written: frames of the output and the gain in dB (`resolve_events`
    checks that it fits in the video)."""

    index: int
    start: int
    end: int
    gain_db: float


@dataclass(frozen=True)
class SfxDoc:
    """`sfx.json` read: the gain of the bus, the events in the order they are written and the
    windows of gain."""

    bus_gain_db: float
    events: tuple[SfxEventDoc, ...]
    windows: tuple[SfxWindowDoc, ...]


def parse_sfx(data: object) -> tuple[SfxDoc | None, list[Issue]]:
    """`data` (what `read_json` gave) as an `SfxDoc`, or `None` and the A01 / A02 / A03 issues if
    the file does not have the schema. `bus_gain_db` (0) and `windows` (none) may be left out;
    `schema` and `events` may not."""
    issues: list[Issue] = []
    if not isinstance(data, dict):
        return None, [_a01("", "el documento debe ser un objeto")]
    _unknown(data, _TOP, "", issues)
    if data.get("schema") != SCHEMA:
        issues.append(_a01("schema", f"debe ser {SCHEMA}"))
    bus = _db(data["bus_gain_db"], "bus_gain_db", issues) if "bus_gain_db" in data else 0.0
    events = _events(data.get("events", _MISSING), issues)
    windows = _windows(data.get("windows", []), issues)
    if issues:
        return None, issues
    return SfxDoc(bus, events, windows), issues


def _a01(path: str, message: str) -> Issue:
    return Issue("A01", "error", path, message)


def _unknown(d: dict[str, object], allowed: frozenset[str], path: str, issues: list[Issue]) -> None:
    for key in d:
        if key not in allowed:
            issues.append(_a01(join_path(path, UNKNOWN_KEY), "clave desconocida"))


def _db(value: object, path: str, issues: list[Issue]) -> float:
    """A gain in dB between -24 and +12 (0.0 and an A01 if it is not one)."""
    lo, hi = GAIN_DB_RANGE
    if isinstance(value, int | float) and not isinstance(value, bool) and lo <= value <= hi:
        return float(value)
    issues.append(_a01(path, f"debe ser un número entre {lo:g} y +{hi:g} dB"))
    return 0.0


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _events(raw: object, issues: list[Issue]) -> tuple[SfxEventDoc, ...]:
    if raw is _MISSING:
        issues.append(_a01("events", "falta (es obligatorio)"))
        return ()
    if not isinstance(raw, list):
        issues.append(_a01("events", "debe ser una lista"))
        return ()
    found: list[SfxEventDoc] = []
    for i, item in enumerate(raw):
        event = _event(item, i, issues)
        if event is not None:
            found.append(event)
    return tuple(found)


def _event(item: object, i: int, issues: list[Issue]) -> SfxEventDoc | None:
    where = f"events[{i}]"
    if not isinstance(item, dict):
        issues.append(_a01(where, "debe ser un objeto"))
        return None
    before = len(issues)
    _unknown(item, _EVENT, where, issues)
    sfx = _type(item, where, issues)
    if "at" not in item:
        issues.append(_a01(join_path(where, "at"), "falta (es obligatorio)"))
    elif not has_time_shape(item["at"]):
        issues.append(_a01(join_path(where, "at"), f"debe ser {_TIME_HELP}"))
    checked = _params(item, sfx, where, issues) if sfx is not None else {}
    if len(issues) > before or sfx is None:
        return None
    given = {name: checked.get(name) for name in item if name in checked}
    return SfxEventDoc(
        i,
        sfx.id,
        item["at"],
        _text(given.get("align")),
        _int(given.get("dur_f")),
        _float(given.get("gain")),
        _int(given.get("seed")),
        _float(given.get("freq")),
        _float(given.get("rate")),
    )


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: object) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _type(item: dict[str, object], where: str, issues: list[Issue]) -> SfxDef | None:
    path = join_path(where, "type")
    if "type" not in item:
        issues.append(_a01(path, "falta (es obligatorio)"))
        return None
    value = item["type"]
    if not isinstance(value, str):
        issues.append(_a01(path, "debe ser texto"))
        return None
    if value not in SFX:
        known = ", ".join(SFX)
        message = f"tipo de efecto desconocido; los que hay: {known}"
        issues.append(Issue("A02", "error", path, message))
        return None
    return SFX[value]


def _params(
    item: dict[str, object], sfx: SfxDef, where: str, issues: list[Issue]
) -> dict[str, object]:
    """The parameters of the event against what its type takes: `gain`, `dur_f` and `align` of
    every type and the `params` of this one, all A03. A parameter that another type has (a `seed`
    in a `pop`) is an A03 that names it: it is one of the words that kcut knows. What
    `check_params` gives back has the defaults of the type too: the event keeps only what
    it wrote."""
    named = {k: v for k, v in item.items() if k in _EVENT and k not in ("type", "at")}
    taken = {"gain", "dur_f", "align", *(p.name for p in sfx.params)}
    for key in named:
        if key not in taken:
            message = "este tipo de efecto no lleva ese parámetro"
            issues.append(Issue("A03", "error", join_path(where, key), message))
    specs = [_GAIN, _DUR, _ALIGN, *sfx.params]
    wanted = {k: v for k, v in named.items() if k in taken}
    checked, found = check_params(specs, wanted, where, "A03", None)
    issues.extend(found)
    align = checked.get("align")
    if isinstance(align, str) and align not in ALIGNS:
        message = f"debe ser uno de: {', '.join(ALIGNS)}"
        issues.append(Issue("A03", "error", join_path(where, "align"), message))
    if "dur_f" in named and sfx.fixed_n is not None:
        message = "este efecto dura siempre lo mismo: no lleva dur_f"
        issues.append(Issue("A03", "error", join_path(where, "dur_f"), message))
    elif "dur_f" not in named and sfx.requires_dur:
        message = "falta dur_f (es obligatorio en este efecto)"
        issues.append(Issue("A03", "error", join_path(where, "dur_f"), message))
    return checked


def _windows(raw: object, issues: list[Issue]) -> tuple[SfxWindowDoc, ...]:
    if not isinstance(raw, list):
        issues.append(_a01("windows", "debe ser una lista"))
        return ()
    found: list[SfxWindowDoc] = []
    for i, item in enumerate(raw):
        window = _window(item, i, issues)
        if window is not None:
            found.append(window)
    return tuple(found)


def _window(item: object, i: int, issues: list[Issue]) -> SfxWindowDoc | None:
    where = f"windows[{i}]"
    if not isinstance(item, dict):
        issues.append(_a01(where, "debe ser un objeto con start, end y gain_db"))
        return None
    before = len(issues)
    _unknown(item, _WINDOW, where, issues)
    start = _bound(item, "start", where, issues)
    end = _bound(item, "end", where, issues)
    if "gain_db" not in item:
        issues.append(_a01(join_path(where, "gain_db"), "falta (es obligatorio)"))
        gain = 0.0
    else:
        gain = _db(item["gain_db"], join_path(where, "gain_db"), issues)
    return None if len(issues) > before else SfxWindowDoc(i, start, end, gain)


def _bound(item: dict[str, object], key: str, where: str, issues: list[Issue]) -> int:
    """A whole frame of a window (0 and an A01 if it is not one)."""
    value = item.get(key, _MISSING)
    if value is _MISSING:
        issues.append(_a01(join_path(where, key), "falta (es obligatorio)"))
    elif isinstance(value, int) and not isinstance(value, bool):
        return value
    else:
        issues.append(_a01(join_path(where, key), "debe ser un frame entero"))
    return 0
