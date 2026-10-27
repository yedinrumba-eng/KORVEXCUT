"""The numbers of an EDL: voice inside the audio, a contiguous timeline, sums, source frames inside
their clip, fades and the warnings (spec S1.5a, 001.15). Pure.

E06 E07 E08 E09 E12 E13 E15 E17 E18 and W01-W05. A source that gave E04 or E05 (`edl.refs`) is not
looked at again here, so one wrong id is one finding and not a dozen.
"""

import math
from collections.abc import Mapping

from kcut.config.model import ProjectConfig
from kcut.edl.fields import check_fields
from kcut.edl.hints import span_hints
from kcut.edl.model import ColorSpan, Edl, Span, VoiceClip, span_src
from kcut.edl.refs import SourceStatus, source_status
from kcut.edl.shown import shown_id, shown_number
from kcut.edl.timeline import VoiceIndex, span_source_bounds
from kcut.ingest.inventory import Inventory
from kcut.issues import Issue
from kcut.timebase import ms_to_f_round

MIN_VOICE_FRAMES = 3  # W02: a voice clip shorter than this is a click


def check_ranges(
    edl: Edl,
    inv: Inventory,
    cfg: ProjectConfig,
    audio_f: Mapping[str, int],
    *,
    status: SourceStatus | None = None,
    index: VoiceIndex | None = None,
) -> list[Issue]:
    """E06 to E18 and W01 to W05. `audio_f[src]` is the voice frames the audio of `src` really has
    (E06: `min(frames of the inventory, frames of its wav16)`). `status` and `index` are what
    `validate` made once for the whole check (001.24, point 4); alone, this makes its own."""
    status = status if status is not None else source_status(edl, inv)
    index = index if index is not None else VoiceIndex(edl)
    issues: list[Issue] = []
    if edl.frames < 1:  # 001.24, point 10: an EDL with nothing in it is not an EDL
        found = f"frames tiene que ser 1 o más (vino {shown_number(edl.frames)})"
        issues.append(Issue("E13", "error", "frames", found))
    longest = math.floor(cfg.ingest.max_duration_h * 3600 * edl.fps)
    if edl.frames > longest:  # 001.25 point 4: no render of days, with the lock taken
        found = (
            f"frames ({shown_number(edl.frames)}) pasa de {longest}: es lo que dura "
            f"ingest.max_duration_h ({cfg.ingest.max_duration_h:g} h) a {shown_number(edl.fps)} fps"
        )
        issues.append(Issue("E13", "error", "frames", found))
    issues += _clip_line(edl, status, audio_f)
    issues += _span_line(edl, inv, cfg, status, index)
    issues += span_hints(edl, inv, cfg, status, index)
    return issues


def _clip_line(edl: Edl, status: SourceStatus, audio_f: Mapping[str, int]) -> list[Issue]:
    """E06 for each voice clip, E07 where the clips do not follow one another, E13 for a gap with
    no length, W02 for a click, E08 if the sum is not `frames`."""
    issues: list[Issue] = []
    cursor = total = 0
    for i, clip in enumerate(edl.clips):
        path = f"clips[{i}]"
        if clip.at_f != cursor:
            found = (
                f"empieza en el frame {shown_number(clip.at_f)} "
                f"y tendría que empezar en el {shown_number(cursor)}"
            )
            issues.append(Issue("E07", "error", path, found))
        if isinstance(clip, VoiceClip):
            issues += _voice(clip, path, status, audio_f)
        elif clip.dur_f < 1:
            issues.append(Issue("E13", "error", f"{path}.dur_f", "dur_f tiene que ser 1 o más"))
        cursor = clip.at_f + max(0, clip.dur_f)
        total += max(0, clip.dur_f)
    if total != edl.frames:
        said = shown_number(edl.frames)
        found = f"los clips suman {shown_number(total)} frames y el EDL dice {said}"
        issues.append(Issue("E08", "error", "clips", found))
    return issues


def _voice(
    clip: VoiceClip, path: str, status: SourceStatus, audio_f: Mapping[str, int]
) -> list[Issue]:
    name = shown_id(clip.src)
    in_f, out_f = shown_number(clip.in_f), shown_number(clip.out_f)
    issues: list[Issue] = []
    if clip.in_f < 0:
        issues.append(Issue("E06", "error", path, f"{name}: in_f ({in_f}) no puede ser negativo"))
    if clip.out_f <= clip.in_f:
        found = f"{name}: out_f ({out_f}) tiene que ser mayor que in_f ({in_f})"
        issues.append(Issue("E06", "error", path, found))
    elif clip.dur_f < MIN_VOICE_FRAMES:
        long = shown_number(clip.dur_f)
        found = f"{name}: el clip dura {long} frame(s); se oirá como un chasquido"
        issues.append(Issue("W02", "warning", path, found))
    real = audio_f.get(clip.src)
    if status.voice_ok(clip.src) and real is not None and clip.out_f > real:
        found = f"{name}: out_f ({out_f}) pasa del audio real, que tiene {real} frames"
        issues.append(Issue("E06", "error", path, found))
    return issues


def _span_line(
    edl: Edl, inv: Inventory, cfg: ProjectConfig, status: SourceStatus, index: VoiceIndex
) -> list[Issue]:
    """Per span: E09, E17, E12 and the numbers (`edl.fields`); E08 if the sum is not `frames`."""
    issues: list[Issue] = []
    cursor = total = 0
    for i, span in enumerate(edl.spans):
        path = f"spans[{i}]"
        if span.dur_f <= 0:
            issues.append(Issue("E09", "error", path, "dur_f tiene que ser 1 o más"))
        if span.at_f != cursor:
            found = (
                f"empieza en el frame {shown_number(span.at_f)} "
                f"y tendría que empezar en el {shown_number(cursor)}"
            )
            issues.append(Issue("E09", "error", path, found))
        cursor = span.at_f + max(0, span.dur_f)
        total += max(0, span.dur_f)
        if span.fade_in_f + span.fade_out_f > span.dur_f:
            both = shown_number(span.fade_in_f + span.fade_out_f)
            found = f"fade_in_f + fade_out_f ({both}) pasa de dur_f"
            issues.append(Issue("E17", "error", path, found))
        issues += check_fields(span, path, cfg.output.w, cfg.output.h)
        issues += _source_frames(edl, inv, span, path, status, index)
    if total != edl.frames:
        said = shown_number(edl.frames)
        found = f"los tramos suman {shown_number(total)} frames y el EDL dice {said}"
        issues.append(Issue("E08", "error", "spans", found))
    return issues


def _source_frames(
    edl: Edl, inv: Inventory, span: Span, path: str, status: SourceStatus, index: VoiceIndex
) -> list[Issue]:
    """E12: the frames the span reads have to be frames the clip has: from where its video starts
    (`vs_f`, spec 0.6) up to its last frame."""
    src = span_src(span)
    if src is None or isinstance(span, ColorSpan) or not status.video_ok(src):
        return []
    clip = inv.by_id(src)
    if clip is None or clip.video is None:
        return []
    first_f = ms_to_f_round(clip.video.start_ms, edl.fps)
    bounds = span_source_bounds(edl, span, inv, index)
    if not bounds:
        return []
    low, high = min(b[0] for b in bounds), max(b[1] for b in bounds)
    if low >= first_f and (clip.frames is None or high < clip.frames):
        return []
    last = "?" if clip.frames is None else shown_number(clip.frames - 1)
    found = (
        f"lee los frames {shown_number(low)} a {shown_number(high)} de {shown_id(src)}, "
        f"pero su video va del {shown_number(first_f)} al {last}"
    )
    return [Issue("E12", "error", path, found)]
