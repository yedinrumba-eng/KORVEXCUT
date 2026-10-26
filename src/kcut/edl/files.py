"""Finding and reading `edit/edl-vN.json` (spec S1.5, 001.15).

A file that is missing or is not JSON is a ProjectError (exit 3). The shape of the JSON is judged
by `edl.parse`, which turns schema errors into `E01` issues instead of raising.
"""

import re

from kcut.edl.model import Edl
from kcut.edl.parse import parse_edl
from kcut.errors import ProjectError
from kcut.issues import Issue
from kcut.jsonio import read_json
from kcut.paths import resolve_in_project
from kcut.project import Project
from kcut.schema_util import describe_value

EDL_NAME = re.compile(r"edl-v([1-9][0-9]{0,3})\.json")
MAX_EDL_BYTES = 4 * 1024 * 1024  # an EDL of tens of thousands of spans; a bigger file is refused


def find_edl(project: Project, rel: str | None) -> tuple[str, int]:
    """The EDL to work on: `(path relative to the project, N)`.

    Without `rel`, the `edit/edl-vN.json` with the highest N (names `edl-v([1-9][0-9]{0,3}).json`);
    none is a ProjectError. With `rel`, that file (relative to the project); N comes from its name,
    which has to follow the same pattern."""
    if rel is not None:
        posix = rel.replace("\\", "/")
        resolve_in_project(project.root, posix)  # a path that leaves the project is refused here
        return posix, _version_of(posix)
    best = 0
    folder = project.layout.edit
    names = [path.name for path in folder.glob("edl-v*.json")] if folder.is_dir() else []
    for name in names:
        match = EDL_NAME.fullmatch(name)
        if match is not None:
            best = max(best, int(match.group(1)))
    if best == 0:
        raise ProjectError("no hay ningún edit/edl-vN.json; escribe el EDL antes de revisarlo")
    return f"edit/edl-v{best}.json", best


def load_edl(project: Project, rel: str) -> tuple[Edl | None, list[Issue], int]:
    """Read and parse the EDL at `rel`: `(edl or None, E01 issues, N from the file name)`."""
    version = _version_of(rel.replace("\\", "/"))
    data = read_json(resolve_in_project(project.root, rel), MAX_EDL_BYTES)
    edl, issues = parse_edl(data, "")
    return edl, issues, version


def _version_of(rel: str) -> int:
    match = EDL_NAME.fullmatch(rel.rsplit("/", 1)[-1])
    if match is None:
        raise ProjectError(
            f"el nombre del EDL tiene que ser edl-vN.json, con N de 1 a 9999 "
            f"(vino {describe_value(rel.rsplit('/', 1)[-1])})"
        )
    return int(match.group(1))
