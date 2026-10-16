"""External process helpers: argument lists only, one stderr file per child (spec 0.8, 0.11)."""

import os
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import IO, NoReturn, Self

from kcut.errors import MissingDependency, ToolError
from kcut.scrub import scrub_media_metadata as scrub_media_metadata
from kcut.toolpath import tool_path as tool_path

_TAIL_LINES = 20
_DEFAULT_GRACE_S = 5.0
_LOG_LOCKS: dict[str, threading.Lock] = {}
_LOG_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class RunResult:
    """Outcome of `run`. `stderr` is the child's raw stderr only with `capture_stderr=True`."""

    returncode: int
    stdout: bytes
    stderr: str


class ChildProcess:
    """A running child whose stderr goes to its own temp file and joins the log when it ends."""

    def __init__(
        self,
        args: list[str],
        *,
        log: Path | None,
        stdin_pipe: bool,
        stdout_pipe: bool,
        grace_s: float = _DEFAULT_GRACE_S,
    ) -> None:
        _validate(args)
        self._args = args
        self._exit_grace_s = grace_s
        self._log = log
        self._start = time.monotonic()
        self._note = ""
        self._stderr_text: str | None = None
        self._stderr_file: IO[bytes] = tempfile.TemporaryFile()  # noqa: SIM115 - lives with the child
        try:
            self._popen = subprocess.Popen(
                args,
                stdin=subprocess.PIPE if stdin_pipe else subprocess.DEVNULL,
                stdout=subprocess.PIPE if stdout_pipe else subprocess.DEVNULL,
                stderr=self._stderr_file,
                shell=False,
            )
        except FileNotFoundError:
            self._stderr_file.close()
            raise MissingDependency(f"no existe el programa: {args[0]}") from None
        except OSError as exc:
            self._stderr_file.close()
            raise ToolError(f"no pude arrancar {_name(args)}: {exc}") from None
        if log is not None:
            _log_append(log, "$ " + subprocess.list2cmdline(args) + "\n")

    @property
    def stdin(self) -> IO[bytes] | None:
        return self._popen.stdin

    @property
    def stdout(self) -> IO[bytes] | None:
        return self._popen.stdout

    @property
    def pid(self) -> int:
        return self._popen.pid

    def wait(self, timeout_s: float | None = None, grace_s: float = _DEFAULT_GRACE_S) -> int:
        """Wait for the child. On timeout: kill it and raise ToolError without waiting forever."""
        try:
            code = self._popen.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            self._popen.kill()
            try:
                self._popen.wait(timeout=grace_s)
            except subprocess.TimeoutExpired:
                self._note = "[aviso] el proceso no murio tras kill()"
            self._abandon(timeout_s)
        except KeyboardInterrupt:
            self._interrupted(grace_s)
            raise
        self._finalize()
        return code

    def kill(self) -> None:
        self._popen.kill()

    def stderr_tail(self, n: int = _TAIL_LINES) -> str:
        """Last `n` stderr lines of this child only, scrubbed. Empty until the child is done."""
        if self._stderr_text is None:
            return ""
        return "\n".join(scrub_media_metadata(self._stderr_text).splitlines()[-n:])

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.kill()
            self._popen.wait()
        elif self._popen.poll() is None:
            try:
                self._popen.wait(timeout=self._exit_grace_s)
            except subprocess.TimeoutExpired:
                self._popen.kill()
                self._popen.wait()
                self._finalize()
                raise ToolError(f"el proceso {self.pid} no se espero: se mato al salir") from None
        self._finalize()

    def _communicate(self, timeout_s: float | None, grace_s: float) -> bytes:
        popen = self._popen
        try:
            out, _ = popen.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            popen.kill()
            try:
                popen.communicate(timeout=grace_s)
            except subprocess.TimeoutExpired:
                self._note = "[aviso] un proceso nieto mantiene el pipe abierto; no se espero mas"
            self._abandon(timeout_s)
        except KeyboardInterrupt:
            self._interrupted(grace_s)
            raise
        except BaseException:
            popen.kill()
            popen.wait()
            self._finalize()
            raise
        self._finalize()
        return out or b""

    def _abandon(self, timeout_s: float | None) -> NoReturn:
        self._popen.poll()
        for stream in (self._popen.stdout, self._popen.stdin):
            if stream is not None:
                _close_without_waiting(stream)
        self._finalize()
        raise ToolError(f"{_name(self._args)} se paso del tiempo ({timeout_s:g} s)")

    def _interrupted(self, grace_s: float) -> None:
        try:
            self._popen.wait(timeout=grace_s)
        except subprocess.TimeoutExpired:
            self._popen.kill()
            self._popen.wait()
        self._finalize()

    def _finalize(self) -> None:
        """Move this child's stderr into the log (one block) and close its temp file."""
        if self._stderr_text is not None:
            return
        self._stderr_file.seek(0)
        raw = self._stderr_file.read()
        self._stderr_file.close()
        self._stderr_text = raw.decode("utf-8", errors="replace")
        if self._log is None:
            return
        code = self._popen.returncode
        elapsed = time.monotonic() - self._start
        body = scrub_media_metadata(self._stderr_text).replace("\r\n", "\n")
        if body and not body.endswith("\n"):
            body += "\n"
        footer = f"[exit {'?' if code is None else code} en {elapsed:.1f} s]\n"
        _log_append(self._log, body + (self._note + "\n" if self._note else "") + footer)


