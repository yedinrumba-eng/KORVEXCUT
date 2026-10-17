"""`logfile.log_writer` never raises `OSError`: what it cannot write goes to stderr (001.7)."""

import io
import os
import sys
from pathlib import Path

import pytest

from kcut import logfile, proc
from kcut.logfile import CreatedLog, append_log, create_run_log, log_writer, remove_if_empty

PY = str(getattr(sys, "_base_executable", None) or sys.executable)


def test_log_oserror_in_the_middle_of_a_block_sends_the_rest_to_stderr_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    real_write, calls = os.write, []

    def flaky(fd: int, data: bytes) -> int:
        calls.append(len(data))
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        return real_write(fd, data)

    log = tmp_path / "mitad.log"
    monkeypatch.setattr(os, "write", flaky)
    with log_writer(log) as sink:
        for piece in ("uno\n", "dos\n", "tres\n"):
            sink.write(piece)
    monkeypatch.undo()
    assert log.read_text(encoding="utf-8") == "uno\n"
    err = capsys.readouterr().err
    assert "dos\ntres\n" in err and err.count("[AVISO]") == 1 and "No space left" in err


def test_log_oserror_on_open_falls_back_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> int:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(logfile.os, "open", refuse)
    with log_writer(tmp_path / "cerrado.log") as sink:
        sink.write("lo que no cabe\n")
    monkeypatch.undo()
    err = capsys.readouterr().err
    assert "lo que no cabe" in err and "Permission denied" in err
    assert not (tmp_path / "cerrado.log").exists()


def test_log_oserror_on_fstat_closes_the_handle_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def refuse(_fd: int) -> os.stat_result:
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(logfile.os, "fstat", refuse)
    with log_writer(tmp_path / "x.log") as sink:
        sink.write("texto\n")
    monkeypatch.undo()
    assert "Input/output error" in capsys.readouterr().err


def test_empty_log_remove_if_empty_checks_the_identity_and_the_content(tmp_path: Path) -> None:
    made = create_run_log(tmp_path / "a.log")
    assert made is not None and made.ino > 0
    assert not remove_if_empty(CreatedLog(made.path, made.dev, made.ino + 1))  # another file
    assert made.path.is_file()
    append_log(made.path, "x")
    assert not remove_if_empty(made) and made.path.read_text(encoding="utf-8") == "x"
    empty = create_run_log(tmp_path / "b.log")
    assert empty is not None and remove_if_empty(empty) and not empty.path.exists()
    assert not remove_if_empty(empty)  # already gone: no error


def _break_stderr(monkeypatch: pytest.MonkeyPatch, how: str) -> None:
    if how == "none":
        monkeypatch.setattr(sys, "stderr", None)
        return
    gone = io.StringIO()
    gone.close()
    monkeypatch.setattr(sys, "stderr", gone)


@pytest.mark.parametrize("how", ["none", "closed"])
def test_a_log_that_cannot_be_written_and_a_stderr_that_is_gone_drop_the_text_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    """Logging never takes a command down: with no log and no stderr the text is just dropped."""
    blocker = tmp_path / "logs"
    blocker.write_text("soy un archivo", encoding="utf-8")
    _break_stderr(monkeypatch, how)
    append_log(blocker / "x.log", "texto\n")
    with log_writer(blocker / "y.log") as sink:
        assert sink.write("mas texto\n") == len("mas texto\n")
    assert blocker.read_text(encoding="utf-8") == "soy un archivo"


@pytest.mark.parametrize("how", ["none", "closed"])
def test_a_log_that_fails_midway_and_a_stderr_that_is_gone_drop_the_rest_quietly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, how: str
) -> None:
    real_write, calls = os.write, []

    def flaky(fd: int, data: bytes) -> int:
        calls.append(len(data))
        if len(calls) == 2:
            raise OSError(28, "No space left on device")
        return real_write(fd, data)

    log = tmp_path / "mitad.log"
    _break_stderr(monkeypatch, how)
    monkeypatch.setattr(os, "write", flaky)
    with log_writer(log) as sink:
        for piece in ("uno\n", "dos\n", "tres\n"):
            sink.write(piece)
    monkeypatch.undo()
    assert log.read_text(encoding="utf-8") == "uno\n"


def test_surrogate_append_log_writes_a_replacement_and_does_not_raise(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    assert append_log(log, "x\ud800y\n") is True
    assert log.read_bytes() == b"x?y\n"


def test_surrogate_in_a_child_argument_does_not_raise(tmp_path: Path) -> None:
    """A file name with a lone surrogate reaches the `$ ...` header of the log (001.7)."""
    log = tmp_path / "hijo.log"
    proc.run([PY, "-c", "pass", "clip\ud800.mov"], log=log)
    text = log.read_text(encoding="utf-8")
    assert text.startswith("$ ") and "clip?.mov" in text and "[exit 0" in text


def test_surrogate_in_the_stderr_fallback_is_replaced_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "logs"
    blocker.write_text("soy un archivo", encoding="utf-8")
    assert append_log(blocker / "x.log", "a\ud800b\n") is False
    assert "a?b" in capsys.readouterr().err


def test_append_log_says_whether_the_text_reached_the_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert append_log(tmp_path / "ok.log", "dentro\n") is True
    (tmp_path / "carpeta.log").mkdir()
    assert append_log(tmp_path / "carpeta.log", "fuera\n") is False  # not a regular file

    def full_disk(fd: int, data: bytes) -> int:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "write", full_disk)
    assert append_log(tmp_path / "lleno.log", "perdido\n") is False  # failed in the write
