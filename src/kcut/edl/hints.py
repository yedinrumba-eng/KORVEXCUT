"""The warnings about a span (spec S1.5a): W01 blurry enlargement, W03 a cut that shows nothing,
W04 a voice cut inside a synchronized shot, W05 a look that is ignored. Nothing here fails a check.
"""

from fractions import Fraction
from itertools import pairwise

from kcut.config.model import ProjectConfig
from kcut.edl.model import BrollSpan, CamSpan, ColorSpan, Edl, Span, VoiceClip
from kcut.edl.refs import SourceStatus
from kcut.edl.timeline import VoiceIndex, is_contiguous
from kcut.ingest.inventory import Inventory
from kcut.issues import Issue
from kcut.render.geometry import upscale_factor
from kcut.schema_util import describe_value

MAX_UPSCALE = 1.10  # W01 warns when the picture is stretched more than 10 % past its pixels
# W03 warns when two shots of one camera differ less than 15 % in zoom
MIN_ZOOM_CHANGE = Fraction(15, 100)


def span_hints(edl: Edl, inv: Inventory, cfg: ProjectConfig, status: SourceStatus) -> list[Issue]:
    """W01, W03, W04 and W05 for every span, in the order of the spans."""
    issues: list[Issue] = []
    index = VoiceIndex(edl) if is_contiguous(edl.clips) else None
    for i, span in enumerate(edl.spans):
        path = f"spans[{i}]"
        if isinstance(span, ColorSpan) and span.look is not None:
            issues.append(
                Issue("W05", "warning", f"{path}.look", "un tramo de color ignora su look")
            )
        issues += _upscale(span, path, inv, cfg, status)
        if i and isinstance(span, CamSpan) and _flat_cut(edl.spans[i - 1], span, status):
            name = describe_value(span.src)
            found = f"corte entre dos cam de {name} que casi no cambia el zoom"
            issues.append(Issue("W03", "warning", path, found))
        if index is not None and isinstance(span, CamSpan) and span.src_f is None:
            issues += _crosses_cut(index, span, path)
    return issues


def _upscale(
    span: Span, path: str, inv: Inventory, cfg: ProjectConfig, status: SourceStatus
) -> list[Issue]:
    """W01: a cam or b-roll that enlarges its source more than `MAX_UPSCALE`."""
    if isinstance(span, CamSpan):
        zoom_max = span.zoom * (1 + span.push)
    elif isinstance(span, BrollSpan):
        zoom_max = 1 + span.push
    else:
        return []
    clip = inv.by_id(span.src)
    if clip is None or clip.video is None or not status.video_ok(span.src):
        return []
    factor = upscale_factor(
        zoom_max, clip.video.display_w, clip.video.display_h, cfg.output.w, cfg.output.h
    )
    if factor <= MAX_UPSCALE:
        return []
    found = (
        f"agranda {factor:.2f}x los pixeles de {describe_value(span.src)} "
        f"({clip.video.display_w}x{clip.video.display_h}); se verá blando"
    )
    return [Issue("W01", "warning", path, found)]


def _flat_cut(before: Span, after: CamSpan, status: SourceStatus) -> bool:
    """Two cam shots of one source in a row whose zoom, where they meet, differs less than 15 %:
    the end of the first (`zoom * (1 + push)`) against the start of the second."""
    if not isinstance(before, CamSpan) or before.src != after.src:
        return False
    if not status.video_ok(after.src) or before.dur_f <= 0:
        return False
    # exact, so a change of exactly 15 % (1.0 to 1.15) is not "less than 15 %"
    end = Fraction(repr(before.zoom)) * (1 + Fraction(repr(before.push)))
    return end > 0 and abs(Fraction(repr(after.zoom)) - end) / end < MIN_ZOOM_CHANGE


def _crosses_cut(index: VoiceIndex, span: CamSpan, path: str) -> list[Issue]:
    """W04: a voice cut strictly inside a synchronized shot, between two voice clips whose source
    does not go on (another clip, or a jump in the same one): the picture follows the voice over
    it, which is what the cut is for, so this only informs."""
    end = span.at_f + span.dur_f
    voices = [clip for _, clip in index.overlapping(span.at_f, end) if isinstance(clip, VoiceClip)]
    for before, after in pairwise(voices):
        if span.at_f < after.at_f < end and (before.src != after.src or before.out_f != after.in_f):
            found = f"el cam sincronizado cruza un corte de voz en el frame {after.at_f} de salida"
            return [Issue("W04", "warning", path, found)]
    return []
