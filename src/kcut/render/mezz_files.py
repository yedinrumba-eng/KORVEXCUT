"""The files of the mezzanines: the ones that exist, which of them can be used and how one is made
(spec S1.5b, DS12, 001.15, 001.25, 001.26).

`.kcut/mezz/` is listed once for each render (`list_mezz`) and each job looks only at the files of
its own clip. A file is used if its sidecar says it is fresh: same clip, chain, range, size, fps,
crf and versions, the same size in bytes as when it was made, and a number of frames that is at
most its range and reaches what the job reads (`need_end_f`). One that holds the whole range of a
job, with the same size and chain, is as good as one made for it.
"""

import os
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from kcut import proc
from kcut.errors import CheckFailed, ProjectError, ToolError
from kcut.ff.args import mezz_args
from kcut.ff.color import CHAIN_VERSION
from kcut.ingest import workfiles
from kcut.ingest.inventory import Clip
from kcut.ingest.sidecar import is_lone_file, wait_to_land
from kcut.jsonio import MAX_SIDECAR_BYTES, read_json, refuse_directory, write_json_exclusive
from kcut.paths import resolve_in_project
from kcut.project import Project
from kcut.render.lock import discard_partial, prepare_partial
from kcut.render.mezz_index import Listed, MezzEntry, MezzIndex, MezzJob

__all__ = [
    "Listed",
    "MezzEntry",
    "MezzIndex",
    "MezzJob",
    "build_mezz",
    "find_fresh",
    "frame_count",
    "list_mezz",
    "params_of",
]
MEZZ_VERSION = 1  # of the layout of a mezzanine and its sidecar; a change of it rebuilds them all
CRF = 14
_NAME = re.compile(
    r"(?P<id>[a-z][0-9]{1,6})_(?P<start>[0-9]+)-(?P<end>[0-9]+)_(?P<w>[0-9]+)x(?P<h>[0-9]+)"
    r"_(?P<chain>[A-Za-z0-9]+)\.mp4"
)
# as `workfiles.job_timeout_s`: ten times the length of what is made, plus 60 s
_TIMEOUT_FACTOR = 10
_PROBE_TIMEOUT_S = 120.0
_OF_THE_FILE = ("size_bytes", "frames")  # what the sidecar says of the mp4 itself


def list_mezz(folder: Path) -> dict[str, list[Listed]]:
    """The mezzanines in `folder`, by clip id, in name order. The folder is read once; a partial
    file (`<name>.<pid>.partial.mp4`) or anything else that is not a mezzanine is left out."""
    found: dict[str, list[Listed]] = {}
    try:
        names = sorted(os.listdir(folder))
    except OSError:  # no folder yet, or something that is not a folder
        return found
    for name in names:
        named = _NAME.fullmatch(name)
        if named is not None:
            item = Listed(
                name,
                int(named["start"]),
                int(named["end"]),
                int(named["w"]),
                int(named["h"]),
                named["chain"],
            )
            found.setdefault(named["id"], []).append(item)
    return found


def params_of(job: MezzJob, start: int, end: int, fps: int) -> dict[str, Any]:
    """What the freshness of a mezzanine of `job`, but with the range `[start, end)`, depends on."""
    return {
        "chain": job.chain,
        "start_f": start,
        "end_f": end,
        "w": job.w,
        "h": job.h,
        "fps": fps,
        "crf": CRF,
        "chain_version": CHAIN_VERSION,
        "mezz_version": MEZZ_VERSION,
    }


def find_fresh(
    folder: Path, job: MezzJob, clip: Clip, fps: int, listed: Sequence[Listed]
) -> tuple[MezzEntry | None, bool]:
    """A fresh file that holds what `job` reads, if there is one (the file of the job itself
    first), and whether the file of the job has a corrupt sidecar (it is made again).

    `folder` is `.kcut/mezz/`, already resolved (once for all the jobs), and `listed` are the
    mezzanines of the clip that `list_mezz` found there."""
    exact = folder / Path(job.path).name
    corrupt = False
    for path, start, end in _candidates(exact, job, listed):
        entry, state = _usable(path, start, end, job, clip, fps)
        if entry is not None:
            return entry, False
        corrupt = corrupt or (path == exact and state == "corrupt")
    return None, corrupt


def _candidates(exact: Path, job: MezzJob, listed: Sequence[Listed]) -> list[tuple[Path, int, int]]:
    """The file of the job, then every other mezzanine of the clip with the same size and chain
    version whose range holds the one of the job: `(path, start_f, end_f)`."""
    found = [(exact, job.start_f, job.end_f)]
    own = _NAME.fullmatch(exact.name)
    if own is None:
        return found
    for item in listed:
        if item.name == exact.name or item.chain != own["chain"]:
            continue
        same_size = (item.w, item.h) == (job.w, job.h)
        holds_it = item.start_f <= job.start_f and job.end_f <= item.end_f
        if same_size and holds_it:
            found.append((exact.with_name(item.name), item.start_f, item.end_f))
    return found


def _usable(
    path: Path, start: int, end: int, job: MezzJob, clip: Clip, fps: int
) -> tuple[MezzEntry | None, workfiles.SidecarState]:
    """The entry of the file `path` (named for `[start, end)`) if it is fresh and its video
    reaches `job.need_end_f`, and what the state of its sidecar is. The range of the entry is the
    one the file really has: `[start, start + frames)` (001.26, point 1)."""
    state, frames = _state(path, clip.qhash, params_of(job, start, end, fps), end - start)
    if state == "fresh" and start + frames >= job.need_end_f:
        return MezzEntry(path, start, start + frames, job.w, job.h), state
    return None, state


