"""The schema of `edit/graphics.json` (spec S1.6a). Only the shape: what the parameters of a cue
mean, where an anchor points and whether it falls inside the video are other checks (`components`
and `resolve`).

Every problem is an `Issue`: G01 for a mistake in the shape of the file and G02 for a component
that does not exist. A message never repeats text of the file (it is Claude's, and Claude reads
what `graphics check` prints) and never names a key it does not know.
"""

import re
from dataclasses import dataclass

from kcut.anchors import has_time_shape
from kcut.gfx.components import CAPTIONS, COMPONENTS
from kcut.issues import Issue
from kcut.schema_util import UNKNOWN_KEY, join_path

SCHEMA = "kcut.graphics/1"
MAX_CUES = 500  # more are not looked at: each one is a `div` in Chromium (001.28, point 3)
_ID = re.compile(r"[a-z0-9-]{1,32}")
_TOP = frozenset({"schema", "captions", "cues"})
_CAPTIONS = frozenset({"enabled", "hide"})
_WINDOW = frozenset({"start", "end"})
_CUE = frozenset({"id", "component", "start", "end", "params", "hide_captions"})
_TIME_HELP = "un frame entero, o un ancla {word, edge} o {src, f}"


@dataclass(frozen=True)
class WindowDoc:
    """A `captions.hide` window as written: `start` and `end` are frames or anchors, unresolved."""

    index: int
    start: object
    end: object


@dataclass(frozen=True)
class CueDoc:
    """A cue as written: `start` and `end` are frames or anchors, `params` is not checked yet."""

    index: int
    id: str
    component: str
    start: object
    end: object
    params: object
    hide_captions: bool | None


@dataclass(frozen=True)
class GraphicsDoc:
    """`graphics.json` read. `captions_enabled` is `None` when the file does not say, and then
    `kcut.toml [captions] enabled` rules."""

    captions_enabled: bool | None
    hide: tuple[WindowDoc, ...]
    cues: tuple[CueDoc, ...]


def default_doc() -> GraphicsDoc:
    """The document that stands for a missing `edit/graphics.json` (001.15, point 40): no cues,
    no hidden windows, and `captions.enabled` left to `kcut.toml`."""
    return GraphicsDoc(None, (), ())


def parse_graphics(data: object) -> tuple[GraphicsDoc | None, list[Issue]]:
    """`data` (what `read_json` gave) as a `GraphicsDoc`, or `None` and the G01 / G02 issues if
    the file does not have the schema."""
    issues: list[Issue] = []
    if not isinstance(data, dict):
        return None, [_g01("", "el documento debe ser un objeto")]
    _unknown(data, _TOP, "", issues)
    if data.get("schema") != SCHEMA:
        issues.append(_g01("schema", f"debe ser {SCHEMA}"))
    enabled, hide = _captions(data.get("captions"), issues)
    cues = _cues(data.get("cues"), issues)
    if issues:
        return None, issues
    return GraphicsDoc(enabled, hide, cues), issues


def _g01(path: str, message: str) -> Issue:
    return Issue("G01", "error", path, message)


def _unknown(d: dict[str, object], allowed: frozenset[str], path: str, issues: list[Issue]) -> None:
    for key in d:
        if key not in allowed:
            issues.append(_g01(join_path(path, UNKNOWN_KEY), "clave desconocida"))


def _time(d: dict[str, object], key: str, path: str, issues: list[Issue]) -> object:
    where = join_path(path, key)
    if key not in d:
        issues.append(_g01(where, "falta (es obligatorio)"))
    elif not has_time_shape(d[key]):
        issues.append(_g01(where, f"debe ser {_TIME_HELP}"))
    return d.get(key)


def _captions(raw: object, issues: list[Issue]) -> tuple[bool | None, tuple[WindowDoc, ...]]:
    if raw is None:
        return None, ()
    if not isinstance(raw, dict):
        issues.append(_g01("captions", "debe ser un objeto"))
        return None, ()
    _unknown(raw, _CAPTIONS, "captions", issues)
    enabled = raw.get("enabled")
    if "enabled" in raw and not isinstance(enabled, bool):
        issues.append(_g01("captions.enabled", "debe ser verdadero o falso"))
        enabled = None
    windows: list[WindowDoc] = []
    listed = raw.get("hide", [])
    if not isinstance(listed, list):
        issues.append(_g01("captions.hide", "debe ser una lista"))
        return enabled, ()
    for i, item in enumerate(listed):
        where = f"captions.hide[{i}]"
        if not isinstance(item, dict):
            issues.append(_g01(where, "debe ser un objeto con start y end"))
            continue
        _unknown(item, _WINDOW, where, issues)
        windows.append(
            WindowDoc(i, _time(item, "start", where, issues), _time(item, "end", where, issues))
        )
    return enabled, tuple(windows)


def _cues(raw: object, issues: list[Issue]) -> tuple[CueDoc, ...]:
    if raw is None:
        issues.append(_g01("cues", "falta (es obligatorio)"))
        return ()
    if not isinstance(raw, list):
        issues.append(_g01("cues", "debe ser una lista"))
        return ()
    if len(raw) > MAX_CUES:  # one issue, and no cue is looked at (it could be 700 000 of them)
        issues.append(_g01("cues", f"hay más de {MAX_CUES} cues; kcut no los revisa"))
        return ()
    cues: list[CueDoc] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        cue = _cue(item, i, seen, issues)
        if cue is not None:
            cues.append(cue)
    return tuple(cues)


def _cue(item: object, i: int, seen: set[str], issues: list[Issue]) -> CueDoc | None:
    where = f"cues[{i}]"
    if not isinstance(item, dict):
        issues.append(_g01(where, "debe ser un objeto"))
        return None
    before = len(issues)
    _unknown(item, _CUE, where, issues)
    cue_id = _cue_id(item.get("id"), where, seen, issues)
    component = _component(item.get("component"), where, issues)
    start = _time(item, "start", where, issues)
    end = _time(item, "end", where, issues)
    params = item.get("params", {})
    if not isinstance(params, dict):
        issues.append(_g01(f"{where}.params", "debe ser un objeto"))
    hidden = item.get("hide_captions")
    if "hide_captions" in item and not isinstance(hidden, bool):
        issues.append(_g01(f"{where}.hide_captions", "debe ser verdadero o falso"))
        hidden = None
    if len(issues) > before or cue_id is None or component is None:
        return None
    return CueDoc(i, cue_id, component, start, end, params, hidden)


def _cue_id(value: object, where: str, seen: set[str], issues: list[Issue]) -> str | None:
    path = f"{where}.id"
    if value is None:
        issues.append(_g01(path, "falta (es obligatorio)"))
        return None
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        issues.append(_g01(path, "debe ser texto de 1 a 32 caracteres: a-z, 0-9 y -"))
        return None
    if value in seen:
        issues.append(_g01(path, "el id está repetido: cada cue lleva el suyo"))
        return None
    seen.add(value)
    return value


def _component(value: object, where: str, issues: list[Issue]) -> str | None:
    path = f"{where}.component"
    if value is None:
        issues.append(_g01(path, "falta (es obligatorio)"))
        return None
    if isinstance(value, str) and value in COMPONENTS:
        return value
    if value == CAPTIONS.id:
        message = "captions es interno: no se escribe como cue, se enciende con captions.enabled"
        issues.append(Issue("G02", "error", path, message))
        return None
    known = ", ".join(sorted(COMPONENTS))
    issues.append(Issue("G02", "error", path, f"componente desconocido; los que hay: {known}"))
    return None
