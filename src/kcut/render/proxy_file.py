"""The proxy of a clip: its file and its size, checked against what `ingest` gives (spec 001.20,
point 4; 001.31, point 12). It was `commands/view.py`'s `proxy_of`, which `render/preview.py`
imported from a command; here the commands and the render both import it, from a module that
is neither.
"""

from pathlib import Path

from kcut.errors import ProjectError, UsageError
from kcut.ff.reader import PROXY_MISMATCH
from kcut.ingest import workfiles
from kcut.ingest.inventory import Clip
from kcut.paths import resolve_in_project
from kcut.project import Project

Proxy = tuple[Path, tuple[int, int]]  # the file and its size (w, h)


def proxy_of(project: Project, clip: Clip) -> Proxy:
    """The clip's proxy file and its size `(w, h)`; a clip without video is a UsageError, a proxy
    that is not there (or not in the inventory) a ProjectError that says to run `kcut ingest`."""
    if clip.video is None:
        raise UsageError(f"{clip.id} no tiene video")
    work = clip.work
    if work is None or work.proxy is None or work.proxy_w is None or work.proxy_h is None:
        raise ProjectError(f"falta el proxy de {clip.id}; corre kcut ingest")
    if (work.proxy_w, work.proxy_h) != workfiles.proxy_size(clip.video):
        raise ProjectError(PROXY_MISMATCH)  # the inventory is not trusted (001.20, point 4)
    path = resolve_in_project(project.root, work.proxy)
    if not path.is_file():
        raise ProjectError(f"falta el proxy de {clip.id}; corre kcut ingest")
    return path, (work.proxy_w, work.proxy_h)
