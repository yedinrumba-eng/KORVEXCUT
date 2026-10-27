"""From output frames to source frames and back (spec S1.5a). Pure: integers and `Fraction`s.

The source clock is the one of spec 0.6: frame `f` of a clip is the instant `f / fps` from the
start of its file. A camera that is synchronized to the voice reads the frame the voice has at
that moment, moved by the offset between the two cameras (`shift_f`).
"""

import math
from bisect import bisect_right
from collections.abc import Sequence
from fractions import Fraction

from kcut.edl.model import (
    BrollSpan,
    CamSpan,
    Clip,
    ColorSpan,
    Edl,
    RemapPoint,
    ScreenSpan,
    Span,
    VoiceClip,
)
from kcut.errors import ProjectError
from kcut.ingest.inventory import Inventory
from kcut.timebase import ms_to_f_round


def voice_at(edl: Edl, out_f: int) -> VoiceClip | None:
    """The voice clip playing at output frame `out_f`, or `None` (a gap, or past the end)."""
    for clip in edl.clips:
        if isinstance(clip, VoiceClip) and clip.at_f <= out_f < clip.at_f + clip.dur_f:
            return clip
    return None


def is_contiguous(clips: Sequence[Clip]) -> bool:
    """Do the clips start at 0 and follow one another with no hole, each one of 1 frame or more?"""
    cursor = 0
    for clip in clips:
        if clip.at_f != cursor or clip.dur_f <= 0:
            return False
        cursor += clip.dur_f
    return True


def group_of(inv: Inventory, src: str) -> frozenset[str]:
    """The clips whose clock `src` shares: the master of the camera sync and its members if `src`
    is one of them, otherwise only `src` (a clip that was rejected or never synced is alone)."""
    sync = inv.sync
    members = {member.id for member in sync.members}
    if sync.master is not None and (src == sync.master or src in members):
        return frozenset({sync.master, *members})
    return frozenset({src})


def _offset_ms(inv: Inventory, src: str) -> int | None:
    """Where `src` starts on the master's clock: 0 for the master, `offset_ms` for a member."""
    if inv.sync.master == src:
        return 0
    for member in inv.sync.members:
        if member.id == src:
            return member.offset_ms
    return None


def shift_f(inv: Inventory, voice_src: str, cam_src: str, fps: int) -> int:
    """Frames to add to a frame of `voice_src` to get the same instant in `cam_src`:
    `ms_to_f_round(off(voice_src) - off(cam_src))`, with `off(master) = 0` and
    `off(member) = offset_ms` (a2 at +4722 ms and 30 fps: -142). The same clip is 0. Two clips that
    are not in one sync group have no shift: that is a ProjectError (E11 stops it before)."""
    if voice_src == cam_src:
        return 0
    voice, cam = _offset_ms(inv, voice_src), _offset_ms(inv, cam_src)
    if voice is None or cam is None:
        raise ProjectError(f"{voice_src} y {cam_src} no están sincronizados entre sí")
    return ms_to_f_round(voice - cam, fps)


class VoiceIndex:
    """The clips of an EDL in time order, to find those that overlap a stretch without scanning
    them all (validation looks at every span)."""

    def __init__(self, edl: Edl) -> None:
        order = sorted(range(len(edl.clips)), key=lambda i: edl.clips[i].at_f)
        self.items: list[tuple[int, Clip]] = [(i, edl.clips[i]) for i in order]
        self._starts = [clip.at_f for _, clip in self.items]

    def overlapping(self, start_f: int, end_f: int) -> list[tuple[int, Clip]]:
        """`(index in edl.clips, clip)` of the clips with frames in `[start_f, end_f)`."""
        first = max(0, bisect_right(self._starts, start_f) - 1)
        found: list[tuple[int, Clip]] = []
        for position in range(first, len(self.items)):
            index, clip = self.items[position]
            if clip.at_f >= end_f:
                break
            dur = clip.dur_f
            if clip.at_f + dur > start_f and dur > 0:
                found.append((index, clip))
        return found


def span_source_frames(
    edl: Edl, span: Span, inv: Inventory, index: VoiceIndex | None = None
) -> list[int]:
    """One source frame for each output frame of the span, in order. `index` is the `VoiceIndex`
    of the EDL if the caller has one (it is made once for all the spans: 001.24, point 4).

    A synchronized camera: `c.in_f + (k - c.at_f) + shift_f(...)` with `c` the voice clip at `k`.
    A free camera or a b-roll: `src_f + (k - at_f)`. A screen insert with `remap`: from the last
    point with `at_f <= r`, `p.src_f + floor((r - p.at_f) * p.speed)` (exact: the speed is read as
    the decimal it was written, `0.29 * 100` is 29 and not 28.999...); without it, `src_f + r`.
    A color span reads nothing.
    """
    if isinstance(span, ColorSpan):
        return []
    if isinstance(span, ScreenSpan) and span.remap:
        return _remapped(span.remap, span.dur_f)
    if isinstance(span, CamSpan) and span.src_f is None:
        return _synchronized(edl, span, inv, index if index is not None else VoiceIndex(edl))
    base = _start(span)
    return [base + r for r in range(span.dur_f)]


