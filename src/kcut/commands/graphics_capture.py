"""kcut graphics capture and still (spec S1.6b): the graphics of the video drawn with Chromium.

`capture` makes the transparent PNGs that `kcut render` blends over the picture (the render does
it first; here it can be run alone). `still` makes a PNG of the frames that are asked for, to look
at: the graphics over the frame of the cut made from the proxy, or with `--alpha` the graphics
alone. What `still` makes is read by Claude, so its page carries the subtitles masked (001.15 T2)
and its files go through `assert_writable` when they are written outside `.kcut/`.

Both take the lock `build-vN` (they use `gfx/` of that build, as `render` does), and the folders of
`gfx/` and each target are looked at again before each file is written (001.31, points 2 and 5).
"""

from __future__ import annotations

import argparse
import contextlib
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from kcut.commands.refuse import refuse_edl
from kcut.console import Out, Progress
from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.edl.model import Edl
from kcut.errors import ToolError, UsageError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.layer import (
    GFX_DIR,
    ensure_layer,
    folder_guard,
    layer_bytes,
    page_for,
    raise_for_errors,
    require_layer_space,
    warnings_json,
)
from kcut.gfx.overlay import alpha_blend
from kcut.gfx.resolve import ResolvedGraphics, resolve
from kcut.ingest.cache_guard import assert_in_cache, build_folder
from kcut.ingest.inventory import Inventory
from kcut.jsonio import write_bytes_atomic
from kcut.paths import to_rel
from kcut.project import Project, assert_writable, load_inventory, open_project, under_kcut
from kcut.render.frame_fx import FxContext, fx_context
from kcut.render.lock import OutputLock
from kcut.render.preview import base_frame

STILLS = "stills"  # `.kcut/build/vN/gfx/stills/`: where a still goes if `--out` is not given
STILLS_WORK = "stills_work"  # the page of the stills and the PNGs as Chromium made them
MAX_STILLS = 60  # different frames that one call of `still` makes
Frame = NDArray[np.uint8]


def run_capture(args: argparse.Namespace) -> int:
    """`kcut graphics capture [--edl EDL] [--force]`, under the lock `build-vN` that `render`,
    `mix` and `build` share. With nothing to draw it does not start Chromium and writes nothing."""
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    log = getattr(args, "log", None)
    inventory = load_inventory(project, log)
    rel, version = find_edl(project, args.edl)
    lock_name = f"build-v{version}"
    assert_in_cache(project, project.layout.locks / f"{lock_name}.lock")
    with OutputLock(project.layout.locks, lock_name):
        edl = _checked_edl(out, project, inventory, rel)
        resolved = _resolved(out, project, edl, version, inventory, log)
        folder = build_folder(project, version)
        folder.mkdir(parents=True, exist_ok=True)
        # the room for the PNGs of the layer, if there is a layer to make (001.31, point 5)
        require_layer_space(folder, layer_bytes(project, resolved, folder, force=args.force))
        layer = ensure_layer(project, resolved, folder, force=args.force, notices=resolved.notices)
    _warn(out, resolved)
    index = None if layer is None else to_rel(project.root, layer.index_path)
    if layer is None:
        out.line("INFO", f"{rel}: no hay nada que dibujar; no se captura nada")
    else:
        what = "capturados" if layer.captured else "ya estaban en la caché"
        out.line("OK", f"{index}: {layer.frames} frames {what}")
    out.result(
        {
            "ok": True,
            "edl": rel,
            "frames": 0 if layer is None else layer.frames,
            "captured": layer is not None and layer.captured,
            "index": index,
            "warnings": warnings_json(resolved),
        }
    )
    return 0


def run_still(args: argparse.Namespace) -> int:
    """`kcut graphics still <f>... [--edl EDL] [--out DIR] [--alpha]`: `still_<f:06d>.png` for
    each frame (at most `MAX_STILLS` different ones), in `--out` or in
    `.kcut/build/vN/gfx/stills/`, under the lock `build-vN`. Every target is checked before the
    first frame is made."""
    out = Out(json_mode=args.json)
    frames = list(dict.fromkeys(args.frames))  # a frame that is asked for twice is made once
    if len(frames) > MAX_STILLS:
        raise UsageError(f"graphics still hace hasta {MAX_STILLS} frames por llamada; pide menos")
    project = open_project(args.project)
    log = getattr(args, "log", None)
    inventory = load_inventory(project, log)
    rel, version = find_edl(project, args.edl)
    lock_name = f"build-v{version}"
    assert_in_cache(project, project.layout.locks / f"{lock_name}.lock")
    with OutputLock(project.layout.locks, lock_name):
        edl = _checked_edl(out, project, inventory, rel)
        for f in frames:
            if not 0 <= f < edl.frames:
                raise UsageError(f"el frame {f} está fuera del video: va de 0 a {edl.frames - 1}")
        build = build_folder(project, version)
        for f in frames:
            _target(project, version, args.out, f)  # all of them, before the first frame is made
        resolved = _resolved(out, project, edl, version, inventory, log)
        made = _make_stills(
            out, project, edl, inventory, resolved, build, version, frames, args, log
        )
    _warn(out, resolved)
    out.result(
        {"ok": True, "stills": made, "alpha": bool(args.alpha), "warnings": warnings_json(resolved)}
    )
    return 0


