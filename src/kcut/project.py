"""An open video project: its root, its configuration and its paths."""

import os
from dataclasses import dataclass
from pathlib import Path

from kcut.config.load import load_config
from kcut.config.model import ProjectConfig
from kcut.errors import ProjectError
from kcut.ingest.inventory import Inventory
from kcut.ingest.inventory import load_inventory as _load_inventory_file
from kcut.paths import CONFIG_NAME, Layout, find_project, is_inside


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
    """ProjectError if any existing folder of the layout is a link or leaves `root`.

    Links are refused even when they point inside the project: `.kcut -> crudo/` would make every
    cache write land in the user's footage. Called before anything is written.
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


def load_inventory(project: Project) -> Inventory:
    """Load `.kcut/inventory.json`; without it the user has to run `kcut ingest`."""
    if not project.layout.inventory.is_file():
        raise ProjectError("no hay inventario: corre kcut ingest")
    return _load_inventory_file(project.layout.inventory, project.root)
