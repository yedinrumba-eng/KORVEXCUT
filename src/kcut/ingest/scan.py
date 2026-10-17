"""Step 1 of `kcut ingest`: list the files of `crudo/` (read only) and hash them."""

import os
from dataclasses import dataclass
from pathlib import Path

from kcut.errors import ProjectError
from kcut.ingest.classify import ClipClass
from kcut.ingest.inventory_model import ImageMeta, Notice
from kcut.ingest.naming import qhash
from kcut.ingest.probe import MediaInfo
from kcut.project import Project


@dataclass
class Found:
    """A file of `crudo/` while it is being inspected."""

    rel: str
    path: Path
    size: int
    hash: str
    info: MediaInfo | None = None
    image: ImageMeta | None = None
    wav: Path | None = None
    peak: float | None = None
    proxy_dims: tuple[int, int] | None = None
    failed: bool = False
    wav_failed: bool = False
    flags: tuple[str, ...] = ()
    clip_class: ClipClass = "desconocido"

    @property
    def ext(self) -> str:
        return self.path.suffix.lower()


def scan_crudo(project: Project, notices: list[Notice]) -> list[Found]:
    """Every regular file under `crudo/`, sorted by path. Hidden entries are skipped; folders that
    are junctions or symlinks are not entered (`skipped_link`); a path is listed once."""
    crudo = project.layout.crudo
    if not crudo.is_dir():
        raise ProjectError(f"no existe la carpeta {crudo}; crea el proyecto con kcut new")
    found: list[Found] = []
    seen: set[str] = set()
    for folder, dirs, names in os.walk(crudo):
        kept: list[str] = []
        for name in sorted(dirs):
            full = Path(folder) / name
            if name.startswith("."):
                continue
            if os.path.islink(full) or os.path.isjunction(full):
                notices.append(Notice("skipped_link", f"{_rel(project, full)}: carpeta enlazada"))
                continue
            kept.append(name)
        dirs[:] = kept
        for name in sorted(names):
            path = Path(folder) / name
            if name.startswith("."):
                continue
            if path.is_symlink():
                notices.append(Notice("skipped_link", f"{_rel(project, path)}: enlace simbólico"))
                continue
            rel = _rel(project, path)
            if not _encodable(rel):
                shown = rel.encode("utf-8", errors="replace").decode("utf-8")
                detail = (
                    f"{shown}: el nombre de este archivo tiene caracteres inválidos; renómbralo"
                )
                notices.append(Notice("probe_failed", detail, shown))
                continue
            if os.path.normcase(rel) in seen:
                continue
            seen.add(os.path.normcase(rel))
            try:
                found.append(Found(rel=rel, path=path, size=path.stat().st_size, hash=qhash(path)))
            except OSError as exc:
                # no hash, no stable id: the file is reported (`probe_failed`) and the rest go on
                detail = f"{rel}: no se pudo leer ({exc.strerror or type(exc).__name__}); se omite"
                notices.append(Notice("probe_failed", detail, rel))
    return sorted(found, key=lambda f: (f.rel.casefold(), f.rel))


def _encodable(rel: str) -> bool:
    """False for a name with a lone surrogate (Windows allows them): it cannot be written to the
    inventory or printed, so the file is reported instead of ingested (001.7, point 14)."""
    try:
        rel.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _rel(project: Project, path: Path) -> str:
    """`crudo/...` as POSIX text, without resolving links (a junction must not break this)."""
    return f"crudo/{path.relative_to(project.layout.crudo).as_posix()}"
