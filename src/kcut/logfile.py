"""The per-run command log: exclusive creation and checked appends (spec 0.11, 001.6, 001.7).

A log lives in `.kcut/logs/`, a folder a hostile project could fill with links. So the log is
created with `O_EXCL` under a unique name, and before **every** append it must still be a
regular file with a single link that resolves inside the real cache. If not, nothing is written
there: the text goes to stderr with a warning. A child's stderr block streams in through
`log_writer` (001.3) and passes the same checks as a one-shot `append_log`.

Writing a log never raises `OSError` or `UnicodeEncodeError` (001.7): a log that cannot be
opened, or that fails in the middle of a block, sends the rest of the text to stderr with a
single warning; a lone surrogate is written as "?". If stderr is also
gone (closed, or `None`), the text is dropped: logging never takes a command down. A run that
created its log and left it empty removes it at the end (`remove_if_empty`).
"""

import os
import stat
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from kcut.paths import is_inside

_LOG_LOCKS: dict[str, threading.Lock] = {}
_LOG_LOCKS_GUARD = threading.Lock()
_WARNED: set[str] = set()
_LOG_ROOT: Path | None = None
_BINARY = getattr(os, "O_BINARY", 0)  # Windows: no newline translation under the text we write


class LogSink(Protocol):
    """What a block of log text is written to: the log itself, or stderr when it is not safe."""

    def write(self, text: str, /) -> int: ...


@dataclass(frozen=True)
class CreatedLog:
    """A log this run created, with the identity of the file (`os.fstat` of the creating handle).

    `ino == -1` means the identity could not be read; such a log is never removed.
    """

    path: Path
    dev: int
    ino: int


def set_log_root(root: Path | None) -> None:
    """Folder (the real `.kcut/`) every log must resolve into; `None` removes the requirement."""
    global _LOG_ROOT
    _LOG_ROOT = None if root is None else root.resolve()


def create_run_log(log: Path) -> CreatedLog | None:
    """Create an empty log with `O_CREAT | O_EXCL` and remember which file it is.

    None if it exists or cannot be created. The identity comes from `os.fstat` on the handle that
    created it, so the end of the run can tell this file from one swapped in afterwards.
    """
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(log, os.O_CREAT | os.O_EXCL | os.O_WRONLY | _BINARY)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
    except OSError:
        return CreatedLog(log, -1, -1)
    finally:
        _close(fd)
    return CreatedLog(log, info.st_dev, info.st_ino)


def create_log(log: Path) -> bool:
    """Create an empty log with `O_CREAT | O_EXCL`. False if it exists or cannot be created."""
    return create_run_log(log) is not None


def remove_if_empty(created: CreatedLog) -> bool:
    """Delete the log this run created if nothing was written to it. True if it was deleted.

    Only the very same file goes (same device and inode as at creation), and only a regular
    file with a single link and size 0: anything else was swapped in or written to by someone,
    and is left alone. Never raises.
    """
    if created.ino <= 0:
        return False
    with _lock_for(created.path):
        try:
            info = os.lstat(created.path)
            same = (info.st_dev, info.st_ino) == (created.dev, created.ino)
            if not (same and stat.S_ISREG(info.st_mode) and info.st_nlink == 1):
                return False
            if info.st_size != 0:
                return False
            os.unlink(created.path)
        except OSError:
            return False
    return True


def unsafe_reason(log: Path) -> str | None:
    """Why `log` must not be appended to, or None if it is safe (a missing file is fine)."""
    try:
        info = os.lstat(log)
    except FileNotFoundError:
        info = None
    except OSError as exc:
        return str(exc)
    if info is not None:
        if not stat.S_ISREG(info.st_mode):
            return "no es un archivo regular (enlace o carpeta)"
        if info.st_nlink != 1:
            return f"tiene {info.st_nlink} enlaces duros"
    if _LOG_ROOT is not None and not is_inside(_LOG_ROOT, log.resolve()):
        return "queda fuera de .kcut/"
    return None