def span_source_bounds(
    edl: Edl, span: Span, inv: Inventory, index: VoiceIndex | None = None
) -> list[tuple[int, int]]:
    """The first and the last source frame (both included) of each stretch of the span that reads
    in order: what `span_source_frames` reaches, without making the list. Used by E12, so a span of
    a billion frames costs as little as one of ten. A synchronized camera has one stretch per
    voice clip of its group the span crosses; a remap one per point. `index` is the `VoiceIndex`
    of the EDL if the caller has one: made again for each span, a check of thousands of them would
    sort the clips thousands of times (001.24, point 4)."""
    if isinstance(span, ColorSpan) or span.dur_f <= 0:
        return []
    if isinstance(span, ScreenSpan) and span.remap:
        return _remap_bounds(span.remap, span.dur_f)
    if isinstance(span, CamSpan) and span.src_f is None:
        return _synchronized_bounds(edl, span, inv, index if index is not None else VoiceIndex(edl))
    base = _start(span)
    return [(base, base + span.dur_f - 1)]


def source_to_output(edl: Edl, src: str, f: int) -> list[int]:
    """The output frames where frame `f` of `src` is heard: one per voice clip of `src` that
    holds it (usually zero or one), in the order of the clips."""
    return [
        clip.at_f + (f - clip.in_f)
        for clip in edl.clips
        if isinstance(clip, VoiceClip) and clip.src == src and clip.in_f <= f < clip.out_f
    ]


def _start(span: CamSpan | BrollSpan | ScreenSpan) -> int:
    """The source frame a span that is not synchronized starts from."""
    if span.src_f is None:
        raise ProjectError("un cam sincronizado no tiene frame de inicio en la fuente")
    return span.src_f


def _synchronized(edl: Edl, span: CamSpan, inv: Inventory, index: VoiceIndex) -> list[int]:
    """The source frames of a synchronized camera: for each voice clip the span crosses, the
    frames of the clip it covers, in order. A frame with no voice is a ProjectError."""
    shifts: dict[str, int] = {}
    frames: list[int] = []
    cursor, end = span.at_f, span.at_f + span.dur_f
    for _, clip in index.overlapping(span.at_f, end):
        if not isinstance(clip, VoiceClip) or cursor >= end:
            continue
        low, high = max(cursor, clip.at_f), min(end, clip.at_f + clip.dur_f)
        if low >= high:
            continue
        if low > cursor:
            break  # a hole: the frame at `cursor` has no voice
        if clip.src not in shifts:
            shifts[clip.src] = shift_f(inv, clip.src, span.src, edl.fps)
        base = clip.in_f - clip.at_f + shifts[clip.src]
        frames.extend(base + k for k in range(low, high))
        cursor = high
    if cursor < end:
        raise ProjectError(
            f"el frame {cursor} de salida no tiene voz: un cam sincronizado la necesita"
        )
    return frames


def _synchronized_bounds(
    edl: Edl, span: CamSpan, inv: Inventory, index: VoiceIndex
) -> list[tuple[int, int]]:
    group = group_of(inv, span.src)
    start, end = span.at_f, span.at_f + span.dur_f
    bounds: list[tuple[int, int]] = []
    for _, clip in index.overlapping(start, end):
        if not isinstance(clip, VoiceClip) or clip.src not in group:
            continue
        low, high = max(start, clip.at_f), min(end, clip.at_f + clip.dur_f) - 1
        shift = shift_f(inv, clip.src, span.src, edl.fps)
        bounds.append(
            (clip.in_f + (low - clip.at_f) + shift, clip.in_f + (high - clip.at_f) + shift)
        )
    return bounds


def _advance(point: RemapPoint, r: int) -> int:
    """`point.src_f + floor((r - point.at_f) * point.speed)`, exact."""
    return point.src_f + math.floor(Fraction(repr(point.speed)) * (r - point.at_f))


def _remapped(points: tuple[RemapPoint, ...], count: int) -> list[int]:
    frames: list[int] = []
    current = 0
    for r in range(count):
        while current + 1 < len(points) and points[current + 1].at_f <= r:
            current += 1
        frames.append(_advance(points[current], r))
    return frames


def _remap_bounds(points: tuple[RemapPoint, ...], count: int) -> list[tuple[int, int]]:
    bounds: list[tuple[int, int]] = []
    for i, point in enumerate(points):
        low = 0 if i == 0 else point.at_f
        high = (points[i + 1].at_f if i + 1 < len(points) else count) - 1
        high = min(high, count - 1)
        if low <= high:
            bounds.append((_advance(point, low), _advance(point, high)))
    return bounds
