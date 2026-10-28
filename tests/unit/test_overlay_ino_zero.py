"""An identity with `st_ino == 0` is not trusted (spec S1.8b step 0, 001.36 point 8; row 19).

`OverlaySource` keeps the `(st_dev, st_ino)` of four folders and compares them before each PNG.
FAT and exFAT have no inode: `st_ino` is 0 there, so the identity of a folder would be the same as
the one of any other folder, and a folder swapped for another would pass. When a watched folder has
0 the source goes back to the whole guard before each PNG, as it does without `watch`. Here
`os.lstat` of the overlay is patched to say 0 (all folders, or only one).
"""

import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut.errors import ProjectError
from kcut.gfx import overlay
from tests.fixtures.links import make_dir_link
from tests.unit.test_overlay_folder_guard_identity import Setup


class _InoZero:
    """The `os.stat_result` of the real `lstat`, but with `st_ino = 0`, as a FAT volume gives."""

    def __init__(self, real: os.stat_result) -> None:
        self._real = real
        self.st_ino = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def _zero_ino(monkeypatch: pytest.MonkeyPatch, only: Path | None = None) -> None:
    """Make `os.lstat`, as `kcut.gfx.overlay` sees it, give `st_ino = 0` (for every path, or for
    the one `only`). The rest of `os` is the real one."""
    real_lstat = os.lstat

    class _Os:
        def __getattr__(self, name: str) -> Any:
            return getattr(os, name)

        @staticmethod
        def lstat(path: Any) -> Any:
            info = real_lstat(path)
            return info if only is not None and Path(path) != only else _InoZero(info)

    monkeypatch.setattr(overlay, "os", _Os())


@pytest.fixture
def zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Setup:
    _zero_ino(monkeypatch)
    return Setup(tmp_path / "proyecto ñandú")


def test_overlay_ino_zero_the_identities_are_zero_and_the_whole_guard_runs_for_each_png(
    zero: Setup,
) -> None:
    assert all(ino == 0 for _, ino in zero.source._identities)  # the patch is what was saved
    assert zero.guard_calls == 1  # when the source was made
    for _ in range(5):
        zero.blend()
    assert zero.guard_calls == 6  # and once before each of the 5 PNGs


def test_overlay_ino_zero_a_folder_that_is_another_one_is_still_refused(zero: Setup) -> None:
    """Without the whole guard a real folder that replaces `gfx/` would have the same identity
    (0, and the same device) and pass; with it, a junction is told by the guard."""
    other = zero.root.parent / "ajeno"
    other.mkdir()
    zero.gfx.rename(zero.gfx.with_name("gfx-real"))
    make_dir_link(zero.gfx, other)
    try:
        with pytest.raises(ProjectError, match=r"enlace|fuera de \.kcut"):
            zero.blend()
    finally:
        os.rmdir(zero.gfx)
        zero.gfx.with_name("gfx-real").rename(zero.gfx)
    assert zero.guard_calls == 2


def test_overlay_ino_zero_one_folder_with_zero_is_enough_for_the_whole_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proyecto ñandú"
    _zero_ino(monkeypatch, only=root / ".kcut" / "build" / "v1" / "gfx")  # a volume of its own
    setup = Setup(root)
    assert [ino == 0 for _, ino in setup.source._identities] == [False, False, False, True]
    for _ in range(3):
        setup.blend()
    assert setup.guard_calls == 4


def test_overlay_ino_zero_with_real_inodes_the_identity_is_compared_and_the_guard_runs_once(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path / "proyecto ñandú")
    assert all(ino != 0 for _, ino in setup.source._identities)
    for _ in range(5):
        setup.source.blend(np.zeros((8, 12, 3), np.uint8), 3)
    assert setup.guard_calls == 1  # S1.8a-13 is still true when the file system has inodes
