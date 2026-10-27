"""Parsing the JSON of an `edit/edl-vN.json` (spec S1.5, 001.15).

`parse_edl` never raises: every schema error becomes an `E01` issue and the EDL comes back as
`None`. Only the shape is checked here (types, keys, whole-number frames); a value out of range is
`edl.ranges`'. Finding and reading the file is `edl.files`.

Three limits keep what comes after cheap and safe (spec 001.24, points 4, 5 and 6): at most
`MAX_ITEMS` clips and `MAX_ITEMS` spans, no whole number of `10**15` or more (so no sum of them
grows past what `str()` of an integer allows), and no text of the file repeated in a message.
"""

from collections.abc import Callable
from typing import Any

from kcut.edl.model import (
    ANCHORS,
    DEFAULT_LOOK,
    SCHEMA,
    BrollSpan,
    CamSpan,
    Clip,
    ColorSpan,
    Edl,
    GapClip,
    RemapPoint,
    ScreenKey,
    ScreenSpan,
    Span,
    VoiceClip,
)
from kcut.edl.readers import (
    MAX_ITEMS,
    MAX_WHOLE,
    choice,
    color,
    e01,
    opt_whole,
    plain,
    whole,
)
from kcut.edl.shown import shown_id, shown_number
from kcut.issues import Issue
from kcut.schema_util import (
    SchemaError,
    _float,
    _int,
    join_path,
    obj,
    only_keys,
    opt_float,
    opt_str,
    req_list,
    req_str,
)

_ROOT_KEYS = {"schema", "version", "fps", "output", "frames", "look", "sources", "clips", "spans"}
_SPAN_COMMON = {"kind", "at_f", "dur_f", "look", "fade_in_f", "fade_out_f", "why"}
_SPAN_KINDS = ("cam", "broll", "screen", "color")


def parse_edl(data: object, path_label: str = "") -> tuple[Edl | None, list[Issue]]:
    """Parse the JSON document `data`. `path_label` is the path of `data` itself, the start of
    every issue's path (empty for a whole file). With any `E01` issue the EDL is `None`."""
    issues: list[Issue] = []
    edl = _document(data, path_label, issues)
    return (None, issues) if issues else (edl, [])


def _guard[T](issues: list[Issue], read: Callable[[], T], default: T) -> T:
    """`read()`, or `default` and an E01 issue if it raises a SchemaError."""
    try:
        return read()
    except SchemaError as exc:
        e01(issues, exc)
        return default


def _each[T](
    issues: list[Issue], d: dict[str, Any], key: str, label: str, parse: Callable[[object, str], T]
) -> tuple[T, ...]:
    """The items of the list `key`, each parsed on its own, so a bad one does not hide the rest."""
    items: list[Any] = _guard(issues, lambda: req_list(d, key, label), [])
    if len(items) > MAX_ITEMS:  # 001.24, point 4: it is not parsed, and the count is told
        found = f"tiene {shown_number(len(items))} elementos y el máximo es {MAX_ITEMS}"
        issues.append(Issue("E01", "error", join_path(label, key), found))
        return ()
    parsed: list[T] = []
    for index, item in enumerate(items):
        got = _item(issues, parse, item, join_path(join_path(label, key), index))
        if got is not None:
            parsed.append(got)
    return tuple(parsed)


def _item[T](
    issues: list[Issue], parse: Callable[[object, str], T], item: object, path: str
) -> T | None:
    try:
        return parse(item, path)
    except SchemaError as exc:
        e01(issues, exc)
        return None


def _document(data: object, label: str, issues: list[Issue]) -> Edl | None:
    try:
        d = obj(data, label)
    except SchemaError as exc:
        e01(issues, exc)
        return None
    _guard(issues, lambda: only_keys(d, _ROOT_KEYS, label), None)
    schema = _guard(issues, lambda: req_str(d, "schema", label), SCHEMA)
    if schema != SCHEMA:
        found = f"se esperaba {SCHEMA}"
        issues.append(Issue("E01", "error", join_path(label, "schema"), found))
    width, height = _guard(issues, lambda: _output(d, label), (0, 0))
    return Edl(
        version=_guard(issues, lambda: whole(d, "version", label), 0),
        fps=_guard(issues, lambda: whole(d, "fps", label), 0),
        out_w=width,
        out_h=height,
        frames=_guard(issues, lambda: whole(d, "frames", label), 0),
        look=_guard(issues, lambda: opt_str(d, "look", label, DEFAULT_LOOK), DEFAULT_LOOK),
        sources=_sources(d, label, issues),
        clips=_each(issues, d, "clips", label, _clip),
        spans=_each(issues, d, "spans", label, _span),
    )


def _output(d: dict[str, Any], label: str) -> tuple[int, int]:
    if "output" not in d:
        raise SchemaError(join_path(label, "output"), "falta (es obligatorio)")
    where = join_path(label, "output")
    out = obj(d["output"], where)
    only_keys(out, {"w", "h"}, where)
    return whole(out, "w", where), whole(out, "h", where)


def _sources(d: dict[str, Any], label: str, issues: list[Issue]) -> dict[str, str]:
    """`{"a1": {"qhash": "..."}}` as `{"a1": "..."}`. A bad entry is an E01 on `sources` that
    names the id."""
    where = join_path(label, "sources")
    if "sources" not in d:  # 001.24, point 7: no block is `{}`, and E04 names each source used
        return {}
    block: dict[str, Any] = _guard(issues, lambda: obj(d["sources"], where), {})
    found: dict[str, str] = {}
    for clip_id, entry in block.items():
        try:
            fields = obj(entry, where)
            only_keys(fields, {"qhash"}, where)
            found[clip_id] = req_str(fields, "qhash", where, min_len=1)
        except SchemaError as exc:
            detail = f"{shown_id(clip_id)}: {plain(exc.detail_es)}"
            issues.append(Issue("E01", "error", where, detail))
    return found


