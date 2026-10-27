"""Project layout and safe resolution of paths that come from data (spec 0.3, 0.10.7)."""

import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kcut.errors import ProjectError
from kcut.schema_util import describe_value as quoted

CONFIG_NAME = "kcut.toml"
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_DRIVE = re.compile(r"[A-Za-z]:.*", re.DOTALL)


@dataclass(frozen=True)
class Layout:
    """Every path of a video project (spec 0.3), derived from its root folder."""

    root: Path

    @property
    def crudo(self) -> Path:
        return self.root / "crudo"

    @property
    def recursos(self) -> Path:
        return self.root / "recursos"

    @property
    def manifest(self) -> Path:
        return self.recursos / "recursos.json"

    @property
    def edit(self) -> Path:
        return self.root / "edit"

    @property
    def salida(self) -> Path:
        return self.root / "salida"

    @property
    def qa(self) -> Path:
        return self.root / "qa"

    @property
    def cache(self) -> Path:
        return self.root / ".kcut"

    @property
    def inventory(self) -> Path:
        return self.cache / "inventory.json"

    @property
    def proxy(self) -> Path:
        return self.cache / "proxy"

    @property
    def wav16(self) -> Path:
        return self.cache / "wav16"

    @property
    def wav48(self) -> Path:
        return self.cache / "wav48"

    @property
    def mezz(self) -> Path:
        return self.cache / "mezz"

    @property
    def transcripts(self) -> Path:
        return self.cache / "transcripts"

    @property
    def view(self) -> Path:
        return self.cache / "view"

    @property
    def frames(self) -> Path:
        return self.cache / "frames"

    @property
    def build(self) -> Path:
        return self.cache / "build"

    @property
    def storyboard_cache(self) -> Path:
        return self.cache / "storyboard"

    @property
    def logs(self) -> Path:
        return self.cache / "logs"

    @property
    def locks(self) -> Path:
        return self.cache / "locks"

    def all_paths(self) -> tuple[Path, ...]:
        """Every folder of the layout: `crudo/`, `recursos/`, `edit/`, `salida/`, `qa/`, `.kcut/`
        and each subfolder of `.kcut/`. None of them may be a link (see `check_layout_inside`)."""
        return (
            self.crudo,
            self.recursos,
            self.edit,
            self.salida,
            self.qa,
            self.cache,
            self.proxy,
            self.wav16,
            self.wav48,
            self.mezz,
            self.transcripts,
            self.view,
            self.frames,
            self.build,
            self.storyboard_cache,
            self.logs,
            self.locks,
        )

    def build_dir(self, version: int) -> Path:
        return self.build / f"v{version}"

    def qa_dir(self, version: int) -> Path:
        return self.qa / f"v{version}"


def find_project(start: Path) -> Path:
    """Walk up from `start` to the first folder holding `kcut.toml`."""
    current = start.resolve()
    for folder in (current, *current.parents):
        if (folder / CONFIG_NAME).is_file():
            return folder
    raise ProjectError(
        f"no encuentro {CONFIG_NAME} desde {start}; entra a la carpeta del proyecto o usa --project"
    )


def log_path(
    logs_dir: Path, command: str, now: datetime | None = None, pid: int | None = None
) -> Path:
    """`<logs>/<command>-<YYYYmmdd-HHMMSS>-<pid>.log` (spec 0.11): unique per process."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return logs_dir / f"{command}-{stamp}-{os.getpid() if pid is None else pid}.log"


def resolve_in_project(root: Path, rel: str) -> Path:
    """Resolve a project-relative data path; anything that could leave the project is refused."""
    _reject_unsafe(rel)
    parts = _clean_parts(rel)
    root_resolved = root.resolve()
    target = root_resolved.joinpath(*parts).resolve()
    if not is_inside(root_resolved, target):
        raise ProjectError(f"la ruta {quoted(rel)} sale del proyecto")
    return target


def to_rel(root: Path, p: Path) -> str:
    """POSIX path of `p` relative to the project root."""
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        raise ProjectError(f"la ruta {p} no está dentro del proyecto {root}") from None


def inside_kcut_repo(p: Path) -> bool:
    """True if `p` or any ancestor holds `src/kcut/__init__.py` (the kcut repo itself)."""
    current = p.resolve()
    return any(
        (folder / "src" / "kcut" / "__init__.py").is_file()
        for folder in (current, *current.parents)
    )


def _reject_unsafe(rel: str) -> None:
    if rel == "":
        raise ProjectError("la ruta está vacía")
    if "\x00" in rel:
        raise ProjectError("la ruta contiene un byte NUL")
    if rel.startswith(("\\\\", "//")):
        raise ProjectError(f"la ruta {quoted(rel)} es una ruta de red (UNC)")
    if _DRIVE.fullmatch(rel):
        raise ProjectError(f"la ruta {quoted(rel)} lleva letra de unidad; usa una ruta relativa")
    if rel.startswith(("/", "\\")):
        raise ProjectError(f"la ruta {quoted(rel)} es absoluta; usa una ruta relativa al proyecto")
    if ":" in rel:
        raise ProjectError(f"la ruta {quoted(rel)} lleva ':' (flujos alternos de Windows)")


def _clean_parts(rel: str) -> list[str]:
    """Split on `/` and `\\`, reject reserved names and `..` that escapes; drop `.` and empties."""
    clean: list[str] = []
    for part in rel.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        stem = part.split(".", 1)[0].strip().upper()
        if stem in _RESERVED:
            raise ProjectError(f"la ruta {quoted(rel)} usa el nombre reservado de Windows {stem}")
        if part == "..":
            if not clean:
                raise ProjectError(f"la ruta {quoted(rel)} sale del proyecto con '..'")
            clean.pop()
            continue
        clean.append(part)
    if not clean:
        raise ProjectError(f"la ruta {quoted(rel)} no apunta a ningún archivo del proyecto")
    return clean


def lone_file_reason(info: os.stat_result) -> str | None:
    """Why a file that kcut is about to write in place is not safe to write, or None if it is.

    `info` is the `os.fstat` of the handle that is already open (never a `stat` of the name: the
    name can change between looking and opening). Only a regular file with a single link is
    written: another link is the same file under another name, perhaps one in `crudo/` (spec
    001.25, point 2; the same rule as the logs, 001.6). Used by every writer in place under
    `.kcut/`: the logs and the locks."""
    if not stat.S_ISREG(info.st_mode):
        return "no es un archivo regular (enlace o carpeta)"
    if info.st_nlink != 1:
        return f"tiene {info.st_nlink} enlaces duros"
    return None


def is_inside(root: Path, target: Path) -> bool:
    """True if `target` is `root` or lies under it (both already resolved; `normcase` compare)."""
    base = os.path.normcase(str(root))
    candidate = os.path.normcase(str(target))
    return candidate == base or candidate.startswith(base.rstrip(os.sep) + os.sep)