def run(
    args: list[str],
    *,
    log: Path | None = None,
    timeout_s: float | None = None,
    check: bool = True,
    capture_stderr: bool = False,
    grace_s: float = _DEFAULT_GRACE_S,
) -> RunResult:
    """Run to completion. stdout is captured; stderr goes to the log (and back if requested)."""
    child = ChildProcess(args, log=log, stdin_pipe=False, stdout_pipe=True)
    out = child._communicate(timeout_s, grace_s)
    code = child._popen.returncode
    if check and code != 0:
        raise ToolError(
            f"{_name(args)} terminó con error (código {code}). Últimas líneas de stderr:\n"
            f"{child.stderr_tail()}"
        )
    raw = (child._stderr_text or "") if capture_stderr else ""
    return RunResult(code, out, raw)


def popen(
    args: list[str],
    *,
    log: Path,
    stdin_pipe: bool = False,
    stdout_pipe: bool = False,
    grace_s: float = _DEFAULT_GRACE_S,
) -> ChildProcess:
    """Start a long-running child. Use it as a context manager and call `wait()`.

    Leaving the `with` without an exception while the child still runs waits `grace_s`, then
    kills it and raises ToolError: a child is never killed silently.
    """
    return ChildProcess(
        args, log=log, stdin_pipe=stdin_pipe, stdout_pipe=stdout_pipe, grace_s=grace_s
    )


def _close_without_waiting(stream: IO[bytes]) -> None:
    """Close a pipe from a helper thread: on Windows close() blocks while a reader holds it."""
    closer = threading.Thread(target=stream.close, daemon=True)
    closer.start()
    closer.join(0.2)


def _validate(args: object) -> None:
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        raise TypeError("args must be a list[str]; a shell string is never accepted")
    if not args:
        raise ValueError("args must not be empty")
    if not Path(args[0]).is_absolute():
        raise ValueError("args[0] debe ser una ruta absoluta: usa tool_path")


def _name(args: list[str]) -> str:
    return Path(args[0]).name


def _log_append(log: Path, text: str) -> None:
    """Append `text` to the log under a lock shared by every writer of that log path."""
    key = os.path.normcase(str(log.resolve()))
    with _LOG_LOCKS_GUARD:
        lock = _LOG_LOCKS.setdefault(key, threading.Lock())
    with lock:
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