def append_log(log: Path, text: str) -> bool:
    """Append `text` to a command log as one block (see `log_writer`). Never raises `OSError`.

    True if the text is in the log; False if it went to stderr instead (or was dropped).
    """
    with log_writer(log) as fh:
        fh.write(text)
        return isinstance(fh, _FdSink) and not fh.failed


@contextmanager
def log_writer(log: Path) -> Iterator[LogSink]:
    """Yield a sink that appends one block to `log`; the caller may write it in pieces.

    The whole block goes under the per-path lock shared by every writer of that log, after the
    checks every append passes: `unsafe_reason`, then the open handle must still be a lone regular
    file. If a check fails, or the log cannot be opened, the sink is stderr, with a warning printed
    once per log. An `OSError` while writing moves the rest of the text to stderr the same way.
    """
    with _lock_for(log):
        fd, reason = _open_checked(log)
        if fd is None:
            yield _to_stderr(log, reason)
            return
        try:
            yield _FdSink(log, fd)
        finally:
            _close(fd)


class _FdSink:
    """Writes straight to an open log. Nothing is buffered, so an `OSError` shows up in the very
    `write` that hit it; from then on that text and all that follows go to stderr."""

    def __init__(self, log: Path, fd: int) -> None:
        self._log = log
        self._fd = fd
        self.failed = False

    def write(self, text: str, /) -> int:
        if not self.failed:
            data = text.encode("utf-8", errors="replace")
            done = 0
            try:
                while done < len(data):
                    written = os.write(self._fd, data[done:])
                    if written <= 0:
                        raise OSError("el sistema no escribio ningun byte")
                    done += written
            except OSError as exc:
                self.failed = True
                _warn_once(self._log, str(exc))
                text = data[done:].decode("utf-8", errors="replace")
            else:
                return len(text)
        _stderr_write(text)
        return len(text)


def _lock_for(log: Path) -> threading.Lock:
    try:
        key = os.path.normcase(str(log.resolve()))
    except OSError:
        key = os.path.normcase(str(log))
    with _LOG_LOCKS_GUARD:
        return _LOG_LOCKS.setdefault(key, threading.Lock())


def _open_checked(log: Path) -> tuple[int | None, str]:
    """Open `log` for appending if that is safe: `(fd, "")`, or `(None, why not)`."""
    try:
        reason = unsafe_reason(log)
        if reason is not None:
            return None, reason
        log.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT | _BINARY)
    except OSError as exc:
        return None, str(exc)
    try:
        info = os.fstat(fd)
    except OSError as exc:
        _close(fd)
        return None, str(exc)
    if stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
        return fd, ""
    _close(fd)
    return None, f"tiene {info.st_nlink} enlaces duros"


def _close(fd: int) -> None:
    with suppress(OSError):
        os.close(fd)


class _StderrSink:
    """Stands in for a log that is not written: its text goes to stderr, if stderr still works."""

    def write(self, text: str, /) -> int:
        _stderr_write(text)
        return len(text)


def _stderr_write(text: str) -> None:
    """Write to the current `sys.stderr`; if it is `None`, closed or broken, drop the text."""
    stream = sys.stderr
    if stream is None:
        return
    try:  # a lone surrogate would make the stream raise: write it as "?" like the log does
        stream.write(text.encode("utf-8", errors="replace").decode("utf-8"))
    except (OSError, ValueError):
        return


def _to_stderr(log: Path, reason: str) -> LogSink:
    """Warn once per log that it is not written, and hand back a sink that goes to stderr."""
    _warn_once(log, reason)
    return _StderrSink()


def _warn_once(log: Path, reason: str) -> None:
    key = os.path.normcase(str(log))
    if key not in _WARNED:
        _WARNED.add(key)
        _stderr_write(f"[AVISO] no escribo en el log {log}: {reason}\n")
