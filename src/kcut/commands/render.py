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

from kcut.audio.voice_track import require_disk_space, write_voice
from kcut.console import Out
from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.edl.gate import strategy_approved
from kcut.edl.refuse import refuse_edl
from kcut.errors import GateError
from kcut.gfx.layer import layer_bytes
from kcut.ingest import workfiles
from kcut.ingest.cache_guard import build_folder
from kcut.ingest.inventory import Notice
from kcut.ingest.partials import sweep_orphan_partials
from kcut.jsonio import refuse_directory
from kcut.logfile import append_log
from kcut.paths import to_rel
from kcut.pipeline.picture import looks, make_video, mux_replace, resolve_graphics  # 001.51
from kcut.project import Project, load_inventory, open_project
from kcut.render.lock import OutputLock

NAME = "render"
HELP_ES = "Renderiza el corte (cámaras, looks, pantalla) con la voz cruda, para revisarlo"
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
            resolved = resolve_graphics(out, project, edl, version, inventory, log)
        # the voice, and the layer of graphics if there is one to capture (001.31, point 5)
        need = 0 if resolved is None else layer_bytes(project, resolved, folder, force=False)
        require_disk_space(folder, edl, layer_bytes=need)
        video, frames, index = make_video(project, edl, version, resolved, inventory, notices, log)
        raw, render = folder / "voice_raw.f32", folder / "render.mp4"
        build_folder(project, version)  # looked at again before each write (001.27, point 4)
        workfiles._assert_in_cache(project, raw)
        write_voice(project, edl, inventory, raw, log, guard=looks(project, version, raw))
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


def _mux(
    project: Project, video: Path, raw: Path, render: Path, version: int, log: Path | None
) -> None:
    """The picture copied and the raw voice as AAC 192k stereo, to `render.mp4`."""
    build_folder(project, version)  # looked at again before the first write (001.27, point 4)
    partial = render.with_name("render.partial.mp4")
    for path in (partial, render):
        workfiles._assert_in_cache(project, path)
    refuse_directory(render)
    look = looks(project, version, partial, render)
    mux_replace(video, raw, partial, render, audio_f32=True, look=look, log=log)
