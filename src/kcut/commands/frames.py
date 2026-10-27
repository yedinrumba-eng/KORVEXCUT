"""kcut frames: frames of a clip's proxy as PNG, with a grid and a label (and a sheet of them).

Claude looks at them before it throws a long pause away (lesson 8: there may be a gesture in it).
Times are of the source clock (spec 0.6): frame `f` of the clip is index `f - vs_f` of its proxy
(`ff.reader.proxy_index`), and a frame before the first one of the video, or after the last one
the proxy really has, is a UsageError. Times that fall on the same frame (`90 3s` at 30 fps) are
one frame, so the run does not meet the PNG it has just written (001.22). A frame is never made
wider than the proxy; the sheet has at most 25 Mpx (its cells get narrower), and each frame is
let go as soon as it is pasted.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from kcut.commands.view import png_bytes
from kcut.console import Out
from kcut.errors import UsageError
from kcut.ff.reader import grab, proxy_frame_count, proxy_index
from kcut.ingest import workfiles
from kcut.ingest.inventory import Clip
from kcut.jsonio import write_bytes_atomic
from kcut.paths import to_rel
from kcut.project import Project, assert_writable, load_inventory, open_project, under_kcut
from kcut.render.proxy_file import proxy_of
from kcut.schema_util import describe_value
from kcut.timebase import fmt_s, rdiv
from kcut.timeparse import parse_time
from kcut.viz.draw import text_box
from kcut.viz.grid import SheetBuilder, grid_overlay

NAME = "frames"
HELP_ES = "Guarda frames del proxy de un clip con rejilla y rótulo"
DEFAULT_GRID = 10
DEFAULT_WIDTH = 540
MIN_WIDTH, MAX_WIDTH = 64, 1920
SHEET_COLS = 8
MAX_TIMES = 64  # times in one run: each one starts an ffmpeg
_LABEL_SIZE = 20


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument("clip", help="id del clip (a1, b1...)")
    sub.add_argument(
        "times", nargs="+", metavar="T", help="frames (90), segundos (3s, 2.5s) o mm:ss (1:02)"
    )
    sub.add_argument(
        "--grid",
        type=int,
        default=DEFAULT_GRID,
        metavar="PCT",
        help=f"rejilla cada PCT por ciento, de 1 a 99 (por defecto {DEFAULT_GRID})",
    )
    sub.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WIDTH,
        metavar="PX",
        help=f"ancho de cada PNG, de {MIN_WIDTH} a {MAX_WIDTH}, sin pasar del ancho del proxy "
        f"(por defecto {DEFAULT_WIDTH})",
    )
    sub.add_argument(
        "--out", metavar="DIR", default=None, help="carpeta de salida, relativa al proyecto"
    )
    sub.add_argument(
        "--force", action="store_true", help="pisa los archivos de --out que ya existan"
    )
    return sub


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    log = getattr(args, "log", None)
    fps = project.config.output.fps
    if len(args.times) > MAX_TIMES:
        raise UsageError(
            f"se pidieron {len(args.times)} tiempos; el máximo por corrida es {MAX_TIMES}"
        )
    # times that fall on the same frame are one: the first appearance keeps its place (001.22)
    times = list(dict.fromkeys(parse_time(t, fps) for t in args.times))
    if not MIN_WIDTH <= args.width <= MAX_WIDTH:
        raise UsageError(f"--width va de {MIN_WIDTH} a {MAX_WIDTH} (vino {args.width})")
    if not 1 <= args.grid <= 99:
        raise UsageError(f"--grid va de 1 a 99 (vino {args.grid})")
    clip = load_inventory(project, log).by_id(args.clip)
    if clip is None:
        raise UsageError(f"no existe el clip {describe_value(args.clip)} en el inventario")
    path, size = proxy_of(project, clip)
    _check_frames(clip, times, fps, proxy_frame_count(path, size, log))
    # every target is checked before the first frame is read: a refusal leaves nothing behind
    targets = [_target(project, args, f"{clip.id}_f{f}.png") for f in times]
    sheet_name = f"{clip.id}_sheet_{times[0]}-{times[-1]}.png"
    sheet_target = _target(project, args, sheet_name) if len(times) > 1 else None
    width = min(args.width, size[0])  # never enlarged: the proxy is the sharpest there is
    builder = None
    if sheet_target is not None:
        builder = SheetBuilder(len(times), (width, max(1, rdiv(size[1] * width, size[0]))))
    rels: list[str] = []
    for f, target in zip(times, targets, strict=True):
        label = f"{clip.id} f{f} {fmt_s(f, fps)} s"
        frame = grab(path, proxy_index(clip, f, fps), fps, size, log=log)
        picture = grid_overlay(_scaled(frame, width), args.grid)
        del frame
        corner = (6, picture.height - _LABEL_SIZE - 10)
        text_box(ImageDraw.Draw(picture), corner, label, _LABEL_SIZE, (255, 255, 255), (0, 0, 0))
        write_bytes_atomic(target, png_bytes(picture), replace=_may_replace(project, args, target))
        rels.append(to_rel(project.root, target))
        out.line("OK", rels[-1])
        if builder is not None:
            builder.add(picture, label)  # pasted into the sheet, the frame is let go
        del picture
    if builder is not None and sheet_target is not None:
        sheet = png_bytes(builder.image())
        write_bytes_atomic(sheet_target, sheet, replace=_may_replace(project, args, sheet_target))
        rels.append(to_rel(project.root, sheet_target))
        out.line("OK", rels[-1])
    out.result(
        {
            "ok": True,
            "frames": [{"f": f, "png": rel} for f, rel in zip(times, rels, strict=False)],
            "sheet": rels[-1] if builder is not None else None,
            "width": width,
            "cell_width": builder.cell_width if builder is not None else None,
        }
    )
    return 0


def _check_frames(clip: Clip, times: list[int], fps: int, proxy_frames: int) -> None:
    """Every frame must be in `[vs_f, vs_f + proxy_frames - 1]`: the clock of the source, from the
    first frame of video (`vs_f`, spec 0.6) to the last frame the proxy really holds."""
    first = -proxy_index(clip, 0, fps)  # vs_f
    last = first + proxy_frames - 1
    for f in times:
        if not first <= f <= last:
            raise UsageError(
                f"el frame {f} está fuera del video de {clip.id}: va del {first} al {last}"
            )


def _target(project: Project, args: argparse.Namespace, name: str) -> Path:
    """Where a PNG goes: `<out>/<name>` (checked by `assert_writable`, which does not replace a
    file that is there unless `--force`) or `.kcut/frames/`."""
    if args.out is None:
        return workfiles._assert_in_cache(project, project.layout.frames / name)
    folder = args.out.replace("\\", "/").rstrip("/")
    return assert_writable(project, f"{folder}/{name}", replace=args.force)


def _may_replace(project: Project, args: argparse.Namespace, target: Path) -> bool:
    """May the write replace a file that is there? With `--force`, and always under `.kcut/`. If
    not, a file that appeared after `_target` looked is a UsageError, not overwritten (001.21)."""
    return bool(args.force) or under_kcut(project, target)


def _scaled(frame: NDArray[np.uint8], width: int) -> NDArray[np.uint8]:
    """The BGR frame at `width` pixels (Pillow, LANCZOS), keeping the aspect."""
    if width == frame.shape[1]:
        return frame
    height = max(1, rdiv(frame.shape[0] * width, frame.shape[1]))
    rgb = Image.fromarray(np.ascontiguousarray(frame[:, :, ::-1]))
    resized = rgb.resize((width, height), Image.Resampling.LANCZOS)
    return np.ascontiguousarray(np.asarray(resized)[:, :, ::-1])
