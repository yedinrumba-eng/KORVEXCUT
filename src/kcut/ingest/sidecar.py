"""The sidecar of a work file and what it says about the file: is it usable (spec 0.9, 001.4,
001.27 point 8). Split from `workfiles.py` by the 300-line rule; `workfiles` still names all of it
(`workfiles.sidecar_state`, `workfiles.is_fresh`, ...), which is what the rest of the code calls.
Also here, because the landings share them (001.29, 001.31): `wait_to_land`, the wait of a refused
move, and `land_sidecar`, which puts a sidecar in its place with it.
"""

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from kcut.errors import ProjectError
from kcut.jsonio import MAX_SIDECAR_BYTES, read_json, write_json_exclusive
from kcut.paths import lone_file_reason

SidecarState = Literal["fresh", "stale", "missing", "corrupt"]
LAND_WAIT_S = 10.0  # how long a refused `os.replace` waits for the file to be let go or fresh
LAND_POLL_S = 0.1  # how often it looks again


def sidecar_path(path: Path) -> Path:
    """`<file>.json` next to a work file."""
    return path.with_name(path.name + ".json")


def is_lone_file(path: Path) -> bool:
    """Is `path` a regular file with a single link, looked at by its name and not through a link?

    A work file or a mezzanine that is a hard link (a second name of a file that may be outside
    the project), a symlink or a junction is not one of kcut's: it is never trusted, whatever its
    sidecar says (spec 001.27, point 8)."""
    try:
        return lone_file_reason(os.lstat(path)) is None
    except OSError:
        return False


def sidecar_state(path: Path, qhash: str, params: dict[str, Any]) -> SidecarState:
    """Is the work file `path` usable? `corrupt`: the sidecar exists but cannot be read. A file
    that is not a regular file with a single link is `stale` (it is made again), even if its
    sidecar is fresh (001.27, point 8)."""
    if not path.is_file():
        return "missing"
    sidecar = sidecar_path(path)
    if not sidecar.is_file():
        return "missing"
    if not is_lone_file(path):
        return "stale"
    try:
        data = read_json(sidecar, MAX_SIDECAR_BYTES)
    except ProjectError:
        return "corrupt"
    return "fresh" if data == {"qhash": qhash, "params": params} else "stale"


def is_fresh(path: Path, qhash: str, params: dict[str, Any]) -> bool:
    """True when `path` exists and its sidecar holds exactly this `qhash` and `params`."""
    return sidecar_state(path, qhash, params) == "fresh"


def wait_to_land[Found](partial: Path, dst: Path, look: Callable[[], Found | None]) -> Found | None:
    """What `_land` does after its first `os.replace(partial, dst)` was refused with a
    `PermissionError` (spec 001.29, point 1): for `LAND_WAIT_S` seconds, every `LAND_POLL_S`, look
    at `dst` and, if it is not fresh, try the move again.

    `look()` is the check of freshness of the caller: what it finds when `dst` is fresh (the
    entry of a mezzanine, `True` for a work file), or `None`. If it finds something, that is what
    is returned and `partial` is left where it is (the caller deletes it): the other process
    finished the file first. If the move works, `None`. When the time is over the last
    `PermissionError` is raised, and the caller says what it says today.

    Two renders that make the same file end almost together: one moves it and writes its sidecar
    a few milliseconds later, and a refused move in that gap (the file is half replaced, or an
    antivirus has just opened it) is not an error to give up on at the first one. It is not a
    retry of what 001.26 point 4 took out, which hid a false "outside the project": this waits
    for another process between two steps, or for a reader to let go, and has a limit."""
    deadline = time.monotonic() + LAND_WAIT_S
    while True:
        found = look()
        if found is not None:
            return found
        try:
            os.replace(partial, dst)
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(LAND_POLL_S)
        else:
            return None


def land_sidecar[Found](
    path: Path, obj: object, look: Callable[[], Found | None], *, label: str | None = None
) -> Found | None:
    """Write `obj` as the sidecar at `path` (`<sidecar>.<pid>.tmp` created new and moved over it,
    as `write_json_exclusive` does) and wait, as `wait_to_land` does, if the move is refused (spec
    001.31, point 1).

    The sidecar of a work file or of a mezzanine is moved like the file itself, and for the same
    reason: the other render that makes the same file has it open to read it, to see if the file is
    fresh, and Windows refuses to replace a file that is open. `look()` is the check of freshness
    of the caller, as for `wait_to_land`: if the sidecar that is there is already the good one (the
    other render put it) `look()` finds it, that is what is returned and the temporary is deleted.
    `None` if the move was done. If the time is over and the sidecar that is there is not the
    good one, the error is the one `write_json_exclusive` gives for a file that is open: `cierra
    {label or el archivo <path>} en el reproductor y repite`."""
    found: Found | None = None

    def wait(tmp: Path, dst: Path) -> None:
        nonlocal found
        found = wait_to_land(tmp, dst, look)

    write_json_exclusive(path, obj, label, on_refused=wait)
    return found
