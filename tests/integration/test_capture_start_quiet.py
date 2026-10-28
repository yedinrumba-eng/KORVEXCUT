"""A driver of Playwright that is missing leaves the console clean (spec S1.7 step 0, 001.33
point 6; row 14). The exit 7 and the message of S1.6b row 32 were right, but stderr carried 47
lines of `Future exception was never retrieved`: the future of the transport of Playwright, which
nobody reads when the driver does not start. `_start` keeps the `asyncio` logger quiet while it
starts and collects that future before it lets the logger speak again.

The failure is a real one, as in `test_capture_start_oserror.py`: `compute_driver_executable` points
at an exe that does not exist. The message of asyncio comes out when the future is collected, which
can be after the test function ends, so each case runs in a process of its own and reads its stderr.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.integration.render_small_cases import small, small_base

__all__ = ["small", "small_base"]
NOISE = ("Future exception", "Traceback", "was never retrieved")
CHILD = """
import sys
from pathlib import Path

import playwright._impl._transport as transport

missing = Path(sys.argv[1]) / "driver que no existe" / "node.exe"
transport.compute_driver_executable = lambda: (str(missing), str(missing.with_name("cli.js")))
"""
SHOOTER = (
    CHILD
    + """
from kcut.errors import KcutError
from kcut.gfx.capture import Shooter

try:
    with Shooter("<html></html>", Path(sys.argv[1]) / "work", 30, (100, 100)):
        pass
except KcutError as exc:
    print(exc.exit_code, exc.message_es)
"""
)
COMMAND = (
    CHILD
    + """
from kcut import cli

sys.exit(cli.main(sys.argv[2:]))
"""
)


def _run(code: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", code, *args],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def test_playwright_start_quiet_the_shooter_gives_exit_7_and_stderr_has_no_asyncio_noise(
    tmp_path: Path,
) -> None:
    done = _run(SHOOTER, str(tmp_path))
    assert done.returncode == 0, done.stderr  # the child printed the error it caught
    assert done.stdout.startswith("7 Chromium no arrancó (")
    for text in NOISE:
        assert text not in done.stderr, done.stderr
    assert done.stderr.strip() == ""


@pytest.mark.ffmpeg
@pytest.mark.slow
@pytest.mark.parametrize("command", ["capture", "render"])
def test_playwright_start_quiet_the_commands_are_exit_7_with_the_message_and_no_asyncio_noise(
    small: Path, tmp_path: Path, command: str
) -> None:
    import json

    document = {
        "schema": "kcut.graphics/1",
        "captions": {"enabled": False},
        "cues": [{"id": "x", "component": "label", "start": 5, "end": 20, "params": {"text": "x"}}],
    }
    (small / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")
    args = ("graphics", "capture") if command == "capture" else ("render",)
    done = _run(COMMAND, str(tmp_path), *args, "--project", str(small))
    assert done.returncode == 7, done.stderr
    assert "Chromium no arrancó (" in done.stderr
    assert "corre kcut doctor para ver qué falta" in done.stderr
    for text in NOISE:
        assert text not in done.stderr, done.stderr
