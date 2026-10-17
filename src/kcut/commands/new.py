"""kcut new: create the folder layout and `kcut.toml` of a video project.

It never overwrites anything: existing files and folders are kept, and `kcut.toml` is written
last, so a failure in the middle never leaves a half project that looks finished.
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from pathlib import Path

from kcut.config.load import parse_config
from kcut.config.model import ProjectConfig
from kcut.config.names import NAME_MAX, clean_default_name, has_forbidden_chars
from kcut.config.template import render_template
from kcut.console import Out
from kcut.errors import ProjectError, UsageError
from kcut.paths import CONFIG_NAME, Layout, inside_kcut_repo
from kcut.project import check_layout_inside

NAME = "new"
HELP_ES = "Crea un proyecto de video nuevo (carpetas y kcut.toml)"

_FOLDERS = ("crudo", "recursos", "edit", "salida", "qa", ".kcut")
_MANIFEST = "recursos/recursos.json"
_VERSIONS = "edit/versiones.md"
_STRATEGY = "edit/estrategia.md"


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument("path", help="carpeta del proyecto (se crea si no existe)")
    sub.add_argument(
        "--name", default=None, help="nombre del video (por defecto, el de la carpeta)"
    )
    sub.add_argument("--preset", choices=("9:16", "16:9"), default="9:16", help="formato de salida")
    sub.add_argument("--fps", type=int, default=30, help="cuadros por segundo (24 25 30 48 50 60)")
    sub.add_argument("--lang", default="es", help="idioma principal, 2 letras")
    return sub


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    root = Path(args.path).resolve()
    name = _name(args.name, root)
    if inside_kcut_repo(root):
        raise ProjectError("los proyectos de video no van dentro del repo de kcut")
    if os.path.lexists(root / CONFIG_NAME):
        raise ProjectError(f"{root} ya es un proyecto (existe {CONFIG_NAME})")
    if root.exists() and not root.is_dir():
        raise ProjectError(f"{root} existe y no es una carpeta")
    if root.is_dir():
        check_layout_inside(root, Layout(root))  # links in an existing folder, before any write
    text = render_template(name, args.preset, args.fps, args.lang, date.today().isoformat())
    config = parse_config(text, default_name=root.name, source="opciones de kcut new")
    stray = _count_files_outside_layout(root)
    _validate_layout(root)
    try:
        created = _create(root, config, text)
    except OSError as exc:
        raise ProjectError(f"no pude crear el proyecto en {root}: {exc}") from None
    for item in created:
        out.line("OK", f"creado {item}")
    if stray:
        message = f"hay {stray} archivos fuera de crudo/; muévelos a crudo/"
        if args.json:
            out.warn(message)
        else:
            out.line("AVISO", message)
    out.line("INFO", f"proyecto listo en {root}; suelta tu material en crudo/ y corre kcut ingest")
    out.result({"ok": True, "project": str(root), "created": created})
    return 0


def _name(given: str | None, root: Path) -> str:
    """`--name` as typed (rejected if unusable) or the cleaned name of the folder."""
    if given is None:
        return clean_default_name(root.name)
    if not 1 <= len(given) <= NAME_MAX:
        raise UsageError(f"--name debe tener entre 1 y {NAME_MAX} caracteres (tiene {len(given)})")
    if has_forbidden_chars(given):
        raise UsageError(
            "--name no puede llevar saltos de línea, separadores ni caracteres de control "
            "o de formato"
        )
    return given


def _validate_layout(root: Path) -> None:
    """Every folder must be absent or a real folder, every starter file absent or a real file.

    Checked before creating anything, so a refusal leaves the disk untouched.
    """
    for folder in _FOLDERS:
        path = root / folder
        if os.path.lexists(path) and not path.is_dir():
            raise ProjectError(
                f"{path} existe y no es una carpeta: muévela antes de crear el proyecto"
            )
    for rel in (_MANIFEST, _VERSIONS, _STRATEGY):
        path = root / rel
        if os.path.lexists(path) and not path.is_file():
            raise ProjectError(
                f"{path} existe y no es un archivo: muévelo antes de crear el proyecto"
            )


def _create(root: Path, config: ProjectConfig, toml_text: str) -> list[str]:
    """Create what is missing and return exactly what was created. `kcut.toml` goes last."""
    layout = Layout(root)
    root.mkdir(parents=True, exist_ok=True)
    name, out = config.project.name, config.output
    starter = {
        _MANIFEST: '{\n "schema": "kcut.recursos/1",\n "items": []\n}\n',
        _VERSIONS: f"# Versiones - {name}\n",
        _STRATEGY: "\n".join(
            [
                "---",
                f"video: {name}",
                f"formato: {out.preset} · {out.w}x{out.h} · {out.fps} fps",
                "aprobado: no",
                "aprobado_por:",
                "---",
                f"# Estrategia de corte - {name}",
                "",
            ]
        ),
    }
    created: list[str] = []
    for folder in _FOLDERS:
        if not (root / folder).exists():
            (root / folder).mkdir()
            created.append(f"{folder}/")
    for rel, text in starter.items():
        if _create_new(root / rel, text):
            created.append(rel)
    if not _create_new(layout.root / CONFIG_NAME, toml_text):
        raise ProjectError(f"{root} ya es un proyecto (apareció {CONFIG_NAME})")
    return [CONFIG_NAME, *created]


def _create_new(path: Path, text: str) -> bool:
    """Write `path` only if it does not exist (exclusive create). False if it was there."""
    try:
        with path.open("x", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except FileExistsError:
        return False
    return True


def _count_files_outside_layout(root: Path) -> int:
    """Loose files in the folder, for the "move them to crudo/" hint.

    The project's own files (`kcut.toml`, everything inside the layout folders) never count and
    links are not entered."""
    if not root.is_dir():
        return 0
    total = 0
    for folder, dirs, names in os.walk(root):
        at_root = Path(folder) == root
        dirs[:] = [
            d
            for d in dirs
            if not (at_root and d in _FOLDERS)
            and not os.path.islink(Path(folder) / d)
            and not os.path.isjunction(Path(folder) / d)
        ]
        total += len([n for n in names if not (at_root and n == CONFIG_NAME)])
    return total
