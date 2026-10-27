"""UTF-8 JSON and text files, written atomically (spec 0.9)."""

import contextlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from kcut.errors import ProjectError, UsageError

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


def write_json_exclusive(
    path: Path,
    obj: object,
    label: str | None = None,
    *,
    on_refused: Callable[[Path, Path], None] | None = None,
) -> None:
    """Write `obj` as indented UTF-8 JSON through `<name>.<pid>.tmp` and `os.replace`, with a
    temporary file that is created new (spec 001.27, point 5; moved here from `mezz_files`).

    The temporary has the pid, so two renders that write the same sidecar together do not write
    the same file, and it is created with `"x"`: a link planted after the `unlink` makes the open
    fail and is not written through (001.26, point 7). A folder at `path` and a `path` that a
    player has open are a ProjectError, as for `write_json_atomic`, which keeps its `<name>.tmp`.

    `label` is the phrase that names the file in the messages (`el sidecar del wav48 de a1`): if it
    comes, the messages have it where they had the path, and the system's text (`strerror`, or the
    class of the error) where they had `str(exc)`, which carries the path too (001.28, point 2).

    `on_refused(tmp, path)` is what is done when the move is refused with a `PermissionError`
    (another process has `path` open, on Windows): it either gets the move done, or leaves the
    `path` that is there as the good one, or raises `PermissionError` again, which is the error of
    a file that a player has open. Without it the first refusal is that error (001.31, point 1;
    `ingest.sidecar.land_sidecar` is the one that gives it)."""
    refuse_directory(path, label)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.unlink(missing_ok=True)  # never write through a stale file or a planted link
        text = json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False) + "\n"
        with tmp.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        try:
            os.replace(tmp, path)
        except PermissionError:
            if on_refused is None:
                raise
            on_refused(tmp, path)
    except PermissionError:
        named = label or f"el archivo {path}"
        raise ProjectError(f"cierra {named} en el reproductor y repite") from None
    except OSError as exc:
        reason = str(exc) if label is None else (exc.strerror or type(exc).__name__)
        raise ProjectError(f"no pude escribir {label or path}: {reason}") from None
    finally:
        _discard(tmp)


def refuse_directory(path: Path, label: str | None = None) -> None:
    """ProjectError if a folder sits where a file is expected (not the "close the player" case).
    With a `label` (a phrase like `el wav48 de a1`) the message names it, not the path (001.28)."""
    if path.is_dir():
        raise ProjectError(
            f"en {label or path} hay una carpeta donde kcut espera un archivo; bórrala o muévela"
        )


def write_text_atomic(path: Path, text: str) -> None:
    """Write UTF-8 text with `\\n` newlines through `<path>.tmp` and `os.replace`."""

    def write(tmp: Path) -> None:
        with tmp.open(
            "w", encoding="utf-8", errors="replace", newline="\n"
        ) as fh:  # no surrogate crash
            fh.write(text)

    _replace_through_tmp(path, write)


def write_bytes_atomic(path: Path, data: bytes, *, replace: bool = True) -> None:
    """Write bytes through `<path>.tmp` and `os.replace`, as `write_text_atomic` does for text.

    The PNG and JPG that kcut makes are encoded in memory (`io.BytesIO`) and written with this
    (spec 001.15): a folder in the target, a stale `.tmp`, a target open in a viewer and any
    other failure of the disk give the same errors as for the text files.

    With `replace=False` the move is `os.rename`, which fails if `path` is there: a file that
    appeared after `assert_writable` looked is not overwritten but a UsageError that names it
    (001.21, point 6). Callers pass `--force` (or "it is under `.kcut/`") as `replace`.

    Only on Windows: there `os.rename` fails if the target exists. On POSIX it replaces the
    target silently, so with `replace=False` the guard is Windows-only (001.22, point 9; debt 32).
    The cure, `os.link` plus `unlink` with a fallback for FAT/exFAT volumes that have no hard
    links, is left for later: kcut is a Windows-first tool.
    """

    def write(tmp: Path) -> None:
        with tmp.open("wb") as fh:
            fh.write(data)

    _replace_through_tmp(path, write, replace=replace)


def _replace_through_tmp(
    path: Path, write: Callable[[Path], None], *, replace: bool = True
) -> None:
    """The shared flow: refuse a folder at `path`, make its parent, write `<path>.tmp` with
    `write`, `os.replace` it over `path` (`os.rename` if `replace` is False, which refuses a file
    that is there, on Windows only: POSIX replaces it). Failures are a ProjectError (spec 0.10,
    point 5)."""
    refuse_directory(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # a parent that is a file, a name the system refuses, no permission
        raise ProjectError(f"no pude crear la carpeta {path.parent}: {exc}") from None
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.unlink(missing_ok=True)  # never write through a stale file or a planted link
        write(tmp)
        if replace:
            os.replace(tmp, path)
        else:
            # fails if `path` is there, but only on Windows: on POSIX `os.rename` replaces it
            # (001.22, point 9; debt 32). Windows-first, so this is the guard we have
            os.rename(tmp, path)
    except FileExistsError:
        _discard(tmp)
        raise UsageError(f"{path.name} ya existe; usa --force para pisarlo") from None
    except PermissionError:
        _discard(tmp)
        raise ProjectError(f"cierra el archivo {path} en el reproductor y repite") from None
    except OSError as exc:
        _discard(tmp)
        raise ProjectError(f"no pude escribir {path}: {exc}") from None


def _discard(tmp: Path) -> None:
    """Remove a leftover `.tmp`; if the system refuses even that (an invalid name), leave it."""
    with contextlib.suppress(OSError):
        tmp.unlink(missing_ok=True)
