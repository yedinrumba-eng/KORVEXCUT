"""One process at a time for each output: an operating system lock on a file (spec S1.5b, DS11).

`os.kill(pid, 0)` is not an option on Windows (signal 0 is Ctrl+C there), and a pid written in a
file says nothing about whether that process is still alive, so the lock is the one the system
keeps: it goes away with the process, however it ends. The file also holds the pid and the time,
only as information for whoever finds a lock taken.
"""

import contextlib
import os
import sys
import time
from pathlib import Path
from types import TracebackType
from typing import Self

from kcut.errors import LockedError, ProjectError
from kcut.jsonio import refuse_directory
from kcut.paths import lone_file_reason

# the byte that is locked: far from the text, so the text can be read and written
_LOCK_AT = 1 << 20


class OutputLock:
    """Context manager that holds `<locks_dir>/<name>.lock` for as long as it is open.

    The lock is taken without waiting: if another process (or this one, through another
    `OutputLock`) holds it, `__enter__` raises `LockedError`. It is released on leaving the
    `with` and by the system if the process dies.

    The file is written in place (the pid and the time), so it is looked at before and after it
    is opened: a folder, a link or a file with another name (a hard link to something of
    `crudo/`) is a ProjectError, and nothing is written to it (001.25, point 2). A lock that
    cannot be opened (read only, in use) is a ProjectError too, never an unexpected failure.
    """

    def __init__(self, locks_dir: Path, name: str) -> None:
        if not name or any(ch in name for ch in "/\\:") or name.startswith("."):
            raise ValueError(f"nombre de lock no válido: {name!r}")
        self._path = locks_dir / f"{name}.lock"
        self._fd: int | None = None

    @property
    def path(self) -> Path:
        return self._path

    def __enter__(self) -> Self:
        fd = self._open()
        try:
            os.lseek(fd, _LOCK_AT, os.SEEK_SET)
            if not _try_lock(fd):
                raise LockedError(
                    f"otro proceso está renderizando esta salida ({self._path.name}); "
                    "espera a que termine"
                )
            self._write_info(fd)
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        return self

    def _open(self) -> int:
        """The lock file, open, after it was seen to be one regular file with a single link: by
        its name before opening it (a link would be followed) and by the open handle after."""
        path = self._path
        refuse_directory(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if os.path.lexists(path):
                self._refuse(lone_file_reason(os.lstat(path)))
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                self._refuse(lone_file_reason(os.fstat(fd)))
            except BaseException:
                os.close(fd)
                raise
        except OSError as exc:
            raise ProjectError(f"no pude abrir el lock {path}: {exc}") from None
        return fd

    def _refuse(self, reason: str | None) -> None:
        if reason is not None:
            raise ProjectError(f"el lock {self._path} no se usa: {reason}; bórralo o muévelo")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        try:
            os.lseek(fd, _LOCK_AT, os.SEEK_SET)
            _unlock(fd)
        finally:
            os.close(fd)

    def _write_info(self, fd: int) -> None:
        """The pid and the time, for whoever wonders; a failure to write them is not a failure to
        lock."""
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, f"pid {os.getpid()}\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n".encode())
        except OSError:
            return


def atomic_replace(partial: Path, final: Path) -> None:
    """Move `partial` over `final` in one step. A `final` that a player has open (Windows says
    `PermissionError`) or that is a folder is a ProjectError that says what to do (0.10.5)."""
    refuse_directory(final)
    try:
        os.replace(partial, final)
    except PermissionError:
        raise ProjectError(f"cierra el archivo {final} en el reproductor y repite") from None


def prepare_partial(path: Path) -> None:
    """Clear the place of a partial file before it is written: a folder there is a ProjectError,
    an old file is deleted, and one the system will not let go (read only, open in another
    program) is a ProjectError that says so (001.25, point 11). Never an unexpected failure."""
    refuse_directory(path)
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise ProjectError(f"no pude borrar {path}: {exc}; ciérralo o bórralo y repite") from None


def discard_partial(path: Path) -> None:
    """Delete a partial file at the end, whatever happened: it never hides the error that ended
    the work, and a file that stays is only a file that stays."""
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)


if sys.platform == "win32":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