def _clip(item: object, path: str) -> Clip:
    d = obj(item, path)
    kind = choice(req_str(d, "kind", path), ("voice", "gap"), join_path(path, "kind"))
    if kind == "voice":
        only_keys(d, {"kind", "at_f", "src", "in_f", "out_f", "why"}, path)
        return VoiceClip(
            at_f=whole(d, "at_f", path),
            src=req_str(d, "src", path, min_len=1),
            in_f=whole(d, "in_f", path),
            out_f=whole(d, "out_f", path),
            why=req_str(d, "why", path),
        )
    only_keys(d, {"kind", "at_f", "dur_f", "why"}, path)
    return GapClip(
        at_f=whole(d, "at_f", path), dur_f=whole(d, "dur_f", path), why=req_str(d, "why", path)
    )


def _span(item: object, path: str) -> Span:
    d = obj(item, path)
    kind = choice(req_str(d, "kind", path), _SPAN_KINDS, join_path(path, "kind"))
    common: dict[str, Any] = {
        "at_f": whole(d, "at_f", path),
        "dur_f": whole(d, "dur_f", path),
        "look": None if d.get("look") is None else req_str(d, "look", path),
        "fade_in_f": opt_whole(d, "fade_in_f", path, 0),
        "fade_out_f": opt_whole(d, "fade_out_f", path, 0),
        "why": opt_str(d, "why", path, ""),
    }
    if kind == "cam":
        only_keys(d, _SPAN_COMMON | {"src", "zoom", "cx", "cy", "anchor", "push", "src_f"}, path)
        return CamSpan(
            **common,
            src=req_str(d, "src", path, min_len=1),
            zoom=opt_float(d, "zoom", path, 1.0),
            cx=opt_float(d, "cx", path, 0.5),
            cy=opt_float(d, "cy", path, 0.5),
            anchor=choice(opt_str(d, "anchor", path, "center"), ANCHORS, join_path(path, "anchor")),
            push=opt_float(d, "push", path, 0.0),
            src_f=opt_whole(d, "src_f", path, None),
        )
    if kind == "broll":
        only_keys(d, _SPAN_COMMON | {"src", "src_f", "push", "cx", "cy", "dim", "sharpen"}, path)
        return BrollSpan(
            **common,
            src=req_str(d, "src", path, min_len=1),
            src_f=whole(d, "src_f", path),
            push=opt_float(d, "push", path, 0.07),
            cx=opt_float(d, "cx", path, 0.5),
            cy=opt_float(d, "cy", path, 0.5),
            dim=opt_float(d, "dim", path, 1.0),
            sharpen=opt_float(d, "sharpen", path, 0.0),
        )
    if kind == "screen":
        only_keys(d, _SPAN_COMMON | {"src", "src_f", "keys", "remap", "card_y"}, path)
        return ScreenSpan(
            **common,
            src=req_str(d, "src", path, min_len=1),
            src_f=whole(d, "src_f", path),
            keys=tuple(_listed(d, "keys", path, _key)),
            remap=tuple(_listed(d, "remap", path, _remap, optional=True)),
            card_y=opt_float(d, "card_y", path, 0.47),
        )
    only_keys(d, _SPAN_COMMON | {"color"}, path)
    return ColorSpan(**common, color=color(d.get("color"), join_path(path, "color")))


def _listed[T](
    d: dict[str, Any],
    key: str,
    path: str,
    parse: Callable[[object, str], T],
    optional: bool = False,
) -> list[T]:
    """The items of the list `key` of `d`, each parsed by `parse`. The first bad one raises."""
    if optional and key not in d:
        return []
    where = join_path(path, key)
    return [parse(item, join_path(where, i)) for i, item in enumerate(req_list(d, key, path))]


def _key(item: object, path: str) -> ScreenKey:
    d = obj(item, path)
    only_keys(d, {"at_f", "crop", "card"}, path)
    crop = _pair_or_more(d, "crop", path, 3, lambda v, where: _float(v, where, None, None))
    card = _pair_or_more(d, "card", path, 2, lambda v, where: _int(v, where, -MAX_WHOLE, MAX_WHOLE))
    return ScreenKey(
        at_f=whole(d, "at_f", path),
        crop=(crop[0], crop[1], crop[2]),
        card=(card[0], card[1]),
    )


def _remap(item: object, path: str) -> RemapPoint:
    d = obj(item, path)
    only_keys(d, {"at_f", "src_f", "speed"}, path)
    return RemapPoint(
        at_f=whole(d, "at_f", path),
        src_f=whole(d, "src_f", path),
        speed=opt_float(d, "speed", path, 1.0),
    )


def _pair_or_more[N: (int, float)](
    d: dict[str, Any], key: str, path: str, count: int, read: Callable[[object, str], N]
) -> list[N]:
    """The list `key` as exactly `count` numbers, each read by `read` (a float or an int)."""
    items = req_list(d, key, path)
    where = join_path(path, key)
    if len(items) != count:
        raise SchemaError(where, f"debe tener {count} números (tiene {len(items)})")
    return [read(value, join_path(where, i)) for i, value in enumerate(items)]