def _state(
    path: Path, qhash: str, params: dict[str, Any], longest: int
) -> tuple[workfiles.SidecarState, int]:
    """`workfiles.sidecar_state`, and the frames the file has. The sidecar must also say how many
    bytes and frames the mp4 has: the file must still have those bytes (a file that was swapped,
    cut or written over is `stale`, 001.25 point 9), and the frames are a whole number from 1 to
    `longest`, the length of the range of its name (001.26, point 1). A file that is not a regular
    file with a single link (a hard link to something outside the project, a symlink) is `stale`
    whatever its sidecar says (001.27, point 8)."""
    sidecar = workfiles.sidecar_path(path)
    try:
        if not path.is_file() or not sidecar.is_file():
            return "missing", 0
        if not is_lone_file(path):
            return "stale", 0
        data = read_json(sidecar, MAX_SIDECAR_BYTES)
        size = path.stat().st_size
    except ProjectError:
        return "corrupt", 0
    except OSError:
        return "missing", 0
    if not isinstance(data, dict) or set(data) != {"qhash", "params", *_OF_THE_FILE}:
        return "stale", 0
    fresh = data["qhash"] == qhash and data["params"] == params
    frames = data["frames"]
    # `type(...) is int`: a JSON `true` is not a number of bytes or of frames
    exact = type(data["size_bytes"]) is int and data["size_bytes"] == size
    counted = type(frames) is int and 1 <= frames <= longest
    return ("fresh", frames) if fresh and exact and counted else ("stale", 0)


def build_mezz(project: Project, job: MezzJob, clip: Clip, fps: int, log: Path | None) -> MezzEntry:
    """Run ffmpeg for `job` into `<name>.<pid>.partial.mp4`, count the frames it made, move it
    into place and write its sidecar after it.

    The partial has the pid, so two renders of the same range do not write the same file and each
    one deletes only its own. If the file of the job is fresh when the partial is done (the other
    render came first) that one is used and the partial is thrown away (001.26, point 2). A
    mezzanine whose video ends before what the EDL reads (`need_end_f`) is a CheckFailed, and
    neither the file nor a sidecar is left; one that is shorter than its range but reaches what
    is read is kept, and its sidecar says how many frames it has (001.25 points 7 and 8, 001.26
    point 1)."""
    dst = resolve_in_project(project.root, job.path)
    src = resolve_in_project(project.root, clip.file)
    partial = dst.with_name(f"{dst.stem}.{os.getpid()}.partial{dst.suffix}")
    sidecar = workfiles.sidecar_path(dst)
    for target in (dst, partial, sidecar):
        workfiles._assert_in_cache(project, target)  # before touching the disk
    dst.parent.mkdir(parents=True, exist_ok=True)
    count = job.end_f - job.start_f
    args = mezz_args(proc.tool_path("ffmpeg"), src, partial, job.chain, fps, job.start_f, count)
    try:
        prepare_partial(partial)
        proc.run(args, log=log, timeout_s=_TIMEOUT_FACTOR * count / fps + 60.0)
        if not partial.is_file():
            raise ToolError(f"ffmpeg no produjo {dst.name}")
        made = frame_count(partial, log)
        if job.start_f + made < job.need_end_f:
            raise CheckFailed(
                f"el video de {clip.id} termina en el frame {job.start_f + made}; "
                f"el EDL pide hasta {job.need_end_f}"
            )
        size = partial.stat().st_size
        already = _land(partial, dst, job, clip, fps)
        if already is not None:
            return already
    finally:
        discard_partial(partial)
    params = params_of(job, job.start_f, job.end_f, fps)
    data = {"qhash": clip.qhash, "params": params, "size_bytes": size, "frames": made}
    write_json_exclusive(sidecar, data)  # through `<sidecar>.<pid>.tmp`, created new (001.27)
    return MezzEntry(dst, job.start_f, job.start_f + made, job.w, job.h)


def _land(partial: Path, dst: Path, job: MezzJob, clip: Clip, fps: int) -> MezzEntry | None:
    """Move `partial` over `dst`; None if it was moved. If `dst` is already fresh for the job
    (another process finished it first), or the move is refused because someone has `dst` open
    (on Windows ffmpeg does not share the delete) and it is fresh at that moment, the entry of
    that file, which is as good as ours. A refused move over a file that is not fresh is a
    ProjectError."""
    entry, _ = _usable(dst, job.start_f, job.end_f, job, clip, fps)
    if entry is not None:
        return entry
    refuse_directory(dst)
    try:
        os.replace(partial, dst)
    except PermissionError:
        try:  # waits for the other process, or for the reader to let go (001.29, point 1)
            return wait_to_land(
                partial, dst, lambda: _usable(dst, job.start_f, job.end_f, job, clip, fps)[0]
            )
        except PermissionError:
            raise ProjectError(
                f"otro proceso tiene abierto {dst}; espera a que termine y repite"
            ) from None
    return None


def frame_count(path: Path, log: Path | None) -> int:
    """How many frames the first video stream of `path` has: `nb_frames` of the header of the
    mp4, and if it is not there ffprobe counts them (as `ff.reader.proxy_frame_count`)."""
    ffprobe = str(proc.tool_path("ffprobe"))
    quiet = [ffprobe, "-v", "error", "-select_streams", "v:0", "-of", "default=noprint_wrappers=1"]
    for flags, entry in (([], "nb_frames"), (["-count_frames"], "nb_read_frames")):
        args = [*quiet, *flags, "-show_entries", f"stream={entry}", str(path)]
        text = proc.run(args, log=log, timeout_s=_PROBE_TIMEOUT_S).stdout.decode("ascii", "replace")
        found = dict(line.strip().split("=", 1) for line in text.splitlines() if "=" in line)
        if found.get(entry, "").isdigit():
            return int(found[entry])
    raise ToolError(f"ffprobe no dio el número de frames de {path.name}")
