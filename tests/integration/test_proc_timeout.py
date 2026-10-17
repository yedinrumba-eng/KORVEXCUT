"""Hard timeout: a grandchild that keeps the stdout pipe open must not hang kcut (spec 0.8)."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from kcut import proc
from kcut.errors import ToolError

TIMEOUT_S = 1.0
GRACE_S = 1.0
GRANDCHILD_SLEEP_S = 60
# The venv python.exe on Windows is a launcher with the base interpreter as its child: killing the
# launcher leaves that child sleeping (an orphan). The base interpreter is a single process.
PY = str(getattr(sys, "_base_executable", None) or sys.executable)
NAP = "import time; time.sleep(60)  # kcut-test-sleeper"

# The child starts a grandchild that inherits its stdout pipe, reports the grandchild pid on
# stderr, then sleeps. After `kill()` of the child the grandchild still holds the pipe.
CHILD_CODE = (
    "import subprocess, sys, time\n"
    f"nap = 'import time; time.sleep({GRANDCHILD_SLEEP_S})  # kcut-test-sleeper'\n"
    "g = subprocess.Popen([sys.executable, '-c', nap])\n"
    "print('GRANDCHILD-PID %d' % g.pid, file=sys.stderr, flush=True)\n"
    f"time.sleep({GRANDCHILD_SLEEP_S})\n"
)


def _grandchild_pid(log: Path) -> int | None:
    if not log.exists():
        return None
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.startswith("GRANDCHILD-PID "):
            return int(line.split()[1])
    return None


def _kill_tree(pid: int) -> None:
    """Kill a process this test started (and, on Windows, its children)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
    else:
        os.kill(pid, signal.SIGKILL)


def _alive_on_windows(pid: int) -> bool:
    listing = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    return f'"{pid}"' in listing


def test_run_gives_up_when_a_grandchild_holds_the_pipe(tmp_path: Path) -> None:
    log = tmp_path / "timeout.log"
    started = time.monotonic()
    with pytest.raises(ToolError) as info:
        proc.run([PY, "-c", CHILD_CODE], log=log, timeout_s=TIMEOUT_S, grace_s=GRACE_S)
    elapsed = time.monotonic() - started
    grandchild = _grandchild_pid(log)
    try:
        if grandchild is None:
            pytest.skip("el nieto no se pudo lanzar: no hay forma de reproducir el pipe retenido")
        assert elapsed < TIMEOUT_S + GRACE_S + 3
        assert "se paso del tiempo" in info.value.message_es
        assert info.value.exit_code == 4
        assert "[exit " in log.read_text(encoding="utf-8")
    finally:
        if grandchild is not None:
            _kill_tree(grandchild)


def test_run_times_out_on_a_plain_sleeping_child(tmp_path: Path) -> None:
    started = time.monotonic()
    with pytest.raises(ToolError, match="se paso del tiempo"):
        proc.run(
            [PY, "-c", NAP],
            log=tmp_path / "plain.log",
            timeout_s=0.5,
            grace_s=GRACE_S,
        )
    assert time.monotonic() - started < 0.5 + GRACE_S + 3


def test_childprocess_wait_enforces_the_same_hard_timeout(tmp_path: Path) -> None:
    started = time.monotonic()
    with (
        proc.popen([PY, "-c", NAP], log=tmp_path / "w.log") as c,
        pytest.raises(ToolError, match="se paso del tiempo"),
    ):
        c.wait(timeout_s=0.5, grace_s=GRACE_S)
    assert time.monotonic() - started < 0.5 + GRACE_S + 3
    assert "[exit " in (tmp_path / "w.log").read_text(encoding="utf-8")


def test_leaving_the_with_block_by_exception_kills_the_child(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError), proc.popen([PY, "-c", NAP], log=tmp_path / "x.log") as child:
        raise RuntimeError("boom")
    assert child.wait(timeout_s=5) != 0


def test_killing_the_child_leaves_no_sleeping_interpreter(tmp_path: Path) -> None:
    """The process that sleeps must be the one kcut kills: no orphan survives the test."""
    pid_file = tmp_path / "pid.txt"
    code = "import os, sys, time; open(sys.argv[1], 'w').write(str(os.getpid())); " + NAP
    with proc.popen([PY, "-c", code, str(pid_file)], log=tmp_path / "o.log") as child:
        deadline = time.monotonic() + 20
        while not (pid_file.exists() and pid_file.read_text()) and time.monotonic() < deadline:
            time.sleep(0.05)
        sleeping = int(pid_file.read_text())
        child.kill()
        child.wait(timeout_s=10)
    try:
        assert sleeping == child.pid
        if sys.platform == "win32":
            assert not _alive_on_windows(sleeping)
    finally:
        if sleeping != child.pid:
            _kill_tree(sleeping)
