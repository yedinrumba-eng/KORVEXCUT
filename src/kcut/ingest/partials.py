"""The sweep of orphan partial files in the cache (spec 001.27, point 1).

A render killed by force leaves `<name>.<pid>.partial<ext>` (a mezzanine, a wav, a proxy) and
`<sidecar>.<pid>.tmp` in `.kcut/`, and nobody sweeps them. `kcut render`, `kcut ingest` and (001.37)
`kcut mix` delete the ones that are over a day old. A live render does not take that long, so the
sweep never touches the files of another process; on Windows a file that is open does not let
itself be deleted and is skipped. A link is never followed, and a file with more than one link is
never deleted.
"""

import os
import re
import time
from pathlib import Path

from kcut.errors import ProjectError
from kcut.ingest.cache_guard import assert_in_cache
from kcut.paths import lone_file_reason
from kcut.project import Project

ORPHAN_AGE_S = 86400  # a partial file older than this (24 h) belongs to a process that is gone
_PARTIAL = re.compile(r"^.+\.[0-9]{1,10}\.partial(\.[A-Za-z0-9]{1,8})?$")
_TMP = re.compile(r"^.+\.[0-9]{1,10}\.tmp$")
_BUILD_DIR = re.compile(r"v[0-9]+")  # `Layout.build_dir`: v1, v2...


def sweep_orphan_partials(project: Project, now: float | None = None) -> int:
    """Delete the orphan partial files of `.kcut/mezz`, `.kcut/wav16`, `.kcut/wav48`,
    `.kcut/proxy` and `.kcut/build/vN` (001.37: what a `kcut mix` or a `kcut render` killed by
    force left; their own files only, no subfolder) and return how many were deleted.

    Only a regular file with a single link is deleted (`lone_file_reason`, from `os.lstat`: a
    folder, a symlink, a junction or a hard link stays), whose name is a partial file or a
    temporary of a sidecar with a pid, and whose modification time is more than `ORPHAN_AGE_S`
    before `now` (`time.time()` if it is not given). Whatever cannot be deleted stays, without an
    error: the sweep is a courtesy of the cache and must never stop a render or an ingest."""
    moment = time.time() if now is None else now
    layout = project.layout
    deleted = 0
    for folder in (layout.mezz, layout.wav16, layout.wav48, layout.proxy, *_build_folders(project)):
        deleted += _sweep_folder(project, folder, moment)
    return deleted


def _build_folders(project: Project) -> list[Path]:
    """The `.kcut/build/vN` folders that are real folders (001.37, point 11). A `build` that leads
    out of `.kcut/`, or a `vN` that is a symlink or a junction, is not looked into; neither is
    anything inside them but their own files (`gfx/` is not swept)."""
    build = project.layout.build
    try:
        assert_in_cache(project, build)
        with os.scandir(build) as entries:
            names = sorted(entry.name for entry in entries if _BUILD_DIR.fullmatch(entry.name))
    except (ProjectError, OSError):  # no `build` yet, or not a folder, or out of the cache
        return []
    folders = [build / name for name in names]
    return [f for f in folders if not (os.path.islink(f) or os.path.isjunction(f))]


def _sweep_folder(project: Project, folder: Path, now: float) -> int:
    try:
        assert_in_cache(project, folder)  # a folder that leads out of `.kcut/` is not swept
        with os.scandir(folder) as entries:
            names = [entry.name for entry in entries]
    except (ProjectError, OSError):  # no such folder yet, or not a folder, or not readable
        return 0
    deleted = 0
    for name in names:
        if _is_orphan_name(name) and _delete(project, folder / name, now):
            deleted += 1
    return deleted


def _is_orphan_name(name: str) -> bool:
    return _PARTIAL.fullmatch(name) is not None or _TMP.fullmatch(name) is not None


def _delete(project: Project, path: Path, now: float) -> bool:
    """True if `path` was an old regular file with one link and it was deleted."""
    try:
        info = os.lstat(path)
        if lone_file_reason(info) is not None or now - info.st_mtime <= ORPHAN_AGE_S:
            return False
        assert_in_cache(project, path)
        path.unlink()
    except (ProjectError, OSError):  # in use, read only, gone already, or out of the cache
        return False
    return True
