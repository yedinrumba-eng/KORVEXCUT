"""What an EDL says about the project: its fps and size, its sources, its looks and which camera
is synchronized to which voice (spec S1.5a, 001.15). Pure; E02, E03, E04, E05, E11 and E14.

A source that fails E04 or E05 is not looked at again by `edl.ranges` (no cascade of errors).
"""

from dataclasses import dataclass

from kcut.config.model import ProjectConfig
from kcut.edl.model import CamSpan, Edl, GapClip, VoiceClip, span_src
from kcut.edl.timeline import VoiceIndex, group_of, is_contiguous
from kcut.ingest.inventory import Inventory
from kcut.issues import Issue
from kcut.schema_util import describe_value

# The looks S1.5b defines in `render/looks.py`. They are listed here too because the EDL has to
# be checked before anything renders (and `edl` does not import `render`): a test in S1.5b keeps
# both lists equal.
LOOK_IDS = frozenset({"neutro", "contraste", "calido", "frio", "cinematico", "bn-acento"})
_VOICE_CLASSES = ("video_voz", "audio")


@dataclass(frozen=True)
class SourceStatus:
    """E04 and E05 for every `src` the EDL uses, and which sources `edl.ranges` may trust."""

    issues: list[Issue]
    broken: frozenset[str]  # ids with an E04, or that are not in the inventory
    no_voice: frozenset[str]  # ids used as voice that cannot be (E05)
    no_video: frozenset[str]  # ids used as picture that cannot be (E05)

    def voice_ok(self, src: str) -> bool:
        return src not in self.broken and src not in self.no_voice

    def video_ok(self, src: str) -> bool:
        return src not in self.broken and src not in self.no_video


def check_refs(edl: Edl, inv: Inventory, cfg: ProjectConfig, version_from_name: int) -> list[Issue]:
    """E02, E03, E04, E05, E14 and E11, in that order."""
    issues: list[Issue] = []
    if edl.fps != cfg.output.fps:
        found = f"el fps del EDL ({edl.fps}) no es el del proyecto ({cfg.output.fps})"
        issues.append(Issue("E02", "error", "fps", found))
    if edl.version != version_from_name:
        found = f"la version del EDL ({edl.version}) no es la del nombre del archivo"
        issues.append(Issue("E02", "error", "version", f"{found} ({version_from_name})"))
    if (edl.out_w, edl.out_h) != (cfg.output.w, cfg.output.h):
        found = f"el tamaño de salida del EDL ({edl.out_w}x{edl.out_h}) no es el del proyecto"
        issues.append(Issue("E03", "error", "output", f"{found} ({cfg.output.w}x{cfg.output.h})"))
    status = source_status(edl, inv)
    issues += status.issues
    issues += _unknown_looks(edl)
    issues += _unsynchronized(edl, inv, status)
    return issues


def source_status(edl: Edl, inv: Inventory) -> SourceStatus:
    """Check every `src` the EDL uses against its `sources` block and the inventory."""
    issues: list[Issue] = []
    uses = _uses(edl)
    broken: set[str] = set()
    for src in dict.fromkeys(src for src, _, _ in uses):
        clip = inv.by_id(src)
        name = describe_value(src)
        if src not in edl.sources:
            found = f"sources no cubre el clip {name}; corre kcut edl sources y pega el bloque"
        elif clip is None:
            found = f"el clip {name} de sources no está en el inventario; corre kcut edl sources"
        elif clip.qhash != edl.sources[src]:
            found = (
                f"el clip {name} del inventario no es el que el EDL usó (su qhash cambió); "
                "revisa los ids con kcut edl sources"
            )
        else:
            continue
        broken.add(src)
        issues.append(Issue("E04", "error", "sources", found))
    no_voice: set[str] = set()
    no_video: set[str] = set()
    for src, wants_voice, path in uses:
        clip = inv.by_id(src)
        name = describe_value(src)
        if clip is None:
            issues.append(Issue("E05", "error", path, f"el clip {name} no existe en el inventario"))
            broken.add(src)
        elif wants_voice and not (clip.clip_class in _VOICE_CLASSES and clip.audio is not None):
            found = f"{name} no tiene audio con voz (es {clip.clip_class}); una voz lo necesita"
            issues.append(Issue("E05", "error", path, found))
            no_voice.add(src)
        elif not wants_voice and clip.video is None:
            found = f"{name} no tiene video (es {clip.clip_class}); un tramo de imagen lo necesita"
            issues.append(Issue("E05", "error", path, found))
            no_video.add(src)
    return SourceStatus(issues, frozenset(broken), frozenset(no_voice), frozenset(no_video))


def _uses(edl: Edl) -> list[tuple[str, bool, str]]:
    """`(src, used as voice, path of the src)` for every clip and span that reads a source."""
    uses = [
        (clip.src, True, f"clips[{i}].src")
        for i, clip in enumerate(edl.clips)
        if isinstance(clip, VoiceClip)
    ]
    for i, span in enumerate(edl.spans):
        src = span_src(span)
        if src is not None:
            uses.append((src, False, f"spans[{i}].src"))
    return uses


def _unknown_looks(edl: Edl) -> list[Issue]:
    issues: list[Issue] = []
    looks = [("look", edl.look)] + [(f"spans[{i}].look", s.look) for i, s in enumerate(edl.spans)]
    for path, look in looks:
        if look is not None and look not in LOOK_IDS:
            listed = ", ".join(sorted(LOOK_IDS))
            found = f"look desconocido {describe_value(look)}; los que hay: {listed}"
            issues.append(Issue("E14", "error", path, found))
    return issues


def _unsynchronized(edl: Edl, inv: Inventory, status: SourceStatus) -> list[Issue]:
    """E11 for each synchronized camera span that does not sit on voice of its own sync group.

    It is only looked at when the clips line is contiguous (a broken line is E07's) and the
    camera is a source that can be trusted."""
    if not is_contiguous(edl.clips):
        return []
    index = VoiceIndex(edl)
    issues: list[Issue] = []
    for i, span in enumerate(edl.spans):
        if not isinstance(span, CamSpan) or span.src_f is not None or span.dur_f <= 0:
            continue
        if not status.video_ok(span.src):
            continue
        reason = _why_not_synchronized(index, inv, span)
        if reason is not None:
            name = describe_value(span.src)
            found = f"el cam sincronizado de {name} {reason}; usa src_f o cambia el tramo"
            issues.append(Issue("E11", "error", f"spans[{i}]", found))
    return issues


def _why_not_synchronized(index: VoiceIndex, inv: Inventory, span: CamSpan) -> str | None:
    group = group_of(inv, span.src)
    cursor, end = span.at_f, span.at_f + span.dur_f
    for position, clip in index.overlapping(cursor, end):
        if clip.at_f > cursor:
            return f"tiene frames sin clip de audio (desde el {cursor})"
        if isinstance(clip, GapClip):
            return f"cae sobre un gap (clips[{position}])"
        if clip.src not in group:
            other = describe_value(clip.src)
            return f"cae sobre la voz de {other} (clips[{position}]), que no es de su grupo de sync"
        cursor = max(cursor, clip.at_f + clip.dur_f)
    if cursor < end:
        return f"tiene frames sin clip de audio (desde el {cursor})"
    return None
