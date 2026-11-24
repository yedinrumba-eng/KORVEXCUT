"""The inputs of a build, copied next to its report (spec S1.9b; 001.15, 001.51).

`kcut build` copies what the video was made from to `qa/vN/inputs/` and writes `inputs.json` with
the SHA-256 of each copy, so that `kcut qa` (which reads the EDL of the snapshot first) judges the
video against what was built and not against what the files say by now. Each copy and `inputs.json`
pass through `assert_writable` (T4), once before the folder is made and again right before the
write: `qa/vN` can become a junction to somebody else's folder meanwhile.

The files are read twice by the build, and never again: `read_inputs` at the start and
`confirm_inputs` after the mux (a file that is not the same is a build that has to be repeated, so
the snapshot never certifies something that was not rendered). `snapshot_inputs` writes the bytes
of the first reading. `clear_stale` deletes what described the video that is about to be replaced.
"""

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from kcut.errors import CheckFailed, ProjectError
from kcut.jsonio import MAX_JSON_BYTES, read_capped, write_bytes_atomic, write_json_atomic
from kcut.paths import resolve_in_project
from kcut.project import Project, assert_writable

SCHEMA = "kcut.inputs/1"
INPUTS_NAME = "inputs.json"
CHANGED_ES = "{rel} cambió mientras se construía; corre kcut build otra vez"
UNREADABLE_ES = "no pude volver a leer {rel} al terminar ({reason}); corre kcut build otra vez"
WRITE_ES = "no pude {action} {rel} ({reason}); ciérralo y repite"


@dataclass(frozen=True)
class Unreadable:
    """An input that is there and could not be read (too big, locked, a link out of the project)."""

    reason: str


# path in the project -> its bytes, `Unreadable`, or `None` if it is not there
Inputs = dict[str, bytes | Unreadable | None]


def input_files(version: int, edl_rel: str | None = None) -> tuple[str, ...]:
    """What a build of version `version` snapshots, relative to the project, in this order. The EDL
    is `edl_rel` (the `--edl` the build was given), or `edit/edl-v<version>.json`."""
    return (
        edl_rel or f"edit/edl-v{version}.json",
        "edit/graphics.json",
        "edit/sfx.json",
        "edit/music.json",
        "edit/correcciones.json",
        "edit/estrategia.md",
        "kcut.toml",
    )


def read_inputs(project: Project, version: int, edl_rel: str | None = None) -> Inputs:
    """The bytes of each input that exists, `None` for the one that is not there and `Unreadable`
    for the one that cannot be read. It never fails: the checks of the build give their own errors,
    in their own order (001.51)."""
    found: Inputs = {}
    for rel in input_files(version, edl_rel):
        try:
            source = resolve_in_project(project.root, rel)
            found[rel] = read_capped(source, MAX_JSON_BYTES) if os.path.lexists(source) else None
        except (ProjectError, OSError) as exc:
            found[rel] = Unreadable(type(exc).__name__)
    return found


def confirm_inputs(project: Project, first: Inputs, version: int, edl_rel: str | None) -> None:
    """Read the inputs again and compare with `first`: a file with other bytes, one that appeared
    or one that went away is a CheckFailed (exit 1) that names it; one that cannot be read now is
    a ProjectError (exit 3)."""
    second = read_inputs(project, version, edl_rel)
    for rel, now in second.items():
        if isinstance(now, Unreadable):
            raise ProjectError(UNREADABLE_ES.format(rel=rel, reason=now.reason))
    for rel, before in first.items():
        if before != second[rel]:
            raise CheckFailed(CHANGED_ES.format(rel=rel))


def snapshot_inputs(
    project: Project, version: int, *, edl_rel: str | None = None, read: Inputs
) -> Path:
    """Write the bytes of `read` (what `read_inputs` gave at the start of the build) to
    `qa/v<version>/inputs/<name>` and `inputs.json` there (`{"schema", "version", "files":
    {<path in the project>: <sha256>}}`); return its path. `edit/` and `kcut.toml` are not read
    again.

    A copy that an earlier build left of a file that is not there any more is deleted, so the
    snapshot never says that a build used something it did not. An `OSError` of the folder is a
    ProjectError (001.51)."""
    folder = f"qa/v{version}/inputs"
    first = assert_writable(project, f"{folder}/{INPUTS_NAME}")
    digests: dict[str, str] = {}
    try:
        first.parent.mkdir(parents=True, exist_ok=True)
        for rel in input_files(version, edl_rel):
            target_rel = f"{folder}/{PurePosixPath(rel).name}"
            data = read[rel]
            if data is None:
                assert_writable(project, target_rel).unlink(missing_ok=True)
                continue
            if isinstance(data, Unreadable):
                raise ProjectError(UNREADABLE_ES.format(rel=rel, reason=data.reason))
            write_bytes_atomic(assert_writable(project, target_rel), data)  # looked at again, now
            digests[rel] = hashlib.sha256(data).hexdigest()
        document = {"schema": SCHEMA, "version": version, "files": digests}
        path = assert_writable(project, f"{folder}/{INPUTS_NAME}")
        write_json_atomic(path, document)
    except OSError as exc:
        raise ProjectError(
            WRITE_ES.format(action="escribir", rel=folder, reason=type(exc).__name__)
        ) from exc
    return path


def stale_rels(version: int, edl_rel: str | None = None) -> list[str]:
    """What `clear_stale` deletes and `snapshot_inputs` writes in `qa/vN/`, relative to the project:
    `report.json`, `contact.jpg`, `inputs/inputs.json` and the copy of each input. One list, for the
    check before the work and for the delete (001.52)."""
    folder = f"qa/v{version}"
    names = [PurePosixPath(rel).name for rel in input_files(version, edl_rel)]
    rels = [f"{folder}/report.json", f"{folder}/contact.jpg", f"{folder}/inputs/{INPUTS_NAME}"]
    return rels + [f"{folder}/inputs/{name}" for name in names]


def clear_stale(project: Project, version: int, edl_rel: str | None = None) -> None:
    """Delete what described the video that `kcut build` is about to replace: `qa/vN/report.json`,
    `qa/vN/contact.jpg`, the copies in `qa/vN/inputs/` and its `inputs.json` (001.51). All the
    paths pass through `assert_writable` first: a link in any of them is a ProjectError and nothing
    is deleted. A video without a report does not lie; one with the report of another does."""
    folder = f"qa/v{version}"
    rels = stale_rels(version, edl_rel)
    for rel in rels:
        assert_writable(project, rel)
    try:
        for rel in rels:
            assert_writable(project, rel).unlink(missing_ok=True)  # and again, right before
    except OSError as exc:
        raise ProjectError(
            WRITE_ES.format(action="borrar", rel=folder, reason=type(exc).__name__)
        ) from exc
