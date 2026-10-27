"""Mezzanines: the stretches of each source that the cut really uses, as intermediate mp4 files
(spec S1.5b, DS12, 001.15).

A 4K HDR clip of an hour cannot be decoded from the original for every frame of a render, and
tone-mapping it each time would cost more than the render. So the plan (`plan_mezz`, pure) says
which ranges of each clip the spans read, with a margin, and the size each needs: no bigger than
the biggest zoom asks for. `ensure_mezz` makes them (once: a sidecar proves a file is fresh) as
SDR bt709 CFR files at the project's fps. Frame `f` of a clip is then frame `f - start_f` of its
mezzanine (spec 0.6: a range never starts before the first frame of the video). The files and
their freshness are in `render/mezz_files.py`.
"""

from dataclasses import dataclass, field
from pathlib import Path

from kcut.config.model import ProjectConfig
from kcut.console import Progress
from kcut.edl.model import BrollSpan, CamSpan, Edl, ScreenSpan, span_src
from kcut.edl.timeline import VoiceIndex, span_source_frames
from kcut.errors import InternalError, ProjectError
from kcut.ff.color import CHAIN_VERSION, video_chain
from kcut.ingest.inventory import Clip, Inventory, Notice
from kcut.paths import resolve_in_project
from kcut.project import Project, load_inventory
from kcut.render.geometry import cover_box
from kcut.render.mezz_files import MezzEntry, MezzIndex, MezzJob, build_mezz, find_fresh, list_mezz
from kcut.timebase import ms_to_f_round

__all__ = ["MezzEntry", "MezzIndex", "MezzJob", "ensure_mezz", "plan_mezz"]
MEZZ_REL = ".kcut/mezz"  # where every job of `plan_mezz` puts its file
MERGE_GAP_FACTOR = 2  # two ranges closer than this many seconds of frames are one
SCREEN_LONG_SIDE = 3840  # a screen recording is kept up to this size: text has to stay readable


@dataclass
class _Use:
    """What the spans ask of one clip."""

    frames: set[int] = field(default_factory=set)
    zoom_max: float = 1.0  # camera and b-roll
    as_picture: bool = False
    as_screen: bool = False


def plan_mezz(edl: Edl, inv: Inventory, cfg: ProjectConfig) -> list[MezzJob]:
    """The mezzanines this EDL needs, in order of the first span that reads each clip.

    The source frames of each clip, from `span_source_frames`, become ranges `[a, b)`; two ranges
    with less than `2 * fps` frames between them are one. Each gets `fps // 2` frames of margin on
    both sides, held inside `[vs_f, frames)` (`vs_f`: where the video starts, spec 0.6), and the
    ranges that touch or overlap after that are one. The size of a clip: a camera or b-roll
    `min(1, H * max(1, zoom_max) / base_h)` of its displayed size, with `base_h` the height of the
    biggest picture of the output's shape that fits in it; a screen `min(1, 3840 / long side)`;
    the bigger of the two if it is both. Sizes are even. Each job also says `need_end_f`: one
    more than the last source frame that its range holds of what the spans read, with no
    margin (001.26, point 1)."""
    uses = _uses(edl, inv)
    fps = edl.fps
    jobs: list[MezzJob] = []
    for clip_id, use in uses.items():
        clip = inv.by_id(clip_id)
        if clip is None or clip.video is None:
            raise ProjectError(f"el clip {clip_id} no tiene video; corre kcut edl check")
        first = ms_to_f_round(clip.video.start_ms, fps)
        w, h = _size(clip, use, cfg.output.w, cfg.output.h)
        chain = video_chain(clip.video, w, h, fps)
        for start, end, need in _ranges(sorted(use.frames), fps, first, clip.frames):
            name = f"{clip_id}_{start}-{end}_{w}x{h}_{CHAIN_VERSION}.mp4"
            path = f"{MEZZ_REL}/{name}"
            jobs.append(MezzJob(clip_id, start, end, w, h, chain, path, need))
    return jobs


