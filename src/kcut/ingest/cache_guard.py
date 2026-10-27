"""The guard of `.kcut/`: kcut never writes, moves or deletes a path that resolves outside it
(spec 0.9). Split from `workfiles.py` by the 300-line rule (001.26); `workfiles` still names it
`_assert_in_cache`, which is what the rest of the code calls.
"""

import os
from pathlib import Path

from kcut.errors import ProjectError
from kcut.paths import is_inside
from kcut.project import Project

_EXTENDED = "\\\\?\\"  # the extended-length prefix: `\\?\C:\...`
_EXTENDED_UNC = "\\\\?\\UNC\\"  # the same for a network path: `\\?\UNC\server\share\...`


def plain_path(path: Path) -> Path:
    """`path` without the extended-length prefix of Windows (`\\\\?\\`; for a network path
    `\\\\?\\UNC\\` becomes `\\\\`).

    `Path.resolve` leaves the prefix on a file that another process is creating or replacing at
    that very moment, and then it no longer looks like it is inside the folder it is in. Both
    sides of a comparison have to be without it (001.26, point 4)."""
    text = str(path)
    if text[: len(_EXTENDED_UNC)].upper() == _EXTENDED_UNC:
        return Path("\\\\" + text[len(_EXTENDED_UNC) :])
    if text.startswith(_EXTENDED):
        return Path(text[len(_EXTENDED) :])
    return path


def assert_in_cache(project: Project, path: Path) -> Path:
    """Resolve `path` (following links) and require it to stay inside the real `.kcut/`.

    The cache must really be `<root>/.kcut` (a `.kcut` linked to `crudo/` is refused) and the
    target must not sit under `crudo/`, whatever the cache says. The paths are compared without
    the extended-length prefix (`plain_path`).
    """
    cache = plain_path(project.layout.cache.resolve())
    real = plain_path((project.root / ".kcut").resolve())
    if os.path.normcase(str(cache)) != os.path.normcase(str(real)):
        raise ProjectError(f"{project.layout.cache} no es la carpeta .kcut real del proyecto")
    resolved = plain_path(path.resolve())
    under_crudo = is_inside(plain_path((project.root / "crudo").resolve()), resolved)
    if under_crudo or not is_inside(cache, resolved):
        raise ProjectError(f"{path} queda fuera de .kcut/: kcut no escribe, mueve ni borra ahí")
    return resolved
