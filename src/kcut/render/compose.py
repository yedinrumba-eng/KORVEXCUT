"""The picture of the cut, frame by frame, into one encode (spec S1.5b, DS2).

For each span, in order: the source frame of every output frame (`span_source_frames`), cut into
runs that one ffmpeg process reads in a row (`plan_reads`) from the mezzanine, with the look of
the span applied in the reader; then `frame_fx.span_frame` makes the output frame, the overlay (the
graphics of `gfx/overlay.py`, S1.6b) goes on top if there is one, and the encoder writes it. A
frame is always built from a source frame that was computed, never from "the next one", so the
picture cannot drift from the sound.
"""

from collections.abc import Iterator
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut.console import Progress
from kcut.edl.model import ColorSpan, Edl, Span, span_src
from kcut.edl.timeline import VoiceIndex, span_source_frames
from kcut.errors import InternalError
from kcut.ff.reader import FrameReader
from kcut.gfx.overlay import OverlaySource
from kcut.ingest.inventory import Inventory
from kcut.project import Project
from kcut.render.encoder import Encoder
from kcut.render.frame_fx import FxContext, fx_context, look_for, span_frame
from kcut.render.mezz import MezzIndex
from kcut.render.reads import plan_reads

Frame = NDArray[np.uint8]


def compose_video(
    project: Project,
    edl: Edl,
    inv: Inventory,
    mezz: MezzIndex,
    dst: Path,
    overlay: OverlaySource | None,
    progress: Progress | None,
    *,
    log: Path | None = None,
) -> int:
    """Write the picture of `edl` to `dst` and return how many frames were written, which has to
    be `edl.frames` (anything else is an InternalError: the EDL was checked before this)."""
    ctx = fx_context(project, edl)
    voices = VoiceIndex(edl)
    done = 0
    with Encoder(dst, edl.out_w, edl.out_h, edl.fps, log) as encoder:
        for span in edl.spans:
            frames = _span_frames(project, edl, inv, mezz, span, ctx, voices, log)
            for i, frame in enumerate(frames):
                out = frame if overlay is None else overlay.blend(frame, span.at_f + i)
                encoder.write(out)
                done += 1
                if progress is not None:
                    progress.update(done)
        written = encoder.close()
    if written != edl.frames:
        raise InternalError(f"el render escribió {written} frames y el EDL pide {edl.frames}")
    return written


def _span_frames(
    project: Project,
    edl: Edl,
    inv: Inventory,
    mezz: MezzIndex,
    span: Span,
    ctx: FxContext,
    voices: VoiceIndex,
    log: Path | None,
) -> Iterator[Frame]:
    """The `span.dur_f` output frames of one span, in order."""
    if isinstance(span, ColorSpan):
        for i in range(span.dur_f):
            yield span_frame(None, span, i, ctx)
        return
    src = span_src(span)
    if src is None:
        raise InternalError("un tramo que lee una fuente no dice cuál")
    look = look_for(edl, span, project.config.brand)
    made = 0
    for run in plan_reads(span_source_frames(edl, span, inv, voices)):
        path, first, size = mezz.locate_run(src, run.first, run.last)
        count = run.last - run.first + 1
        wanted = 0  # the next of `run.picks` still to come out
        with FrameReader(path, first, count, edl.fps, size, rgb_filters=look, log=log) as reader:
            for current, picture in enumerate(reader, start=run.first):
                while wanted < len(run.picks) and run.picks[wanted] == current:
                    yield span_frame(picture, span, made, ctx)
                    made += 1
                    wanted += 1
    if made != span.dur_f:
        raise InternalError(f"el tramo dio {made} frames y pide {span.dur_f}")
