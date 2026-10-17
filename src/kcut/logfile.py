"""The per-run command log: exclusive creation and checked appends (spec 0.11, 001.6).

A log lives in `.kcut/logs/`, a folder a hostile project could fill with links. So the log is
created with `O_EXCL` under a unique name, and before **every** append it must still be a
regular file with a single link that resolves inside the real cache. If not, nothing is written
there: the text goes to stderr with a warning.
"""

import os
import stat
import sys
import threading
from pathlib import Path

from kcut.paths import is_inside

_LOG_LOCKS: dict[str, threading.Lock] = {}
_LOG_LOCKS_GUARD = threading.Lock()
_WARNED: set[str] = set()
_LOG_ROOT: Path | None = None
_BINARY = getattr(os, "O_BINARY", 0)  # Windows: keep the text layer's newlines as they are


def set_log_root(root: Path | None) -> None:
    """Folder (the real `.kcut/`) every log must resolve into; `None` removes the requirement."""
    global _LOG_ROOT
    _LOG_ROOT = None if root is None else root.resolve()


def create_log(log: Path) -> bool:
    """Create an empty log with `O_CREAT | O_EXCL`. False if it exists or cannot be created."""
    try:
        log.parent.mkdir(parents=True, exist_ok=True)
        os.close(os.open(log, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
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


def append_log(log: Path, text: str) -> None:
    """Append `text` to a command log under the per-path lock shared by every writer of it."""
    key = os.path.normcase(str(log.resolve()))
    with _LOG_LOCKS_GUARD:
        lock = _LOG_LOCKS.setdefault(key, threading.Lock())
    with lock:
        reason = unsafe_reason(log)
        if reason is None:
            reason = _append_checked(log, text)
        if reason is not None:
            _to_stderr(log, reason, text)


def _append_checked(log: Path, text: str) -> str | None:
    """Open for append, confirm on the open handle that it is still a lone regular file, write."""
    log.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT | _BINARY)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return f"tiene {info.st_nlink} enlaces duros"
        with os.fdopen(fd, "a", encoding="utf-8", newline="\n", closefd=False) as fh:
            fh.write(text)
    finally:
        os.close(fd)
    return None


def _to_stderr(log: Path, reason: str, text: str) -> None:
    key = os.path.normcase(str(log))
    if key not in _WARNED:
        _WARNED.add(key)
        print(f"[AVISO] no escribo en el log {log}: {reason}", file=sys.stderr)
    sys.stderr.write(text)
