"""`kcut mix` sweeps the orphan partial files of `.kcut/build/v*/` (spec S1.8b round 1, 001.37
point 11; row 34), as `kcut render` does. A `voice.f32.<pid>.partial` of a process that is gone
and is over a day old is deleted by the next mix; one of a process that is alive (a recent one)
stays. The rules of the sweep itself are in `tests/unit/test_sweep_build_partials.py`.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.integration.mix_helpers import BUILD, audio_project
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
TWO_DAYS_S = 2 * 86400


def _dead_pid() -> int:
    """The pid of a process that was started and has ended."""
    child = subprocess.Popen([sys.executable, "-I", "-c", "pass"])
    child.wait()
    return child.pid


def _age(path: Path, seconds: float) -> None:
    when = time.time() - seconds
    os.utime(path, (when, when))


def test_sweep_build_partials_the_next_mix_deletes_the_one_of_a_dead_pid_and_keeps_a_live_one(
    view_fresh: Path, kcut_json: Run
) -> None:
    root = audio_project(view_fresh, sfx=False, music=False)
    folder = root / BUILD
    folder.mkdir(parents=True)
    dead = folder / f"voice.f32.{_dead_pid()}.partial"
    live = folder / f"other.f32.{os.getpid()}.partial"  # not a name the mix writes
    for path in (dead, live):
        path.write_bytes(b"half a file")
    _age(dead, TWO_DAYS_S)  # it has been there since a mix that was killed
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)
    assert not dead.exists()  # swept
    assert live.read_bytes() == b"half a file"  # a process that is alive: recent, so it stays
    assert (folder / "voice.f32").is_file() and (folder / "mix.wav").is_file()
