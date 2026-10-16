"""kcut.proc: list-only arguments, stderr handling, error mapping (uses python itself as child)."""

import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kcut import proc
from kcut.errors import MissingDependency, ToolError

PY = sys.executable
SLEEPER = [PY, "-c", "import time; time.sleep(60)"]


class TestArgumentValidation:
    def test_run_rejects_a_shell_string(self) -> None:
        with pytest.raises(TypeError):
            proc.run("ffmpeg -version")  # type: ignore[arg-type]

    def test_run_rejects_non_string_items(self) -> None:
        with pytest.raises(TypeError):
            proc.run([PY, 3])  # type: ignore[list-item]

    def test_run_rejects_a_tuple(self) -> None:
        with pytest.raises(TypeError):
            proc.run((PY, "-V"))  # type: ignore[arg-type]

    def test_popen_rejects_a_shell_string(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            proc.popen("ffmpeg -version", log=tmp_path / "x.log")  # type: ignore[arg-type]

    def test_nothing_is_written_to_the_log_when_args_are_rejected(self, tmp_path: Path) -> None:
        log = tmp_path / "x.log"
        with pytest.raises(TypeError):
            proc.run("ffmpeg -version", log=log)  # type: ignore[arg-type]
        assert not log.exists()

    def test_empty_list_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            proc.run([])


class TestRun:
    def test_captures_stdout_bytes(self) -> None:
        result = proc.run([PY, "-c", "print('hola ñandú')"])
        assert result.returncode == 0
        assert b"hola" in result.stdout
        assert result.stderr == ""

    def test_capture_stderr_returns_text(self) -> None:
        code = "import sys; sys.stderr.buffer.write('aviso ñ\\n'.encode('utf-8'))"
        result = proc.run([PY, "-c", code], capture_stderr=True)
        assert result.stderr.strip() == "aviso ñ"

    def test_stderr_is_not_returned_unless_requested(self) -> None:
        result = proc.run([PY, "-c", "import sys; print('x', file=sys.stderr)"])
        assert result.stderr == ""

    def test_stderr_goes_to_the_log_with_header_and_footer(self, tmp_path: Path) -> None:
        log = tmp_path / "logs" / "cmd.log"
        proc.run([PY, "-c", "import sys; print('boom', file=sys.stderr)"], log=log)
        lines = log.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith("$ ")
        assert "boom" in lines
        assert lines[-1].startswith("[exit 0 en ")

    def test_capture_stderr_also_reaches_the_log(self, tmp_path: Path) -> None:
        log = tmp_path / "cmd.log"
        proc.run(
            [PY, "-c", "import sys; print('visto', file=sys.stderr)"], log=log, capture_stderr=True
        )
        assert "visto" in log.read_text(encoding="utf-8")

    def test_check_false_returns_the_code_and_logs_it(self, tmp_path: Path) -> None:
        log = tmp_path / "cmd.log"
        result = proc.run([PY, "-c", "raise SystemExit(3)"], log=log, check=False)
        assert result.returncode == 3
        assert "[exit 3 en " in log.read_text(encoding="utf-8")

    def test_failure_raises_tool_error_with_the_last_20_stderr_lines(self, tmp_path: Path) -> None:
        code = "import sys\nfor i in range(40): print(f'line {i}', file=sys.stderr)\nsys.exit(2)"
        with pytest.raises(ToolError) as info:
            proc.run([PY, "-c", code], log=tmp_path / "cmd.log")
        message = info.value.message_es
        assert "line 39" in message
        assert "line 20" in message
        assert "line 19" not in message
        assert info.value.exit_code == 4

    def test_failure_without_a_log_still_reports_stderr(self) -> None:
        code = "import sys; print('sin log', file=sys.stderr); sys.exit(1)"
        with pytest.raises(ToolError, match="sin log"):
            proc.run([PY, "-c", code])

    def test_failure_with_captured_stderr_reports_it(self) -> None:
        code = "import sys; print('capturado', file=sys.stderr); sys.exit(1)"
        with pytest.raises(ToolError, match="capturado"):
            proc.run([PY, "-c", code], capture_stderr=True)

    def test_tail_only_includes_this_command_when_the_log_is_shared(self, tmp_path: Path) -> None:
        log = tmp_path / "cmd.log"
        proc.run([PY, "-c", "import sys; print('viejo', file=sys.stderr)"], log=log)
        failing = "import sys; print('nuevo', file=sys.stderr); sys.exit(1)"
        with pytest.raises(ToolError) as info:
            proc.run([PY, "-c", failing], log=log)
        assert "nuevo" in info.value.message_es
        assert "viejo" not in info.value.message_es

    def test_missing_program_raises_missing_dependency(self, tmp_path: Path) -> None:
        with pytest.raises(MissingDependency):
            proc.run([str(tmp_path / "no-existe.exe")])

    def test_utf8_stderr_is_decoded_with_replacement(self, tmp_path: Path) -> None:
        code = "import sys; sys.stderr.buffer.write(b'ok \\xff\\xfe fin\\n')"
        result = proc.run([PY, "-c", code], capture_stderr=True)
        assert result.stderr.startswith("ok ")
        assert result.stderr.strip().endswith("fin")


class TestPopen:
    def test_pipes_wait_and_log(self, tmp_path: Path) -> None:
        log = tmp_path / "pipe.log"
        code = "import sys; sys.stdout.write(sys.stdin.read().upper()); print('e', file=sys.stderr)"
        with proc.popen([PY, "-c", code], log=log, stdin_pipe=True, stdout_pipe=True) as child:
            assert child.stdin is not None
            assert child.stdout is not None
            child.stdin.write(b"abc")
            child.stdin.close()
            assert child.stdout.read() == b"ABC"
            assert child.wait(timeout_s=30) == 0
            assert child.pid > 0
        text = log.read_text(encoding="utf-8")
        assert "e\n" in text.replace("\r\n", "\n")
        assert "[exit 0 en " in text

    def test_no_pipes_by_default(self, tmp_path: Path) -> None:
        with proc.popen([PY, "-c", "pass"], log=tmp_path / "p.log") as child:
            assert child.stdin is None
            assert child.stdout is None
            assert child.wait(timeout_s=30) == 0

    def test_stderr_tail_is_empty_until_the_child_is_done(self, tmp_path: Path) -> None:
        with proc.popen(SLEEPER, log=tmp_path / "s.log") as child:
            assert child.stderr_tail() == ""
            child.kill()
            child.wait(timeout_s=5)

    def test_missing_program_raises_missing_dependency(self, tmp_path: Path) -> None:
        with pytest.raises(MissingDependency):
            proc.popen([str(tmp_path / "no-existe.exe")], log=tmp_path / "m.log")


class TestCtrlC:
    """Spec 0.10.9: after Ctrl+C the parent waits a grace period, then kills the child."""

    def test_ctrl_c_during_communicate_kills_a_stubborn_child(self, tmp_path: Path) -> None:
        log = tmp_path / "sleep.log"
        child = proc.popen(SLEEPER, log=log, stdout_pipe=True)

        def interrupted(*_a: object, **_k: object) -> tuple[bytes, bytes]:
            raise KeyboardInterrupt

        child._popen.communicate = interrupted  # type: ignore[method-assign]
        with pytest.raises(KeyboardInterrupt):
            child._communicate(None, 0.3)
        assert child._popen.poll() is not None
        assert "[exit " in log.read_text(encoding="utf-8")


def test_rejects_relative_argv0(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A bare program name would be searched by the OS (cwd first): callers use tool_path."""
    spawned: list[object] = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: spawned.append(a))
    log = tmp_path / "x.log"
    message = re.escape("args[0] debe ser una ruta absoluta: usa tool_path")
    with pytest.raises(ValueError, match=message):
        proc.run(["ffmpeg", "-version"], log=log)
    with pytest.raises(ValueError, match=message):
        proc.popen(["ffmpeg"], log=log)
    for relative in ("./ffmpeg", "bin/ffmpeg.exe", ""):
        with pytest.raises(ValueError, match=message):
            proc.run([relative])
    assert spawned == []
    assert not log.exists()


def test_child_exit_alive_waits_grace_then_raises_tool_error(tmp_path: Path) -> None:
    """Leaving the with normally while the child lives: wait grace_s, kill, never silent."""
    started = time.monotonic()
    sleeper = [PY, "-c", "import time; time.sleep(30)"]
    with (
        pytest.raises(ToolError, match="no se espero") as info,
        proc.popen(sleeper, log=tmp_path / "a.log", grace_s=0.5) as child,
    ):
        pass
    assert time.monotonic() - started >= 0.4
    assert f"el proceso {child.pid} no se espero" in info.value.message_es
    assert child.wait(timeout_s=5) != 0
    assert "[exit " in (tmp_path / "a.log").read_text(encoding="utf-8")


def test_child_exit_finishing_in_time_is_not_an_error(tmp_path: Path) -> None:
    short = [PY, "-c", "import time; time.sleep(0.1)"]
    with proc.popen(short, log=tmp_path / "b.log", grace_s=2) as child:
        pass
    assert child.wait(timeout_s=5) == 0
    assert "[exit 0 en " in (tmp_path / "b.log").read_text(encoding="utf-8")


def test_child_exit_by_exception_kills_and_reraises_the_same_exception(tmp_path: Path) -> None:
    started = time.monotonic()
    with (
        pytest.raises(RuntimeError, match="boom"),
        proc.popen(SLEEPER, log=tmp_path / "c.log", grace_s=30) as child,
    ):
        raise RuntimeError("boom")
    assert time.monotonic() - started < 10
    assert child.wait(timeout_s=5) != 0
