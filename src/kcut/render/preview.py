"""One frame of the cut without graphics, made from the proxy, for `graphics still` and for the
storyboard (spec S1.6b, 001.15). It is what the render makes for that frame, but from the small
file: fast to read, and the same crop, zoom, look and fades (`frame_fx.span_frame`).
"""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut.edl.model import ColorSpan, Edl, Span, span_src
from kcut.edl.timeline import span_source_frames
from kcut.errors import ProjectError
from kcut.ff.reader import grab, proxy_index
from kcut.ingest.inventory import Inventory
from kcut.project import Project
from kcut.render.frame_fx import FxContext, look_for, span_frame
from kcut.render.proxy_file import proxy_of


def base_frame(
    project: Project,
    edl: Edl,
    inv: Inventory,
    out_f: int,
    ctx: FxContext,
    *,
    log: Path | None,
) -> NDArray[np.uint8]:
    """The frame `out_f` of the output, `(H, W, 3)` BGR, without graphics, made from the proxy: the
    span that covers it, its source frame (`span_source_frames`, index `out_f - span.at_f`) read
    from the proxy with the look of the span, and `span_frame` at the size of the output. A color
    span reads nothing. A proxy that is not there is a ProjectError that says `kcut ingest`."""
    span = _span_at(edl, out_f)
    i = out_f - span.at_f
    if isinstance(span, ColorSpan):
        return span_frame(None, span, i, ctx)
    src_id = span_src(span)
    clip = None if src_id is None else inv.by_id(src_id)
    if src_id is None or clip is None:
        raise ProjectError(f"falta el proxy de {src_id or 'un tramo'}; corre kcut ingest")
    path, size = proxy_of(project, clip)
    source_f = span_source_frames(edl, span, inv)[i]
    picture = grab(
        path,
        proxy_index(clip, source_f, edl.fps),
        edl.fps,
        size,
        rgb_filters=look_for(edl, span, project.config.brand),
        log=log,
    )
    return span_frame(picture, span, i, ctx)


def _span_at(edl: Edl, out_f: int) -> Span:
    """The span that has output frame `out_f`."""
    for span in edl.spans:
        if span.at_f <= out_f < span.at_f + span.dur_f:
            return span
    raise ProjectError(f"el frame {out_f} no cae en ningún tramo del EDL")
