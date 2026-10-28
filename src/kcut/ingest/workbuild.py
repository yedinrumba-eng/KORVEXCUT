"""Making a work file: ffmpeg into a partial, then the partial over the file and its sidecar next to
it (spec 0.9, 001.26 to 001.33). Split from `workfiles.py` by the 300-line rule (001.33, point 3);
`workfiles` still names `_build`, `_land` and `work_label`, which is what the rest of the code and
the tests call.

The ffmpeg takes minutes, and in that time a folder of the cache can be changed for a junction. So
the target, the partial and the sidecar go through `assert_in_cache` (each one with its `label`)
before the ffmpeg starts and again right before each thing that is written: before `_land`, and
before `land_sidecar`.
"""

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from kcut import proc
from kcut.errors import ProjectError, ToolError
from kcut.ingest.cache_guard import assert_in_cache
from kcut.ingest.sidecar import is_fresh, land_sidecar, sidecar_path, wait_to_land
from kcut.jsonio import refuse_directory
from kcut.project import Project


def work_label(dst: Path) -> str:
    """The phrase that names a work file in a message: its class and its clip (`wav48 de a1`),
    never its name. The name has the slug of the original clip, which may hold a phone number
    (001.28, point 2). The clip is what comes before the first `_` of the name."""
    return f"{dst.parent.name} de {dst.name.split('_', 1)[0]}"


def _look(project: Project, targets: Iterable[Path], label: str) -> None:
    """`assert_in_cache` for each of `targets`, named by `label` in the message."""
    for target in targets:
        assert_in_cache(project, target, label=label)


def _discard(project: Project, partial: Path, label: str) -> None:
    """Delete `partial`, but only if it still passes `assert_in_cache` (001.34, point 3). If the
    folder was changed for a link while the ffmpeg ran, the name is a file of somebody else's
    folder: it stays where it is, and the error that was on its way goes out as it was."""
    try:
        assert_in_cache(project, partial, label=label)
    except ProjectError:
        return
    partial.unlink(missing_ok=True)


def _build(
    project: Project,
    make_args: Callable[[Path], list[str]],
    dst: Path,
    job: tuple[str, dict[str, Any], float],
    log: Path | None,
) -> None:
    """Run ffmpeg into `<name>.<pid>.partial.<ext>`, then replace `dst` and write its sidecar.

    The partial has the pid, so two renders that make the same file do not write the same one and
    each deletes only its own. If `dst` is fresh when the partial is done (the other one came
    first) it is used as it is, and the sidecar is the other's (001.26, point 3). The sidecar goes
    through `<sidecar>.<pid>.tmp`, created new, and is moved like the file, waiting if the other
    render has it open (`land_sidecar`, 001.27 point 5, 001.31 point 1). The three paths are looked
    at before the ffmpeg and again right before `_land` and right before `land_sidecar`, because the
    ffmpeg takes minutes and a folder can change in them (001.33, point 3). The partial is deleted
    at the end only if it is still in the cache (`_discard`, 001.34, point 3)."""
    qhash, params, timeout_s = job
    partial = dst.with_name(f"{dst.stem}.{os.getpid()}.partial{dst.suffix}")
    label = work_label(dst)  # messages name the class and the clip, not the slug (001.30)
    targets = (dst, partial, sidecar_path(dst))
    _look(project, targets, label)  # before touching the disk
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        partial.unlink(missing_ok=True)
        proc.run(make_args(partial), log=log, timeout_s=timeout_s)
        if not partial.is_file():
            raise ToolError(f"ffmpeg no produjo el {work_label(dst)}")
        _look(project, targets, label)  # after the ffmpeg, right before the file is moved
        if not _land(partial, dst, qhash, params):
            return
    finally:
        _discard(project, partial, label)
    _look(project, targets, label)  # right before the sidecar is written
    land_sidecar(
        sidecar_path(dst),
        {"qhash": qhash, "params": params},
        lambda: True if is_fresh(dst, qhash, params) else None,
        label=f"el sidecar del {label}",
    )


def _land(partial: Path, dst: Path, qhash: str, params: dict[str, Any]) -> bool:
    """Put `partial` over `dst`: True if it was moved, False if `dst` was already fresh, before
    or because the replace was refused (a reader has it open: on Windows ffmpeg and `wave` do not
    share the delete), so the one that is there is the one to use."""
    if is_fresh(dst, qhash, params):
        return False
    refuse_directory(dst, f"el {work_label(dst)}")
    try:
        os.replace(partial, dst)
    except PermissionError:
        try:  # waits for the other process, or for the reader to let go (001.29, point 1)
            if wait_to_land(partial, dst, lambda: True if is_fresh(dst, qhash, params) else None):
                return False
        except PermissionError:
            raise ProjectError(f"cierra el {work_label(dst)} en el reproductor y repite") from None
    return True
