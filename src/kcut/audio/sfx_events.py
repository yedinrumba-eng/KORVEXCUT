"""The events of `edit/sfx.json` resolved against an EDL (spec S1.8a, 001.15): each one with its
frame of the output, its length, its gain and the parameters of its type, ready for the bus.

Pure. `resolve_events` does not raise for a mistake in the file: every problem is an `Issue`
(A03 for a `dur_f` longer than the video, A04 for a word that the cut does not keep, A05 for a
frame of a source that is not heard, A06 when it is heard more than once and the first is used, A07
for a time or a window outside the video, A08 when part of a sound falls outside it and is cut),
and an event with an error is left out of the result. A message never repeats text of the file.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from kcut.anchors import resolve_time
from kcut.audio.sfx_library import SFX, SfxDef
from kcut.audio.sfx_schema import SfxDoc, SfxEventDoc
from kcut.edl.model import Edl
from kcut.edl.words import KeptWord
from kcut.issues import Issue
from kcut.schema_util import describe_value
from kcut.timebase import SAMPLE_RATE, ms_to_f_round
from kcut.timebase import spf as samples_per_frame

Align = Literal["start", "center", "end"]
# The budget of the synthesis (001.36, point 2). A `dur_f` could be as long as the video: a `pad` of
# 20 minutes asks for about 2.5 GB. 30 s are enough for "a short cushion" and "a rise before a hit",
# and 1200 s of effects in all keep the CPU of the synthesis to about 70 s (001.37, point 9: the
# total was 600 s, and 2000 `kick`, the most events a file may have, last more than that)
MAX_SFX_DUR_S = 30
MAX_SFX_TOTAL_S = 1200


@dataclass(frozen=True)
class SfxEvent:
    """An event ready to be made: `at_f` is the frame of the output the `align` says (`start`: the
    first sample, `center`: the middle one, `end`: the last one falls at `at_f * spf`). `dur_f` is
    `None` in the types of a fixed length. `seed`, `freq` and `rate` are `None` in the types that
    do not have them."""

    type: str
    at_f: int
    align: Align
    dur_f: int | None
    gain: float
    seed: int | None
    freq: float | None
    rate: float | None


def resolve_events(
    doc: SfxDoc, kept: Sequence[KeptWord], edl: Edl, fps: int
) -> tuple[list[SfxEvent], list[Issue]]:
    """The events of `doc` in output frames, in the order of the file, and the issues. `at` is
    resolved with `kcut.anchors.resolve_time`. `dur_f` is `None` in the fixed types, the given one
    (or `ms_to_f_round(default_dur_ms, fps)`) in `whoosh` and `shimmer` and the given one in the
    required ones; `gain` is the given one or the default of the type; `seed`, `freq` and `rate`
    are the given ones or the default of their `ParamSpec` in the types that have them. The windows
    of gain are checked too (A07): `0 <= start < end <= frames`.

    The words are indexed once, by id, and not looked up in the list for each anchor (001.36,
    point 1). An event of a type with `dur_f` that lasts more than `MAX_SFX_DUR_S` is an A03. Past
    `MAX_SFX_TOTAL_S` of effects in all (the events that are left, added), it returns `[]` next to
    one A03 of level error in `events` (001.37, point 13): there is nothing to make, and the error
    stops `kcut mix` before any effect is synthesized."""
    issues: list[Issue] = []
    events: list[SfxEvent] = []
    spf = samples_per_frame(fps)
    index: dict[str, KeptWord] = {}
    for word in kept:
        index.setdefault(word.id, word)  # the first one with an id, as the list search found it
    for event in doc.events:
        resolved = _resolve(event, index, edl, fps, spf, issues)
        if resolved is not None:
            events.append(resolved)
    for window in doc.windows:
        if not 0 <= window.start < window.end <= edl.frames:
            message = (
                f"queda en [{describe_value(window.start)}, {describe_value(window.end)}) y el "
                f"video tiene {edl.frames} frames: tiene que cumplirse 0 <= start < end <= frames"
            )
            issues.append(Issue("A07", "error", f"windows[{window.index}]", message))
    total = sum(_length(event, spf) for event in events)
    if total > MAX_SFX_TOTAL_S * SAMPLE_RATE:
        message = f"los efectos suman más de {MAX_SFX_TOTAL_S} s de audio"
        issues.append(Issue("A03", "error", "events", message))
        return [], issues
    return events, issues


def _length(event: SfxEvent, spf: int) -> int:
    """The samples that `event` makes: the fixed length of its type or `dur_f * spf`."""
    fixed = SFX[event.type].fixed_n
    return fixed if fixed is not None else (event.dur_f or 0) * spf


def _resolve(
    event: SfxEventDoc,
    index: Mapping[str, KeptWord],
    edl: Edl,
    fps: int,
    spf: int,
    issues: list[Issue],
) -> SfxEvent | None:
    sfx = SFX.get(event.type)
    where = f"events[{event.index}]"
    if sfx is None:  # a document that was not made by `parse_sfx`
        message = "tipo de efecto desconocido"
        issues.append(Issue("A02", "error", f"{where}.type", message))
        return None
    before = len(issues)
    at_f = _moment(event, index, edl, issues)
    dur_f = _duration(event, sfx, edl, fps, issues)
    failed = any(issue.level == "error" for issue in issues[before:])  # a warning keeps the event
    if failed or at_f is None:
        return None
    align: Align = (
        "center" if event.align == "center" else "end" if event.align == "end" else "start"
    )
    n = sfx.fixed_n if sfx.fixed_n is not None else (dur_f or 0) * spf
    cut = _cut(at_f, align, n, spf, edl.frames * spf)
    if cut is not None:
        issues.append(Issue("A08", "warning", where, cut))
    return SfxEvent(
        sfx.id,
        at_f,
        align,
        dur_f,
        sfx.default_gain if event.gain is None else event.gain,
        _int_param(event.seed, sfx, "seed"),
        _float_param(event.freq, sfx, "freq"),
        _float_param(event.rate, sfx, "rate"),
    )


def _scope(at: object, index: Mapping[str, KeptWord]) -> Sequence[KeptWord]:
    """The words `resolve_time` has to look through for the moment `at`: none, unless it is a word
    anchor, and then only the one with that id, found in the index and not in the whole list."""
    if isinstance(at, dict):
        wanted = at.get("word")
        word = index.get(wanted) if isinstance(wanted, str) else None
        return () if word is None else (word,)
    return ()


def _moment(
    event: SfxEventDoc, index: Mapping[str, KeptWord], edl: Edl, issues: list[Issue]
) -> int | None:
    """The frame of `event.at` (A04 / A05 / A07 if it cannot be found or is outside the video, A06
    if a frame of a source is heard more than once and the first is used)."""
    path = f"events[{event.index}].at"
    found = resolve_time(event.at, _scope(event.at, index), edl)
    if found.problem == "word_not_kept":
        message = "la palabra no está entre las que conserva el corte"
        issues.append(Issue("A04", "error", path, message))
    elif found.problem == "src_not_heard":
        message = "ese frame del clip no se oye en la salida"
        issues.append(Issue("A05", "error", path, message))
    elif found.problem is not None or found.frame is None:
        issues.append(Issue("A01", "error", path, "no es un frame ni un ancla"))
    else:
        if found.repeats > 1:
            message = f"ese frame del clip se oye {found.repeats} veces: se usa la primera"
            issues.append(Issue("A06", "warning", path, message))
        if 0 <= found.frame < edl.frames:
            return found.frame
        message = (
            f"cae en el frame {describe_value(found.frame)} y el video tiene {edl.frames}: "
            "tiene que estar en [0, frames)"
        )
        issues.append(Issue("A07", "error", path, message))
    return None


def _duration(
    event: SfxEventDoc, sfx: SfxDef, edl: Edl, fps: int, issues: list[Issue]
) -> int | None:
    """`dur_f` of the event: `None` in a fixed type, the given one, or the default of the type
    (`ms_to_f_round(default_dur_ms, fps)`). A given one over the frames of the EDL is an A03."""
    if sfx.fixed_n is not None:
        return None
    given = event.dur_f
    where = f"events[{event.index}].dur_f"
    if given is not None and given > edl.frames:
        seen = describe_value(given)
        message = f"debe estar entre 1 y {edl.frames} (los frames del video; vino {seen})"
        issues.append(Issue("A03", "error", where, message))
        return None
    if given is not None and given > MAX_SFX_DUR_S * fps:  # more than 30 s, in whole frames
        message = f"dura más de {MAX_SFX_DUR_S} s; un efecto va hasta {MAX_SFX_DUR_S} s"
        issues.append(Issue("A03", "error", where, message))
        return None
    if given is not None:
        return given
    if sfx.default_dur_ms is not None:
        return ms_to_f_round(sfx.default_dur_ms, fps)
    return None


def _cut(at_f: int, align: Align, n: int, spf: int, total: int) -> str | None:
    """The message of an A08 if the `n` samples of a sound placed at `at_f` go before sample 0 or
    after `total`, and so are cut; `None` if they all fit."""
    first = at_f * spf
    if align == "center":
        first -= n // 2
    elif align == "end":
        first -= n - 1
    before, after = first < 0, first + n > total
    if before and after:
        return "parte del efecto cae antes del inicio y otra después del final: se recorta"
    if before:
        return "parte del efecto cae antes del inicio del video y se recorta"
    if after:
        return "parte del efecto cae después del final del video y se recorta"
    return None


def _int_param(given: int | None, sfx: SfxDef, name: str) -> int | None:
    """`given`, or the default of the `ParamSpec` called `name` of the type; `None` if the type
    does not have that parameter."""
    spec = next((p for p in sfx.params if p.name == name), None)
    if spec is None:
        return None
    if given is not None:
        return given
    default = spec.default
    return default if isinstance(default, int) and not isinstance(default, bool) else None


def _float_param(given: float | None, sfx: SfxDef, name: str) -> float | None:
    """Like `_int_param`, for a number that may have a fraction (`freq`, `rate`)."""
    spec = next((p for p in sfx.params if p.name == name), None)
    if spec is None:
        return None
    if given is not None:
        return given
    default = spec.default
    if isinstance(default, int | float) and not isinstance(default, bool):
        return float(default)
    return None
