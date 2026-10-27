"""Make the graphics layer of a video, or reuse the one that is there (spec S1.6b).

`ensure_layer` is what `kcut render` and `kcut graphics capture` share: the page for the video
(with the raw text of the subtitles: this one goes into the MP4, 001.13 point 6), its hash, and
Chromium only if the hash is not the one in `index.json`. The folder of the build has already been
checked by the caller, and it is checked again here before each thing that is written in it
(`folder_guard`, 001.31 point 2): the capture takes minutes, and `gfx/` can be changed for a
junction in the meantime.

Also here, for the same two commands: the room that the layer asks of the disk (`layer_bytes`,
`require_layer_space`; 001.31 point 5).
"""

import os
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from kcut.audio.voice_track import SPARE_BYTES
from kcut.console import Out, Progress
from kcut.errors import CheckFailed, GateError, ProjectError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.capture import Guard
from kcut.gfx.capture_index import INDEX_NAME, index_document, load_index, page_hash
from kcut.gfx.page import build_page
from kcut.gfx.resolve import ResolvedGraphics, data_json
from kcut.ingest.cache_guard import assert_in_cache, assert_own_folder
from kcut.ingest.inventory import Notice
from kcut.issues import exit_code, issue_json
from kcut.jsonio import write_json_atomic
from kcut.project import Project

GFX_DIR = "gfx"
GFX_FRAME_BYTES = 192 * 1024  # what the PNG of a frame that is drawn may weigh, with room to spare
MAX_NAMED = 5  # errors that are printed when the graphics are refused
GATE_EXIT = 5  # what `exit_code` says for a G10: a resource that nobody approved
_FRAME_PNG = re.compile(r"[0-9]{6}\.png")


@dataclass(frozen=True)
class Layer:
    """The graphics of a video, ready to blend: `index_path` is its `index.json`, `frames` how
    many frames have something drawn and `captured` is false if the ones of the cache were used."""

    index_path: Path
    frames: int
    captured: bool


def page_for(resolved: ResolvedGraphics, *, masked: bool) -> str:
    """The HTML page of `resolved`, with the components its cues use (`captions` included)."""
    data = data_json(resolved, masked=masked)
    cues = data["cues"]
    ids = [str(cue["component"]) for cue in cues] if isinstance(cues, list) else []
    return build_page(data, ids)


def folder_guard(project: Project, *folders: Path) -> Guard:
    """A check of `folders` (outermost first) with `assert_own_folder`: a function that raises a
    ProjectError if any of them is not a real folder of the cache any more. It is what the capture
    calls before each thing that it writes (001.31, point 2)."""

    def check() -> None:
        for folder in folders:
            assert_own_folder(project, folder)

    return check


def layer_bytes(
    project: Project, resolved: ResolvedGraphics, build_dir: Path, *, force: bool
) -> int:
    """The room that capturing the layer asks of the disk: `GFX_FRAME_BYTES` for each frame that
    is going to be drawn (`active_frames`), and 0 if there is nothing to draw or if the layer of
    the cache is reused: the same page and an index that is valid, as `ensure_layer` decides
    (`force` captures anyway). 001.31, point 5."""
    if resolved.empty:
        return 0
    frames = len(gfx_capture.active_frames(resolved))
    if frames == 0:
        return 0
    if not force:
        folder = build_dir / GFX_DIR
        folder_guard(project, build_dir, folder)()
        index, _ = load_index(folder, resolved.fps, resolved.frames)
        if index is not None and index.hash == page_hash(page_for(resolved, masked=False)):
            return 0
    return frames * GFX_FRAME_BYTES


def require_layer_space(folder: Path, layer: int) -> None:
    """ProjectError, which says how many bytes are missing, unless the disk of `folder` has room
    for `layer` bytes of graphics and `SPARE_BYTES` more. Nothing is asked if there is no layer to
    make (`layer` is 0): nothing is going to be written. The figures go before the path
    (001.30, point 4), as in `voice_track.require_disk_space`."""
    if layer <= 0:
        return
    needed = layer + SPARE_BYTES
    free = shutil.disk_usage(folder).free
    if free < needed:
        raise ProjectError(
            f"no hay espacio en el disco: faltan {needed - free} bytes (la capa de gráficos y "
            f"1 GiB libre piden {needed}, hay {free}) en {folder}"
        )


