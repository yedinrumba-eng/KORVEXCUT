"""`kcut qa` takes the lock `build-vN` without waiting (spec 001.51 point 9, row 34b).

`kcut build` calls `run_qa` with its own lock taken, so the lock of `kcut qa` lives in the command.
With the lock held by somebody else the exit is 6 and nothing is written in `qa/vN/`.
"""

from pathlib import Path

import pytest

from kcut.render.lock import OutputLock
from tests.integration.qa_helpers import VIDEO, built, copy_of
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["built"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]


def test_qa_locked_with_the_build_lock_taken_the_exit_is_6_and_nothing_is_written(
    built: Path, tmp_path: Path, kcut_json: Run
) -> None:
    root = copy_of(built, tmp_path)
    with OutputLock(root / ".kcut" / "locks", "build-v1"):
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 6 and doc["error"]["kind"] == "LockedError", doc
    assert not (root / "qa" / "v1").exists()


def test_qa_locked_a_name_that_is_not_a_video_of_salida_is_still_exit_2(
    built: Path, tmp_path: Path, kcut_json: Run
) -> None:
    root = copy_of(built, tmp_path)
    code, doc, _ = kcut_json("qa", "salida/otro.mp4", *project_args(root))
    assert code == 2 and doc["error"]["kind"] == "UsageError", doc
