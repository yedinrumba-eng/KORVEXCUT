"""A work file and a mezzanine are looked at again after the ffmpeg (spec S1.7 step 0, 001.33
point 3; row 11). The ffmpeg takes minutes, and `.kcut/wav48` or `.kcut/mezz` can be changed for a
junction in the meantime. `_assert_in_cache` (with its `label`) is called for the target, the
partial and the sidecar once more right before `_land` and once more right before `land_sidecar`,
in `ingest/workbuild._build` and in `render/mezz_files.build_mezz`.

The tests change the folder for a junction to an empty folder outside, at the moment that matters,
in process: the render has to stop with exit 3, what is outside has to stay empty and the message
names the class and the clip (`wav48 de a1`), never the slug of the original file.

Before `_land` the hook runs just after the real ffmpeg and also puts a copy of the partial where
the junction leads, so the partial can be found through it (as an attacker's folder would have it):
the guard is what stops the render, and not a missing partial. Before the sidecar the hook runs
just after `_land`.
"""

import hashlib
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.ingest import workfiles
from kcut.render import mezz_files
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
__all__ = ["small", "small_base"]


def _slug(root: Path) -> str:
    """The slug of the original clip a1, from the name of its wav48 (`a1_<slug>.wav`)."""
    name = next((root / ".kcut" / "wav48").glob("a1_*.wav")).name
    return name.split("_", 1)[1].removesuffix(".wav")


def _junction(folder: Path, outside: Path) -> None:
    """Keep `folder` beside it as `<name>-real` and put a junction to `outside` in its place."""
    folder.rename(folder.with_name(f"{folder.name}-real"))
    make_dir_link(folder, outside)


def _restore(folder: Path) -> None:
    remove_dir_link(folder)
    real = folder.with_name(f"{folder.name}-real")
    if real.exists() and not folder.exists():
        real.rename(folder)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _after_the_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
    folder: Path,
    outside: Path,
    planted: dict[str, str] | None = None,
) -> list[int]:
    """After the first ffmpeg whose partial is in `folder`: junction, and a copy of the partial
    where it leads, with the exact name of the partial. The list gets one item when that happened;
    `planted` (001.34, row 20) gets the name and the sha256 of the copy at that moment."""
    done: list[int] = []
    real = proc.run

    def run(args: list[str], *rest: Any, **kwargs: Any) -> Any:
        result = real(args, *rest, **kwargs)
        for arg in args:
            path = Path(str(arg))
            if not done and ".partial." in path.name and path.parent.name == folder.name:
                done.append(1)
                _junction(folder, outside)
                shutil.copy2(folder.with_name(f"{folder.name}-real") / path.name, outside)
                if planted is not None:
                    planted[path.name] = _sha256(outside / path.name)
        return result

    monkeypatch.setattr(proc, "run", run)
    return done


