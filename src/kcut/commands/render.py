"""kcut render: the cut as a video to review, with the voice as it was recorded (spec S1.5b).

Order: the lock of the output, the gate of the strategy (exit 5), the check of the EDL (exit 1), the
mezzanines, the picture (`.kcut/build/vN/video.mp4`), the voice (`voice_raw.f32`) and the mux
(`render.mp4`). It does not add graphics, SFX, music or loudness: that is `kcut build` (S1.9b).
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import NoReturn

from kcut import proc
from kcut.audio.voice_track import require_disk_space, write_voice
from kcut.console import Out, Progress
from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.edl.gate import strategy_approved
from kcut.edl.model import Edl
from kcut.errors import CheckFailed, GateError, ProjectError
from kcut.ingest import workfiles
from kcut.ingest.inventory import Inventory, Notice
from kcut.issues import Issue
from kcut.jsonio import refuse_directory
from kcut.paths import to_rel
from kcut.pipeline.mux import mux_args
from kcut.project import Project, load_inventory, open_project
from kcut.render.compose import compose_video
from kcut.render.lock import OutputLock, atomic_replace, discard_partial, prepare_partial
from kcut.render.mezz import MezzIndex, ensure_mezz, plan_mezz

NAME = "render"
HELP_ES = "Renderiza el corte (cámaras, looks, pantalla) con la voz cruda, para revisarlo"
_MUX_TIMEOUT_S = 600.0
_MAX_NAMED = 5  # findings of the check that are printed when a render is refused
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
        help="sin la capa de gráficos (hasta S1.6b no cambia nada: aún no hay gráficos)",
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
            _refuse(out, rel, errors)
        edl = checked.edl
        folder = _build_folder(project, version)
        folder.mkdir(parents=True, exist_ok=True)
        for name in _DESTINATIONS:  # a folder there is told now, not after minutes of render
            refuse_directory(folder / name)
        require_disk_space(folder, edl)
        index = _mezzanines(project, edl, inventory, version, log, notices)
        video, raw, render = folder / "video.mp4", folder / "voice_raw.f32", folder / "render.mp4"
        frames = _picture(project, edl, inventory, index, video, version, log)
        workfiles._assert_in_cache(project, raw)
        write_voice(project, edl, inventory, raw, log)
        _mux(project, video, raw, render, log)
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


def _refuse(out: Out, rel: str, errors: list[Issue]) -> NoReturn:
    """The EDL has errors: print the first ones and stop with exit 1, before any frame is made."""
    for issue in errors[:_MAX_NAMED]:
        out.line("ERROR", f"{issue.code} {issue.path}: {issue.message_es}")
    named = ", ".join(sorted({issue.code for issue in errors}))
    raise CheckFailed(
        f"{rel} tiene {len(errors)} errores ({named}); corre kcut edl check y corrígelos"
    )


def _build_folder(project: Project, version: int) -> Path:
    """`.kcut/build/vN`, after it was seen to be a real folder of the cache and not a symlink or
    a junction to somewhere else, even somewhere inside `.kcut/` (`build/v7 -> .kcut/` would make
    the render write `video.mp4` in the root of the cache): it has to resolve to itself. A
    ProjectError before anything is written there (001.26, point 10)."""
    folder = project.layout.build_dir(version)
    workfiles._assert_in_cache(project, folder)
    if os.path.lexists(folder):
        itself = project.layout.build.resolve() / folder.name
        linked = os.path.islink(folder) or os.path.isjunction(folder)
        if linked or os.path.normcase(str(folder.resolve())) != os.path.normcase(str(itself)):
            raise ProjectError(
                f"{folder} es un enlace (symlink o junction) o no resuelve a sí misma: "
                "kcut no renderiza ahí; reemplázala por una carpeta de verdad"
            )
    return folder


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
) -> int:
    """The picture to `video.partial.mp4` and then to `video.mp4`; the partial is never left."""
    partial = video.with_name("video.partial.mp4")
    for path in (partial, video):
        workfiles._assert_in_cache(project, path)
    refuse_directory(video)  # a folder there is told now, not after the frames are made
    progress = Progress(f"render v{version}", edl.frames, "frames")
    try:
        prepare_partial(partial)
        frames = compose_video(project, edl, inventory, index, partial, None, progress, log=log)
        progress.close()
        atomic_replace(partial, video)
    finally:
        discard_partial(partial)
    return frames


def _mux(project: Project, video: Path, raw: Path, render: Path, log: Path | None) -> None:
    """The picture copied and the raw voice as AAC 192k stereo, to `render.mp4`."""
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
