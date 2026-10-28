"""The guard of the folders costs microseconds a frame (spec S1.8a step 0, 001.35 point 6; row 13).

`OverlaySource` runs the whole guard once, when it is made, and keeps the identity of `.kcut`,
`.kcut/build`, `build/vN` and `gfx/` (`os.lstat`: device and inode, and not a link or a reparse
point). Before each PNG it only compares those four with an `lstat` each, besides the
`lone_file_reason` of the PNG itself (S1.6b row 39). A folder that is not the one that was seen is a
ProjectError (exit 3), and nothing of what a link leads to is read. The whole guard took 1.6 ms a
frame (2.7 ms in the audit that asked for this): 18 000 frames of a 10-minute video are 30 to 49 s.

The render with a junction in the middle is in `tests/integration/test_overlay_folder_guard.py`.
"""

import json
import os
import shutil
import statistics
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np
import pytest

from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.gfx.capture_index import INDEX_NAME, png_name
from kcut.gfx.layer import folder_guard
from kcut.gfx.overlay import FOLDER_CHANGED, OverlaySource, folder_identity
from kcut.paths import Layout, lone_file_reason
from kcut.project import Project
from tests.fixtures.links import make_dir_link

W, H = 12, 8
MAX_MEDIAN_MS = 0.2  # the whole check of a frame, after the change (001.35, row 13)


def _png(path: Path) -> None:
    red = np.zeros((H, W, 4), np.uint8)
    red[:, :, :3], red[:, :, 3] = (0, 0, 255), 255
    done, data = cv2.imencode(".png", red)
    assert done
    path.write_bytes(data.tobytes())


class Setup:
    """A project with `.kcut/build/v1/gfx/` holding the PNG of frame 3, and an `OverlaySource`
    over it that counts how many times the whole guard ran."""

    def __init__(self, root: Path, *, watch: bool = True) -> None:
        self.root = root
        (root / "crudo").mkdir(parents=True)
        self.build_dir = root / ".kcut" / "build" / "v1"
        self.gfx = self.build_dir / "gfx"
        self.gfx.mkdir(parents=True)
        _png(self.gfx / png_name(3))
        index = self.gfx / INDEX_NAME
        index.write_text(json.dumps({"fps": 30, "frames": [3], "hash": "a" * 64}), encoding="utf-8")
        self.project = Project(root, parse_config("", default_name="x"), Layout(root))
        self.folders = {
            "kcut": self.project.layout.cache,
            "build": self.project.layout.build,
            "vN": self.build_dir,
            "gfx": self.gfx,
        }
        whole = folder_guard(self.project, self.build_dir, self.gfx)
        self.guard_calls = 0

        def counting() -> None:
            self.guard_calls += 1
            whole()

        watched = tuple(self.folders.values()) if watch else ()
        self.source = OverlaySource(index, W, H, guard=counting, watch=watched)

    def blend(self) -> None:
        self.source.blend(np.zeros((H, W, 3), np.uint8), 3)


@pytest.fixture
def setup(tmp_path: Path) -> Setup:
    return Setup(tmp_path / "proyecto ñandú")


def test_overlay_folder_guard_identity_the_whole_guard_runs_once_and_not_per_png(
    setup: Setup,
) -> None:
    assert setup.guard_calls == 1  # when the source was made
    for _ in range(5):
        setup.blend()
    assert setup.guard_calls == 1  # nothing changed: only identities were compared


@pytest.mark.parametrize("which", ["kcut", "build", "vN", "gfx"])
def test_overlay_folder_guard_identity_a_folder_changed_for_a_junction_is_exit_3_and_unread(
    setup: Setup, tmp_path: Path, which: str
) -> None:
    """Each of the four folders, swapped for a link to a folder outside that has a PNG of the same
    size and the same name: the blend is a ProjectError and the red of the PNG outside is not read
    (the parent of the folder outside is the same one, so every path leads to a red PNG)."""
    outside = tmp_path / "ajeno"
    for rel in ("", "build/v1/gfx", "v1/gfx", "gfx"):
        folder = outside / rel
        folder.mkdir(parents=True, exist_ok=True)
        _png(folder / png_name(3))
    setup.blend()  # fine until now
    folder = setup.folders[which]
    folder.rename(folder.with_name(f"{folder.name}-real"))
    make_dir_link(folder, outside)
    try:
        with pytest.raises(ProjectError) as info:
            setup.blend()
    finally:
        os.rmdir(folder)  # the link, not what it leads to
        folder.with_name(f"{folder.name}-real").rename(folder)
    assert info.value.exit_code == 3
    message = info.value.message_es
    assert "enlace" in message or "queda fuera de .kcut/" in message or message == FOLDER_CHANGED