def ensure_layer(
    project: Project,
    resolved: ResolvedGraphics,
    build_dir: Path,
    *,
    force: bool,
    notices: list[Notice],
) -> Layer | None:
    """Capture the graphics of `resolved` into `build_dir/gfx/` unless the index there is valid
    and has the hash of this page (`force` captures anyway). `None` if there is nothing to draw
    (`resolved.empty`): Chromium is not started and `index.json` is not written.

    An index that was there and fails its checks (`load_index`) is rebuilt with a `cache_rebuilt`
    notice. The old index and the old PNGs go before the new capture starts, so a capture that
    fails half way never leaves an index that describes something else."""
    if resolved.empty:
        return None
    folder = build_dir / GFX_DIR
    index_path = folder / INDEX_NAME
    guard = folder_guard(project, build_dir, folder)
    guard()
    assert_in_cache(project, index_path)
    page = page_for(resolved, masked=False)
    digest = page_hash(page)
    if not force:
        index, damaged = load_index(folder, resolved.fps, resolved.frames)
        if index is not None and index.hash == digest:
            return Layer(index_path, len(index.frames), False)
        if damaged:
            detail = "gráficos: el índice de la caché estaba dañado y se recaptura"
            notices.append(Notice("cache_rebuilt", detail))
    guard()
    folder.mkdir(parents=True, exist_ok=True)
    _clear(guard, folder)
    wanted = gfx_capture.active_frames(resolved)
    kept: list[int] = []
    if wanted:  # Chromium is only started for frames that may have something drawn
        progress = Progress(f"gráficos v{resolved.version}", len(wanted), "frames")
        size = (resolved.w, resolved.h)
        kept = gfx_capture.capture(
            page, folder, wanted, resolved.fps, size, folder, progress, guard=guard
        )
        progress.close()
    guard()
    write_json_atomic(index_path, index_document(resolved.fps, kept, digest))
    return Layer(index_path, len(kept), True)


def raise_for_errors(out: Out, resolved: ResolvedGraphics) -> None:
    """Stop before anything is rendered or captured if the graphics have errors: the first ones
    are printed and the exit is the one of `graphics check` (`exit_code`: 1, or 5 with a G10)."""
    errors = [issue for issue in resolved.issues if issue.level == "error"]
    if not errors:
        return
    for issue in errors[:MAX_NAMED]:
        where = f" {issue.path}" if issue.path else ""
        out.line("ERROR", f"{issue.code}{where}: {issue.message_es}")
    named = ", ".join(sorted({issue.code for issue in errors}))
    message = (
        f"los gráficos tienen {len(errors)} errores ({named}); "
        "corre kcut graphics check y corrígelos"
    )
    if exit_code(errors) == GATE_EXIT:
        raise GateError(message)
    raise CheckFailed(message)


def warnings_json(resolved: ResolvedGraphics) -> list[dict[str, str]]:
    """The warnings of the graphics for `--json`: the issues of level warning, then the notices
    of the run (`pii_unmasked`, `cache_rebuilt`), as `graphics check` lists them."""
    found = [issue_json(i) for i in resolved.issues if i.level == "warning"]
    return found + [{"code": n.code, "path": "", "message": n.detail} for n in resolved.notices]


def _clear(guard: Guard, folder: Path) -> None:
    """Delete `index.json` and the PNGs of the frames in `folder` (not the folders in it, such as
    `stills`). Only the names are removed, links included: nothing is followed. The folder is
    checked before the list and again right before each `unlink` (001.32, point 8): `index.json`
    goes last, and a junction put in `gfx/` before it would have it deleted through the link."""
    guard()
    try:
        names = [entry for entry in folder.iterdir() if _is_stale(entry)]
        for entry in names:
            guard()
            entry.unlink()
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        raise ProjectError(f"no pude borrar los gráficos viejos de la caché: {reason}") from None


def _is_stale(entry: Path) -> bool:
    """Is `entry` the index or the PNG of a frame, and not a folder?"""
    if entry.name != INDEX_NAME and _FRAME_PNG.fullmatch(entry.name) is None:
        return False
    return not stat.S_ISDIR(os.lstat(entry).st_mode)