def _make_stills(
    out: Out,
    project: Project,
    edl: Edl,
    inventory: Inventory,
    resolved: ResolvedGraphics,
    build: Path,
    version: int,
    frames: list[int],
    args: argparse.Namespace,
    log: Path | None,
) -> list[dict[str, object]]:
    """Chromium's PNG of each frame in `gfx/stills_work/` (nothing, if there is nothing to draw),
    and from it the still of each frame. The folders of `gfx/` are checked before they are made and
    before each PNG (`folder_guard`), and each target again before each still."""
    gfx = build / GFX_DIR
    work_guard = folder_guard(project, build, gfx, gfx / STILLS_WORK)
    stills_guard = folder_guard(project, build, gfx, gfx / STILLS)
    if args.out is None:
        stills_guard()  # `gfx/stills/` that is a link or a file is told before Chromium starts
    ctx = fx_context(project, edl)
    shots: dict[int, Path] = {}
    if not resolved.empty:
        progress = Progress("graphics still", len(frames), "frames")
        page = page_for(resolved, masked=True)  # the subtitles as Claude may read them
        size = (edl.out_w, edl.out_h)
        work = gfx / STILLS_WORK
        shots = gfx_capture.capture_stills(
            page, work, frames, edl.fps, size, work, progress, guard=work_guard
        )
        progress.close()
    made: list[dict[str, object]] = []
    for f in frames:
        data = _still(project, edl, inventory, f, shots.get(f), args.alpha, ctx, log)
        target = _target(project, version, args.out, f)  # looked at again before each still
        if args.out is None:
            stills_guard()
        write_bytes_atomic(target, data)
        made.append({"f": f, "png": to_rel(project.root, target)})
        out.line("OK", str(made[-1]["png"]))
    if shots:
        work_guard()
    for shot in shots.values():  # what Chromium made is not kept: the still is
        with contextlib.suppress(OSError):
            shot.unlink()
    return made


def _checked_edl(out: Out, project: Project, inventory: Inventory, rel: str) -> Edl:
    """The EDL, judged as every command of graphics does first (`check_edl_file`): with errors it
    stops with exit 1 and those errors, and nothing else is resolved."""
    checked = check_edl_file(project, inventory, rel)
    errors = [issue for issue in checked.issues if issue.level == "error"]
    if errors or checked.edl is None:
        refuse_edl(out, checked.rel, errors)
    return checked.edl


def _resolved(
    out: Out,
    project: Project,
    edl: Edl,
    version: int,
    inventory: Inventory,
    log: Path | None,
) -> ResolvedGraphics:
    """The graphics of `edl` (the file, or the implicit document), or exit 1 / 5 with errors."""
    resolved = resolve(project, edl, version, inventory=inventory, log=log)
    raise_for_errors(out, resolved)
    return resolved


def _warn(out: Out, resolved: ResolvedGraphics) -> None:
    """The warnings and the notices of the graphics, one line each on stderr."""
    for item in warnings_json(resolved):
        where = f" {item['path']}" if item["path"] else ""
        out.warn(f"{item['code']}{where}: {item['message']}")


def _target(project: Project, version: int, out_dir: str | None, f: int) -> Path:
    """Where the still of frame `f` goes: `<out_dir>/still_<f>.png` (checked by `assert_writable`)
    or, without `--out`, `.kcut/build/vN/gfx/stills/` (checked by the guard of the cache).

    An `--out` that is inside `.kcut/` is a UsageError (001.31, point 9): `assert_writable` replaces
    a file that is there under `.kcut/`, so `--out .kcut/transcripts` would write next to the
    transcripts. The name of a still is fixed, so one outside `.kcut/` replaces the one before."""
    name = f"still_{f:06d}.png"
    if out_dir is None:
        folder = project.layout.build_dir(version) / GFX_DIR / STILLS
        return assert_in_cache(project, folder / name)
    folder_rel = out_dir.replace("\\", "/").rstrip("/")
    target = assert_writable(project, f"{folder_rel}/{name}")
    if under_kcut(project, target):
        raise UsageError(
            "--out no puede ir dentro de .kcut/; "
            "sin --out los stills van a .kcut/build/vN/gfx/stills/"
        )
    return target


def _still(
    project: Project,
    edl: Edl,
    inventory: Inventory,
    f: int,
    shot: Path | None,
    alpha: bool,
    ctx: FxContext,
    log: Path | None,
) -> bytes:
    """The PNG of the still of frame `f`. `shot` is what Chromium made for it, `None` if there is
    nothing to draw. With `alpha` it is that PNG as it is (RGBA); without, the graphics blended
    over `base_frame`, as an RGB PNG of the size of the video."""
    if alpha:
        return _transparent(edl) if shot is None else shot.read_bytes()
    base = base_frame(project, edl, inventory, f, ctx, log=log)
    if shot is None:
        return _png(base)
    bgra = cv2.imdecode(np.frombuffer(shot.read_bytes(), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if bgra is None or bgra.dtype != np.uint8 or bgra.shape != (edl.out_h, edl.out_w, 4):
        raise ToolError("Chromium no entregó un PNG con alfa del tamaño del video")
    return _png(alpha_blend(base, np.asarray(bgra)))


def _transparent(edl: Edl) -> bytes:
    """An RGBA PNG of the size of the video with alpha 0 everywhere: no graphics in a still."""
    return _png(np.zeros((edl.out_h, edl.out_w, 4), dtype=np.uint8))


def _png(picture: Frame) -> bytes:
    """`picture` (BGR or BGRA) as the bytes of a PNG, encoded in memory (never `cv2.imwrite`)."""
    done, encoded = cv2.imencode(".png", picture)
    if not done:
        raise ToolError("no pude codificar el PNG del still")
    return bytes(encoded.tobytes())
