"""The guard of `.kcut/`: kcut never writes, moves or deletes a path that resolves outside it
(spec 0.9). Split from `workfiles.py` by the 300-line rule (001.26); `workfiles` still names it
`_assert_in_cache`, which is what the rest of the code calls.

Also here, because the render and the graphics commands share them (001.31, points 2 and 12):
`assert_own_folder`, the rule for a folder of the cache where kcut writes, and `build_folder`, that
rule for `.kcut/build/vN`.
"""

import os
from pathlib import Path

from kcut.errors import ProjectError
from kcut.paths import is_inside, same_path
from kcut.paths import plain_path as plain_path  # moved to `paths.py` in 001.28; still importable
from kcut.project import Project


def assert_in_cache(project: Project, path: Path, *, label: str | None = None) -> Path:
    """Resolve `path` (following links) and require it to stay inside the real `.kcut/`.

    The cache must really be `<root>/.kcut` (a `.kcut` linked to `crudo/` is refused) and the
    target must not sit under `crudo/`, whatever the cache says. The paths are compared without
    the extended-length prefix (`plain_path`).

    `label` is the phrase that names `path` in the message when it is given (`wav48 de a1`, from
    `workfiles.work_label`): the name of a work file has the slug of the original clip, which may
    hold a phone number (001.30, point 2). Without it the message names the path, as it always did.
    """
    cache = plain_path(project.layout.cache.resolve())
    real = plain_path((project.root / ".kcut").resolve())
    if not same_path(cache, real):
        raise ProjectError(f"{project.layout.cache} no es la carpeta .kcut real del proyecto")
    resolved = plain_path(path.resolve())
    under_crudo = is_inside(plain_path((project.root / "crudo").resolve()), resolved)
    if under_crudo or not is_inside(cache, resolved):
        named = path if label is None else label
        raise ProjectError(f"{named} queda fuera de .kcut/: kcut no escribe, mueve ni borra ahí")
    return resolved


def assert_own_folder(project: Project, folder: Path) -> Path:
    """`folder`, after it was seen to be a real folder of the cache and not a symlink or a junction
    to somewhere else, even somewhere inside `.kcut/` (`build/v7 -> .kcut/` would make the render
    write `video.mp4` in the root of the cache, and `gfx -> transcripts` would write `index.json`
    over the transcripts): it has to resolve to itself, inside `.kcut/` (`assert_in_cache`). A
    ProjectError before anything is written there (001.26 point 10, 001.31 point 2), and a file
    where the folder goes is one too (001.27, point 3), never a `FileExistsError`.

    A folder that is not there yet is fine: the caller makes it. This is the rule of every folder of
    the cache where kcut writes, and it is called again before each write into the folder, because
    a render or a capture takes minutes and the folder can be changed for a link in the meantime."""
    assert_in_cache(project, folder)
    if os.path.lexists(folder):
        itself = folder.parent.resolve() / folder.name
        linked = os.path.islink(folder) or os.path.isjunction(folder)
        if linked or not same_path(folder.resolve(), itself):
            raise ProjectError(
                f"{folder} es un enlace (symlink o junction) o no resuelve a sí misma: "
                "kcut no escribe ahí; reemplázala por una carpeta de verdad"
            )
        if not folder.is_dir():
            raise ProjectError(
                f"{folder} es un archivo; kcut espera una carpeta ahí: bórralo o renómbralo"
            )
    return folder


def build_folder(project: Project, version: int) -> Path:
    """`.kcut/build/vN`, checked as `assert_own_folder` says (001.26 point 10, 001.27 points 3 and
    4). The render calls it again before each write into the folder (the picture, the voice and the
    mux), because the mezzanines take minutes."""
    return assert_own_folder(project, project.layout.build_dir(version))
