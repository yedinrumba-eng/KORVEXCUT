"""The guard of `.kcut/`: kcut never writes, moves or deletes a path that resolves outside it
(spec 0.9). Split from `workfiles.py` by the 300-line rule (001.26); `workfiles` still names it
`_assert_in_cache`, which is what the rest of the code calls.
"""

from pathlib import Path

from kcut.errors import ProjectError
from kcut.paths import is_inside, same_path
from kcut.paths import plain_path as plain_path  # moved to `paths.py` in 001.28; still importable
from kcut.project import Project


def assert_in_cache(project: Project, path: Path) -> Path:
    """Resolve `path` (following links) and require it to stay inside the real `.kcut/`.

    The cache must really be `<root>/.kcut` (a `.kcut` linked to `crudo/` is refused) and the
    target must not sit under `crudo/`, whatever the cache says. The paths are compared without
    the extended-length prefix (`plain_path`).
    """
    cache = plain_path(project.layout.cache.resolve())
    real = plain_path((project.root / ".kcut").resolve())
    if not same_path(cache, real):
        raise ProjectError(f"{project.layout.cache} no es la carpeta .kcut real del proyecto")
    resolved = plain_path(path.resolve())
    under_crudo = is_inside(plain_path((project.root / "crudo").resolve()), resolved)
    if under_crudo or not is_inside(cache, resolved):
        raise ProjectError(f"{path} queda fuera de .kcut/: kcut no escribe, mueve ni borra ahí")
    return resolved
