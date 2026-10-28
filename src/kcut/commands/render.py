"""kcut render: the cut as a video to review, with the voice as it was recorded (spec S1.5b).

Order: the lock of the output, the gate of the strategy (exit 5), the check of the EDL (exit 1), the
graphics (S1.6b: `edit/graphics.json`, or the subtitles of the transcript if there is none; errors
in them are exit 1 before anything is made), the mezzanines, the picture with the graphics over it
(`.kcut/build/vN/video.mp4`), the voice (`voice_raw.f32`) and the mux (`render.mp4`). It does not
add SFX, music or loudness: that is `kcut build` (S1.9b).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from kcut import proc
from kcut.audio.voice_track import require_disk_space, write_voice
from kcut.commands.refuse import refuse_edl
from kcut.console import Out, Progress
from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.edl.gate import strategy_approved
from kcut.edl.model import Edl
from kcut.errors import GateError
from kcut.gfx.layer import Layer, ensure_layer, folder_guard, layer_bytes, raise_for_errors
from kcut.gfx.overlay import OverlaySource
from kcut.gfx.resolve import ResolvedGraphics, resolve
from kcut.ingest import workfiles
from kcut.ingest.cache_guard import build_folder
from kcut.ingest.inventory import Inventory, Notice
from kcut.ingest.partials import sweep_orphan_partials
from kcut.jsonio import refuse_directory
from kcut.logfile import append_log
from kcut.paths import to_rel
from kcut.pipeline.mux import mux_args
from kcut.project import Project, load_inventory, open_project
from kcut.render.compose import compose_video
from kcut.render.lock import OutputLock, atomic_replace, discard_partial, prepare_partial
from kcut.render.mezz import MezzIndex, ensure_mezz, plan_mezz

NAME = "render"
HELP_ES = "Renderiza el corte (cámaras, looks, pantalla) con la voz cruda, para revisarlo"
_MUX_TIMEOUT_S = 600.0
# what the render writes in `.kcut/build/vN/`, and the partial files it writes them through
_DESTINATIONS = (
    "video.mp4",
    "render.mp4",
    "voice_raw.f32",
    "video.partial.mp4",
    "render.partial.mp4",
)


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument(
        "--edl",
        metavar="EDL",
        default=None,
        help="ruta del EDL, relativa al proyecto (por defecto el edit/edl-vN.json de N más alto)",
    )
    sub.add_argument(
        "--no-graphics",
        action="store_true",
        help="sin la capa de gráficos: ni los de edit/graphics.json ni los subtítulos",
    )
    return sub


def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    log = getattr(args, "log", None)
    inventory = load_inventory(project, log)
    rel, version = find_edl(project, args.edl)
    lock_name = f"build-v{version}"
    workfiles._assert_in_cache(project, project.layout.locks / f"{lock_name}.lock")
    notices: list[Notice] = []
    with OutputLock(project.layout.locks, lock_name):
        gate = strategy_approved(project)
        if not gate.approved:
            raise GateError(f"{gate.reason_es}; apruébala antes de renderizar")
        checked = check_edl_file(project, inventory, rel)
        errors = [issue for issue in checked.issues if issue.level == "error"]
        if errors or checked.edl is None:
            refuse_edl(out, rel, errors)
        edl = checked.edl
        folder = build_folder(project, version)
        folder.mkdir(parents=True, exist_ok=True)
        for name in _DESTINATIONS:  # a folder there is told now, not after minutes of render
            refuse_directory(folder / name)
        swept = sweep_orphan_partials(project)  # what a render killed by force left (001.27)
        if swept and log is not None:
            append_log(log, f"[orphan_partials] {swept} archivos parciales huérfanos borrados\n")
        resolved = None
        if not args.no_graphics:
            resolved = _graphics(out, project, edl, version, inventory, log)
        # the voice, and the layer of graphics if there is one to capture (001.31, point 5)
        need = 0 if resolved is None else layer_bytes(project, resolved, folder, force=False)
        require_disk_space(folder, edl, layer_bytes=need)
        layer = None if resolved is None else _layer(project, resolved, folder, version, notices)
        index = _mezzanines(project, edl, inventory, version, log, notices)
        video, raw, render = folder / "video.mp4", folder / "voice_raw.f32", folder / "render.mp4"
        overlay = None
        if layer is not None:  # each PNG is read minutes from now: its folders are looked at then
            guard = folder_guard(project, folder, layer.index_path.parent)
            overlay = OverlaySource(layer.index_path, edl.out_w, edl.out_h, guard=guard)
        frames = _picture(project, edl, inventory, index, video, version, log, overlay)
        build_folder(project, version)  # looked at again before each write (001.27, point 4)
        workfiles._assert_in_cache(project, raw)
        write_voice(project, edl, inventory, raw, log)
        _mux(project, video, raw, render, version, log)
    for item in notices:
        out.warn(f"{item.code}: {item.detail}")
    elapsed = round(time.monotonic() - started, 1)
    out.line("OK", f"{to_rel(project.root, render)}: {frames} frames en {elapsed} s")
    out.result(
        {
            "ok": True,
            "video": to_rel(project.root, video),
            "render": to_rel(project.root, render),
            "frames": frames,
            "mezz_built": index.built,
            "mezz_reused": index.reused,
            "elapsed_s": elapsed,
        }
    )
    return 0


def _graphics(
    out: Out,
    project: Project,
    edl: Edl,
    version: int,
    inventory: Inventory,
    log: Path | None,
) -> ResolvedGraphics:
    """What is drawn over the picture: `edit/graphics.json`, or the implicit document if it is
    not there (subtitles from the transcript, 001.15 point 40). Errors in it are exit 1 (5 for a
    G10) before anything is rendered; its warnings are printed."""
    resolved = resolve(project, edl, version, inventory=inventory, log=log)
    raise_for_errors(out, resolved)
    for issue in resolved.issues:
        where = f" {issue.path}" if issue.path else ""
        out.warn(f"{issue.code}{where}: {issue.message_es}")
    return resolved


def _layer(
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


def _mezzanines(
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


def _picture(
    project: Project,
    edl: Edl,
    inventory: Inventory,
    index: MezzIndex,
    video: Path,
    version: int,
    log: Path | None,
    overlay: OverlaySource | None = None,
) -> int:
    """The picture to `video.partial.mp4` and then to `video.mp4`, with the graphics over it if
    there is an `overlay`; the partial is never left."""
    build_folder(project, version)  # looked at again before the first write (001.27, point 4)
    partial = video.with_name("video.partial.mp4")
    for path in (partial, video):
        workfiles._assert_in_cache(project, path)
    refuse_directory(video)  # a folder there is told now, not after the frames are made
    progress = Progress(f"render v{version}", edl.frames, "frames")
    try:
        prepare_partial(partial)
        frames = compose_video(project, edl, inventory, index, partial, overlay, progress, log=log)
        progress.close()
        atomic_replace(partial, video)
    finally:
        discard_partial(partial)
    return frames


def _mux(
    project: Project, video: Path, raw: Path, render: Path, version: int, log: Path | None
) -> None:
    """The picture copied and the raw voice as AAC 192k stereo, to `render.mp4`."""
    build_folder(project, version)  # looked at again before the first write (001.27, point 4)
    partial = render.with_name("render.partial.mp4")
    for path in (partial, render):
        workfiles._assert_in_cache(project, path)
    refuse_directory(render)
    try:
        prepare_partial(partial)
        args = mux_args(proc.tool_path("ffmpeg"), video, raw, partial, audio_f32=True)
        proc.run(args, log=log, timeout_s=_MUX_TIMEOUT_S)
        atomic_replace(partial, render)
    finally:
        discard_partial(partial)