def test_overlay_folder_guard_identity_the_whole_guard_says_why_when_it_can(setup: Setup) -> None:
    """On a mismatch the whole guard runs, so the message is the one of the guard (a link, or a
    folder that leaves `.kcut/`), not the bare `FOLDER_CHANGED`."""
    other = setup.root.parent / "ajeno"
    other.mkdir()
    folder = setup.gfx
    folder.rename(folder.with_name("gfx-real"))
    make_dir_link(folder, other)
    try:
        with pytest.raises(ProjectError, match=r"enlace|fuera de \.kcut"):
            setup.blend()
        assert setup.guard_calls == 2
    finally:
        os.rmdir(folder)
        folder.with_name("gfx-real").rename(folder)


@pytest.mark.parametrize("which", ["build", "vN", "gfx"])
def test_overlay_folder_guard_identity_a_real_folder_that_is_another_one_is_refused(
    setup: Setup, which: str
) -> None:
    """The folder is replaced by a new real folder: the whole guard has nothing against it, but it
    is not the one that was seen, so the render stops all the same (`FOLDER_CHANGED`)."""
    folder = setup.folders[which]
    folder.rename(folder.with_name(f"{folder.name}-old"))
    folder.mkdir()
    (setup.gfx / png_name(3)).parent.mkdir(parents=True, exist_ok=True)
    _png(setup.gfx / png_name(3))
    with pytest.raises(ProjectError) as info:
        setup.blend()
    assert info.value.exit_code == 3 and info.value.message_es == FOLDER_CHANGED


def test_overlay_folder_guard_identity_a_folder_that_is_gone_is_refused(setup: Setup) -> None:
    shutil.rmtree(setup.gfx)
    with pytest.raises(ProjectError) as info:
        setup.blend()
    assert info.value.exit_code == 3 and info.value.message_es == FOLDER_CHANGED


def test_overlay_folder_guard_identity_without_watch_the_whole_guard_runs_before_each_png(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path / "proyecto ñandú", watch=False)
    assert setup.guard_calls == 1
    for _ in range(3):
        setup.blend()
    assert setup.guard_calls == 4  # once at the start and once before each of the 3 PNGs


def test_overlay_folder_guard_identity_a_png_that_became_a_hard_link_is_still_refused(
    setup: Setup,
) -> None:
    """The lstat of the PNG itself (S1.6b row 39) is still there next to the identities."""
    outside = setup.root / "ajeno.png"
    _png(outside)
    (setup.gfx / png_name(3)).unlink()
    os.link(outside, setup.gfx / png_name(3))
    with pytest.raises(ProjectError, match="cambió durante el render"):
        setup.blend()


def test_overlay_folder_guard_identity_folder_identity_of_a_real_folder_a_link_and_a_file(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "real"
    folder.mkdir()
    identity = folder_identity(folder)
    assert identity is not None and identity == folder_identity(folder)
    assert identity == (os.lstat(folder).st_dev, os.lstat(folder).st_ino)
    link = tmp_path / "enlace"
    make_dir_link(link, folder)
    assert folder_identity(link) is None  # a link, to the same folder or not, is not a folder
    (tmp_path / "archivo").write_bytes(b"x")
    assert folder_identity(tmp_path / "archivo") is None
    assert folder_identity(tmp_path / "no-hay") is None
    other = tmp_path / "otra"
    other.mkdir()
    assert folder_identity(other) != identity


def test_overlay_folder_guard_identity_the_check_of_a_frame_is_under_0_2_ms(setup: Setup) -> None:
    """Row 13: the median of the whole check before a PNG (the four identities and the `lstat` of
    the PNG) is at most 0.2 ms. The old one, the whole guard, was 1.6 ms on this machine."""
    path = setup.gfx / png_name(3)

    def check() -> None:
        setup.source._folders_unchanged()
        assert lone_file_reason(os.lstat(path)) is None

    def median_ms(run: Callable[[], None]) -> float:
        samples = []
        for _ in range(500):
            started = time.perf_counter()
            run()
            samples.append((time.perf_counter() - started) * 1000)
        return statistics.median(samples)

    check()  # warm up
    assert median_ms(check) <= MAX_MEDIAN_MS
    whole = folder_guard(setup.project, setup.build_dir, setup.gfx)
    assert median_ms(whole) > MAX_MEDIAN_MS  # the check that was there before was above it
