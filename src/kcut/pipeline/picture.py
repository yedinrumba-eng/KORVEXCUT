"""The picture steps that `kcut render` and `kcut build` share (spec S1.5b, S1.9b; 001.51 point 6).

The graphics (`edit/graphics.json`, or the subtitles of the transcript if there is none; errors in
them stop everything before anything is rendered: exit 1, 5 for a G10), the layer of PNGs, the
mezzanines, the picture with the layer over it (`.kcut/build/vN/video.mp4`) and the mux of the
picture with a sound into a final file. `kcut render` joins the raw voice, `kcut build` the mix.

They live here, and not in `commands/`, because a module outside `commands/` cannot import a command
(`tests/unit/test_layers.py`) and each command used to have its own copy. What is not here is what
each command does around them: the five destinations of `render` looked at before the work, the
count of the disk and the order of the checks.
"""

from collections.abc import Callable
from pathlib import Path

from kcut import proc
from kcut.console import Out, Progress
from kcut.edl.model import Edl
from kcut.gfx.layer import Layer, ensure_layer, folder_guard, raise_for_errors
from kcut.gfx.overlay import OverlaySource
from kcut.gfx.resolve import ResolvedGraphics, resolve
from kcut.ingest.cache_guard import assert_in_cache, build_folder
from kcut.ingest.inventory import Inventory, Notice
from kcut.jsonio import refuse_directory
from kcut.pipeline.mux import mux_args
from kcut.project import Project
from kcut.render.compose import compose_video
from kcut.render.lock import atomic_replace, discard_partial, prepare_partial
from kcut.render.mezz import MezzIndex, ensure_mezz, plan_mezz

MUX_TIMEOUT_S = 600.0  # the most that the ffmpeg of a mux may take


def resolve_graphics(
    out: Out, project: Project, edl: Edl, version: int, inventory: Inventory, log: Path | None
) -> ResolvedGraphics:
    """The graphics of `edl` (the file, or the implicit document), or exit 1 / 5 with errors; its
    warnings are printed."""
    resolved = resolve(project, edl, version, inventory=inventory, log=log)
    raise_for_errors(out, resolved)
    for issue in resolved.issues:
        where = f" {issue.path}" if issue.path else ""
        out.warn(f"{issue.code}{where}: {issue.message_es}")
    return resolved


def make_video(
    project: Project,
    edl: Edl,
    version: int,
    resolved: ResolvedGraphics | None,
    inventory: Inventory,
    notices: list[Notice],
    log: Path | None,
) -> tuple[Path, int, MezzIndex]:
    """`.kcut/build/vN/video.mp4` (the picture with the graphics over it, if there are `resolved`
    graphics to draw: `None` is `render --no-graphics`), its frame count and the mezzanines."""
    folder = build_folder(project, version)
    layer = None if resolved is None else make_layer(project, resolved, folder, version, notices)
    index = make_mezzanines(project, edl, inventory, version, log, notices)
    overlay = overlay_of(project, edl, folder, layer)
    video = folder / "video.mp4"
    frames = make_picture(project, edl, inventory, index, video, version, log, overlay)
    return video, frames, index


def make_layer(
    project: Project,
    resolved: ResolvedGraphics,
    folder: Path,
    version: int,
    notices: list[Notice],
) -> Layer | None:
    """The PNGs of the graphics: captured with Chromium, or those of the cache if the page did not
    change. `None` if there is nothing to draw (Chromium is not started then)."""
    notices.extend(resolved.notices)
    build_folder(project, version)  # looked at again before the first write (001.27, point 4)
    return ensure_layer(project, resolved, folder, force=False, notices=notices)


def make_mezzanines(
    project: Project,
    edl: Edl,
    inventory: Inventory,
    version: int,
    log: Path | None,
    notices: list[Notice],
) -> MezzIndex:
    """Plan and make the mezzanines, with their own progress line."""
    jobs = plan_mezz(edl, inventory, project.config)
    progress = Progress(f"mezzanines v{version}", len(jobs), "rangos")
    index = ensure_mezz(project, jobs, progress, inv=inventory, log=log, notices=notices)
    progress.close()
    return index


def overlay_of(
    project: Project, edl: Edl, folder: Path, layer: Layer | None
) -> OverlaySource | None:
    """The source of the PNGs of the layer, if there is one; each PNG is read minutes from now, so
    its folders are looked at then (the guard, and the identities of the folders)."""
    if layer is None:
        return None
    gfx = layer.index_path.parent
    guard = folder_guard(project, folder, gfx)  # the whole check, once (001.35, point 6)
    watch = (project.layout.cache, project.layout.build, folder, gfx)  # their identities
    return OverlaySource(layer.index_path, edl.out_w, edl.out_h, guard=guard, watch=watch)


def make_picture(
    project: Project,
    edl: Edl,
    inventory: Inventory,
    index: MezzIndex,
    video: Path,
    version: int,
    log: Path | None,
    overlay: OverlaySource | None,
) -> int:
    """The picture to `video.partial.mp4` and then to `video.mp4`, with the graphics over it if
    there is an `overlay`; the partial is never left."""
    build_folder(project, version)  # looked at again before the first write (001.27, point 4)
    partial = video.with_name("video.partial.mp4")
    for path in (partial, video):
        assert_in_cache(project, path)
    refuse_directory(video)  # a folder there is told now, not after the frames are made
    progress = Progress(f"render v{version}", edl.frames, "frames")
    look = looks(project, version, partial, video)
    try:
        prepare_partial(partial)
        frames = compose_video(project, edl, inventory, index, partial, overlay, progress, log=log)
        progress.close()
        look()  # 001.38, point 2: the frames took minutes; again right before the move
        atomic_replace(partial, video)
    finally:
        discard_partial(partial, look)
    return frames


def looks(project: Project, version: int, *paths: Path) -> Callable[[], None]:
    """The check of `build/vN` and of each of `paths`, as something to call later (001.38, point
    2): a render takes minutes, and the folder can be changed for a link meanwhile. It is called
    right before a partial file is moved over its final name and right before it is deleted."""

    def look() -> None:
        build_folder(project, version)
        for path in paths:
            assert_in_cache(project, path)

    return look


def mux_replace(
    video: Path,
    audio: Path,
    partial: Path,
    final: Path,
    *,
    audio_f32: bool,
    look: Callable[[], None],
    log: Path | None,
    before_replace: Callable[[], None] | None = None,
) -> None:
    """The picture copied and `audio` as AAC 192k stereo (`audio_f32`: the raw float32 of the voice
    track) to `partial`, moved over `final`. `look` is called before the partial is prepared, right
    before the move and right before it is deleted; `before_replace` runs after the ffmpeg and
    before the move, and if it raises the partial goes."""
    try:
        look()
        prepare_partial(partial)
        args = mux_args(proc.tool_path("ffmpeg"), video, audio, partial, audio_f32=audio_f32)
        proc.run(args, log=log, timeout_s=MUX_TIMEOUT_S)
        if before_replace is not None:
            before_replace()
        look()  # 001.38, point 2: the ffmpeg took a while, so again right before the move
        atomic_replace(partial, final)
    finally:
        discard_partial(partial, look)