def ensure_mezz(
    project: Project,
    jobs: list[MezzJob],
    progress: Progress | None = None,
    *,
    inv: Inventory | None = None,
    log: Path | None = None,
    notices: list[Notice] | None = None,
) -> MezzIndex:
    """Make the mezzanines of `jobs` that are not already there and return where all of them are.

    A file is reused only if its sidecar says it is fresh and its video reaches what the job
    reads, `need_end_f` (`mezz_files.find_fresh`); one that already holds the whole range, with
    the same size and chain, is as good as one made for it (001.26).
    `.kcut/mezz/` is listed once, whatever the number of jobs. A corrupt sidecar adds a
    `cache_rebuilt` notice and the file is made again; a stale or missing one is made again.
    Each file is written to `<name>.<pid>.partial.mp4`, moved into place, and its sidecar written
    after it."""
    inventory = inv if inv is not None else load_inventory(project, log)
    fps = project.config.output.fps
    folder = resolve_in_project(project.root, MEZZ_REL)  # once, not for each job
    listed = list_mezz(folder)
    index = MezzIndex()
    for done, job in enumerate(jobs, start=1):
        clip = inventory.by_id(job.clip_id)
        if clip is None:
            raise ProjectError(
                f"el clip {job.clip_id} ya no está en el inventario; corre kcut ingest"
            )
        if Path(job.path).parent.as_posix() != MEZZ_REL:
            raise InternalError(f"el mezzanine {job.path} no va en {MEZZ_REL}/")
        entry, rebuild = find_fresh(folder, job, clip, fps, listed.get(job.clip_id, ()))
        if entry is None:
            if rebuild and notices is not None:
                detail = f"{Path(job.path).name}: el sidecar estaba dañado y se reconstruye"
                notices.append(Notice("cache_rebuilt", detail))
            entry = build_mezz(project, job, clip, fps, log)
            index.built += 1
        else:
            index.reused += 1
        index.entries.setdefault(job.clip_id, []).append(entry)
        if progress is not None:
            progress.update(done)
    for entries in index.entries.values():
        entries.sort(key=lambda e: e.start_f)
    return index


def _uses(edl: Edl, inv: Inventory) -> dict[str, _Use]:
    index = VoiceIndex(edl)
    uses: dict[str, _Use] = {}
    for span in edl.spans:
        src = span_src(span)
        if src is None:
            continue
        use = uses.setdefault(src, _Use())
        use.frames.update(span_source_frames(edl, span, inv, index))
        if isinstance(span, CamSpan):
            use.zoom_max = max(use.zoom_max, span.zoom * (1 + span.push))
            use.as_picture = True
        elif isinstance(span, BrollSpan):
            use.zoom_max = max(use.zoom_max, 1 + span.push)
            use.as_picture = True
        elif isinstance(span, ScreenSpan):
            use.as_screen = True
    return uses


def _size(clip: Clip, use: _Use, out_w: int, out_h: int) -> tuple[int, int]:
    video = clip.video
    if video is None:
        raise ProjectError(f"el clip {clip.id} no tiene video")
    sw, sh = video.display_w, video.display_h
    scales: list[float] = []
    if use.as_picture:
        base_h = cover_box(sw, sh, out_w, out_h)[1]
        scales.append(min(1.0, out_h * max(1.0, use.zoom_max) / base_h))
    if use.as_screen:
        scales.append(min(1.0, SCREEN_LONG_SIDE / max(sw, sh)))
    scale = max(scales) if scales else 1.0
    return max(2, 2 * round(sw * scale / 2)), max(2, 2 * round(sh * scale / 2))


def _ranges(
    frames: list[int], fps: int, first: int, total: int | None
) -> list[tuple[int, int, int]]:
    """`(a, b, need)` for each `[a, b)` range that holds every frame of `frames` (sorted, no
    repeats): `need` is one more than the last of those frames in it, without the margin."""
    runs: list[list[int]] = []
    for f in frames:
        if runs and f - runs[-1][1] < MERGE_GAP_FACTOR * fps:
            runs[-1][1] = f + 1
        else:
            runs.append([f, f + 1])
    margin = fps // 2
    merged: list[list[int]] = []
    for a, b in runs:
        need = b
        a = max(first, a - margin)
        b = b + margin if total is None else min(total, b + margin)
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2] = max(merged[-1][2], need)
        else:
            merged.append([a, b, need])
    return [(a, b, need) for a, b, need in merged]
