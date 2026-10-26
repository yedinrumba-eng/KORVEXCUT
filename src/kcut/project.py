"""An open video project: its root, its configuration and its paths."""

import os
from dataclasses import dataclass
from pathlib import Path

from kcut.config.load import load_config
from kcut.config.model import ProjectConfig
from kcut.errors import ProjectError, UsageError
from kcut.ingest.inventory import Inventory, InventoryInvalid, field_text
from kcut.ingest.inventory import load_inventory as _load_inventory_file
from kcut.jsonio import refuse_directory
from kcut.logfile import append_log
from kcut.paths import CONFIG_NAME, Layout, _clean_parts, _reject_unsafe, find_project, is_inside


@dataclass
class Project:
    root: Path
    config: ProjectConfig
    layout: Layout


def locate_project(explicit: str | None) -> Path | None:
    """Project root from `--project` or by climbing from the cwd; `None` if there is none."""
    if explicit is not None:
        root = Path(explicit).resolve()
        return root if (root / CONFIG_NAME).is_file() else None
    try:
        return find_project(Path.cwd())
    except ProjectError:
        return None


def open_project(explicit: str | None) -> Project:
    """Open the project given by `--project`, or the one that contains the cwd.

    A project whose `.kcut` or layout folders resolve outside its root (a junction or symlink
    planted in a shared folder) is refused: kcut would otherwise write through the link.
    """
    if explicit is not None:
        root = Path(explicit).resolve()
        if not (root / CONFIG_NAME).is_file():
            raise ProjectError(f"{root} no es un proyecto de kcut (falta {CONFIG_NAME})")
    else:
        root = find_project(Path.cwd())
    layout = Layout(root)
    check_layout_inside(root, layout)
    return Project(root=root, config=load_config(root / CONFIG_NAME), layout=layout)


def check_layout_inside(root: Path, layout: Layout) -> None:
    """ProjectError if any existing folder of the layout is a link, leaves `root` or is a file.

    Links are refused even when they point inside the project: `.kcut -> crudo/` would make every
    cache write land in the user's footage. A file where a folder belongs (001.7) is named, so the
    user is not left with a bare `NotADirectoryError`. Called before anything is written.
    """
    base = root.resolve()
    for path in layout.all_paths():
        if not os.path.lexists(path):
            continue
        if os.path.islink(path) or os.path.isjunction(path):
            raise ProjectError(
                f"{path} es un enlace (symlink o junction): no se abre el proyecto; "
                "reemplázalo por una carpeta de verdad"
            )
        if not is_inside(base, path.resolve()):
            raise ProjectError(f"{path} resuelve fuera del proyecto: no se abre el proyecto")
        if not path.is_dir():
            rel = path.relative_to(layout.root).as_posix()
            raise ProjectError(f"hay un archivo donde kcut espera una carpeta: {rel}")


def load_inventory(project: Project, log: Path | None = None) -> Inventory:
    """Load `.kcut/inventory.json`; without it the user has to run `kcut ingest`.

    An inventory that does not pass validation is a ProjectError with a fixed text and the field
    by position (`clips[0].id`), never a value from the file (spec 001.12, point 2): the loader's
    own message quotes the file, which anyone could have planted, and Claude reads this output.
    The whole message goes to `log` (the run's log) and nowhere else.
    """
    if not project.layout.inventory.is_file():
        raise ProjectError("no hay inventario: corre kcut ingest")
    try:
        return _load_inventory_file(project.layout.inventory, project.root)
    except InventoryInvalid as exc:
        if log is not None:
            append_log(log, f"[inventory_invalid] {exc.message_es}\n")
        where = f" ({field_text(exc.field)})" if exc.field else ""
        raise ProjectError(
            f"inventory.json no pasó la validación{where}; corre kcut ingest"
        ) from None


def under_kcut(project: Project, target: Path) -> bool:
    """Is `target` inside `.kcut/`, the folder kcut keeps its own files in? A file there is
    replaced without `--force` (001.21, point 6)."""
    return is_inside(project.root.resolve() / ".kcut", target.resolve())


def assert_writable(project: Project, rel: str, *, replace: bool = True) -> Path:
    """The absolute path of `rel` (relative to the project, with `/`) if kcut may write there.

    For every write outside `.kcut/` (spec 0.9, 001.15 T4). Refuses, with a ProjectError:
    a path that breaks the rules of 0.10.7 (absolute, drive letter, UNC, `..` that escapes, `:`,
    NUL, reserved names); a path that goes through a symlink or a junction; a target that is not
    inside the project or is under `crudo/`; a target that is a folder or a hard link. It does
    not create folders: the caller makes the parent after this.

    With `replace=False` a file that is already there is a UsageError that names it (001.20,
    point 9): what `--out` does without `--force`, so a prompt injection cannot ask for
    `recursos/logo.png` to be overwritten. Under `.kcut/` it is replaced all the same (001.21,
    point 6). `pack` keeps the default: it rewrites its files.
    """
    _reject_unsafe(rel)
    parts = _clean_parts(rel)
    root = project.root.resolve()
    current = root
    for part in parts:
        current = current / part
        if os.path.lexists(current) and (os.path.islink(current) or os.path.isjunction(current)):
            raise ProjectError(
                f"{rel} pasa por un enlace (symlink o junction): "
                "kcut no escribe a través de enlaces"
            )
    target = root.joinpath(*parts).resolve()
    # Windows reads `crudo.` and `crudo ` as `crudo`: the first part is compared without them
    in_crudo = parts[0].rstrip(". ").lower() == "crudo" or is_inside((root / "crudo"), target)
    if not is_inside(root, target) or in_crudo:
        raise ProjectError(f"kcut no escribe en {rel}")
    if target.exists():
        refuse_directory(target)
        if os.lstat(target).st_nlink > 1:
            raise ProjectError(f"{rel} es un enlace duro (hard link): kcut no escribe ahí")
        if not replace and not under_kcut(project, target):
            raise UsageError(f"{rel} ya existe; usa --force para pisarlo")
    return target
