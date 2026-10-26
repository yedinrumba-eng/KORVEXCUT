"""UTF-8 JSON and text files, written atomically (spec 0.9)."""

import json
import os
from pathlib import Path
from typing import Any

from kcut.errors import ProjectError

_MIB = 1024 * 1024
# What each JSON file kcut reads may weigh (spec 001.14, point 11): one hostile file cannot cost
# the whole 64 MiB. The transcript, the biggest honest file, keeps the default.
MAX_INDEX_BYTES = 1 * _MIB
MAX_CORRECTIONS_BYTES = 8 * _MIB
MAX_INVENTORY_BYTES = 16 * _MIB
MAX_JSON_BYTES = 64 * _MIB
MAX_TOML_BYTES = 1 * _MIB  # `kcut.toml` (spec 001.16, point 9)
MAX_SIDECAR_BYTES = 1 * _MIB  # `<work file>.json` next to a proxy or a wav16
MAX_MANIFEST_BYTES = 4 * _MIB  # `recursos/manifest.json`


def read_capped(path: Path, max_bytes: int) -> bytes:
    """The bytes of a file of at most `max_bytes`; a bigger one is a ProjectError.

    The size is looked at before reading, and the read asks for no more than the file has (plus one
    byte, to notice a file that grew): a small file costs its own size, not the cap's, and a
    big one is never read. Errors of the file system (`OSError`) are the caller's.
    """
    with path.open("rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        raw = handle.read(size + 1) if size <= max_bytes else b""
    if size > max_bytes or len(raw) > max_bytes:
        cap = f"{max_bytes // _MIB} MB" if max_bytes >= _MIB else f"{max_bytes} bytes"
        raise ProjectError(f"{path}: el archivo pesa más de {cap}; kcut no lo lee")
    if len(raw) > size:  # it grew between the `stat` and the read (spec 001.17, point 9)
        raise ProjectError(f"{path}: el archivo cambió mientras se leía; repite el comando")
    return raw


def read_json(path: Path, max_bytes: int = MAX_JSON_BYTES) -> Any:
    """Read a JSON file; a malformed file raises ProjectError with file, line and column.

    A file over `max_bytes` (64 MiB by default; each kind of file has its own cap) is not parsed:
    it takes the same road as a corrupt one, a ProjectError. At most `max_bytes + 1` bytes are
    ever read, whatever the file grows to.
    """
    try:
        raw = read_capped(path, max_bytes)
    except FileNotFoundError:
        raise ProjectError(f"no existe el archivo {path}") from None
    except OSError as exc:
        raise ProjectError(f"no pude leer {path}: {exc}") from None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
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
        with tmp.open(
            "w", encoding="utf-8", errors="replace", newline="\n"
        ) as fh:  # no surrogate crash
            fh.write(text)
        os.replace(tmp, path)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise ProjectError(f"cierra el archivo {path} en el reproductor y repite") from None
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise ProjectError(f"no pude escribir {path}: {exc}") from None
