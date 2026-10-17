"""UTF-8 JSON and text files, written atomically (spec 0.9)."""

import json
import os
from pathlib import Path
from typing import Any

from kcut.errors import ProjectError


def read_json(path: Path) -> Any:
    """Read a JSON file; a malformed file raises ProjectError with file, line and column."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ProjectError(f"no existe el archivo {path}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ProjectError(f"no pude leer {path}: {exc}") from None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectError(
            f"{path}: JSON mal formado en la línea {exc.lineno}, columna {exc.colno}: {exc.msg}"
        ) from None
    except RecursionError:
        raise ProjectError(f"{path}: JSON demasiado anidado") from None
    except ValueError as exc:  # e.g. a number with thousands of digits
        raise ProjectError(f"{path}: JSON inválido: {exc}") from None


def write_json_atomic(path: Path, obj: object) -> None:
    """Write `obj` as indented UTF-8 JSON through `<path>.tmp` and `os.replace`."""
    write_text_atomic(path, json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n")


def refuse_directory(path: Path) -> None:
    """ProjectError if a folder sits where a file is expected (not the "close the player" case)."""
    if path.is_dir():
        raise ProjectError(
            f"en {path} hay una carpeta donde kcut espera un archivo; bórrala o muévela"
        )


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 text with `\\n` newlines through `<path>.tmp` and `os.replace`."""
    refuse_directory(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.unlink(missing_ok=True)  # never write through a stale file or a planted link
        with tmp.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise ProjectError(f"cierra el archivo {path} en el reproductor y repite") from None
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise ProjectError(f"no pude escribir {path}: {exc}") from None