def _after_land(
    monkeypatch: pytest.MonkeyPatch, module: Any, folder: Path, outside: Path
) -> list[int]:
    """Right after `module._land` moved the file in: junction (the sidecar is still to be made)."""
    done: list[int] = []
    real: Callable[..., Any] = module._land

    def land(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        if not done:
            done.append(1)
            _junction(folder, outside)
        return result

    monkeypatch.setattr(module, "_land", land)
    return done


def _render(small: Path, kcut_json: Run, folder: Path) -> tuple[int, dict[str, Any]]:
    try:
        code, doc, _ = kcut_json("render", "--no-graphics", *project_args(small))
    finally:
        _restore(folder)
    return code, doc


def _refused(code: int, doc: dict[str, Any], label: str, slug: str, outside: Path) -> None:
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    message = doc["error"]["message"]
    assert message.startswith(f"{label} queda fuera de .kcut/"), message
    assert slug not in message
    # nothing of kcut went through the junction: no file, no sidecar (the copy of the partial that
    # the hook planted may still be there, if the cleanup does not reach through the link)
    assert [p.name for p in outside.iterdir() if ".partial." not in p.name] == []


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    folder = tmp_path / "ajeno"
    folder.mkdir()
    return folder


def test_after_ffmpeg_guard_wav48_before_the_move_is_exit_3_and_the_outside_stays_empty(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, outside: Path
) -> None:
    slug, folder = _slug(small), small / ".kcut" / "wav48"
    shutil.rmtree(folder)  # the render makes the wav48 again
    done = _after_the_ffmpeg(monkeypatch, folder, outside)
    code, doc = _render(small, kcut_json, folder)
    assert done == [1]  # the junction went in where the test meant
    _refused(code, doc, "wav48 de a1", slug, outside)


def test_after_ffmpeg_guard_wav48_before_the_sidecar_is_exit_3_and_the_outside_stays_empty(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, outside: Path
) -> None:
    slug, folder = _slug(small), small / ".kcut" / "wav48"
    shutil.rmtree(folder)
    module = sys.modules[workfiles._build.__module__]  # where `_build` lives, split or not
    done = _after_land(monkeypatch, module, folder, outside)
    code, doc = _render(small, kcut_json, folder)
    assert done == [1]
    _refused(code, doc, "wav48 de a1", slug, outside)


def test_after_ffmpeg_guard_mezz_before_the_move_is_exit_3_and_the_outside_stays_empty(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, outside: Path
) -> None:
    slug, folder = _slug(small), small / ".kcut" / "mezz"
    shutil.rmtree(folder)  # the render makes the mezzanines again
    done = _after_the_ffmpeg(monkeypatch, folder, outside)
    code, doc = _render(small, kcut_json, folder)
    assert done == [1]
    _refused(code, doc, "mezz de a1", slug, outside)


def test_after_ffmpeg_guard_mezz_before_the_sidecar_is_exit_3_and_the_outside_stays_empty(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, outside: Path
) -> None:
    slug, folder = _slug(small), small / ".kcut" / "mezz"
    shutil.rmtree(folder)
    done = _after_land(monkeypatch, mezz_files, folder, outside)
    code, doc = _render(small, kcut_json, folder)
    assert done == [1]
    _refused(code, doc, "mezz de a1", slug, outside)


def _partial_left_alone(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, outside: Path, name: str
) -> None:
    """001.34, row 20: the folder becomes a junction after the ffmpeg and a file with the exact name
    of the partial is waiting outside. The render is exit 3 as before, and the `finally` that used
    to delete the partial reached through the junction and deleted that file: it must not."""
    slug, folder = _slug(small), small / ".kcut" / name
    shutil.rmtree(folder)
    planted: dict[str, str] = {}
    done = _after_the_ffmpeg(monkeypatch, folder, outside, planted)
    code, doc = _render(small, kcut_json, folder)
    assert done == [1] and len(planted) == 1
    _refused(code, doc, f"{name} de a1", slug, outside)
    left = {p.name: _sha256(p) for p in outside.iterdir()}
    assert left == planted, (left, planted)  # still there, the same bytes


def test_after_ffmpeg_guard_wav48_the_partial_outside_is_not_deleted_through_the_junction(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, outside: Path
) -> None:
    _partial_left_alone(small, kcut_json, monkeypatch, outside, "wav48")


def test_after_ffmpeg_guard_mezz_the_partial_outside_is_not_deleted_through_the_junction(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, outside: Path
) -> None:
    _partial_left_alone(small, kcut_json, monkeypatch, outside, "mezz")


def test_after_ffmpeg_guard_a_render_nobody_tampers_with_still_makes_both_files(
    small: Path, kcut_json: Run
) -> None:
    shutil.rmtree(small / ".kcut" / "wav48")
    shutil.rmtree(small / ".kcut" / "mezz")
    code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
    assert code == 0 and doc["mezz_built"] >= 1, (doc, err)
    assert list((small / ".kcut" / "wav48").glob("a1_*.wav.json"))
    assert list((small / ".kcut" / "mezz").glob("a1_*.mp4.json"))
