"""`.kcut` itself as a link (spec S1.8a step 0, 001.35 point 3; row 10).

`assert_in_cache` compared `.kcut` with itself, so a `.kcut` changed for a junction (or a symlink)
to a folder outside, after the project was opened, passed the guard: every path "inside" it was
really in the other folder. The guard now refuses the link the way `check_layout_inside` does when
the project is opened, and with it `assert_own_folder` and the `_discard` of the partial of a work
file (001.34 row 20), which delete nothing through it.
"""

import hashlib
import os
import shutil
from pathlib import Path

import pytest

from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.ingest.cache_guard import assert_in_cache, assert_own_folder
from kcut.ingest.workbuild import _discard
from kcut.paths import Layout
from kcut.project import Project
from tests.fixtures.links import make_dir_link

PARTIAL = f"a1_x.{os.getpid()}.partial.wav"


@pytest.fixture
def opened(tmp_path: Path) -> Project:
    """A project with its real `.kcut/wav48/`, as it was when it was opened."""
    root = tmp_path / "proyecto ñandú"
    (root / "crudo").mkdir(parents=True)
    (root / ".kcut" / "wav48").mkdir(parents=True)
    return Project(root, parse_config("", default_name="x"), Layout(root))


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    """The folder of somebody else that has a `wav48/` too, with a file that has the exact name
    of the partial and that has to be left alone."""
    folder = tmp_path / "ajeno"
    (folder / "wav48").mkdir(parents=True)
    (folder / "wav48" / PARTIAL).write_bytes(b"de otra persona")
    return folder


def _swap_kcut_for_a_link(project: Project, outside: Path) -> None:
    """After the project was opened: `.kcut` goes away and a link to `outside` takes its place."""
    shutil.rmtree(project.layout.cache)
    make_dir_link(project.layout.cache, outside)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_kcut_root_link_assert_in_cache_refuses_a_path_under_a_kcut_that_became_a_link(
    opened: Project, outside: Path
) -> None:
    _swap_kcut_for_a_link(opened, outside)
    with pytest.raises(ProjectError, match=r"\.kcut es un enlace"):
        assert_in_cache(opened, opened.layout.wav48 / "a1_x.wav")


def test_kcut_root_link_assert_own_folder_refuses_a_folder_under_it(
    opened: Project, outside: Path
) -> None:
    _swap_kcut_for_a_link(opened, outside)
    with pytest.raises(ProjectError, match=r"\.kcut es un enlace"):
        assert_own_folder(opened, opened.layout.wav48)


def test_kcut_root_link_the_message_does_not_name_the_path_or_the_label(
    opened: Project, outside: Path
) -> None:
    _swap_kcut_for_a_link(opened, outside)
    with pytest.raises(ProjectError) as info:
        assert_in_cache(opened, opened.layout.wav48 / PARTIAL, label="wav48 de a1")
    assert "ñandú" not in info.value.message_es and PARTIAL not in info.value.message_es


def test_kcut_root_link_discard_does_not_delete_the_file_outside_with_the_name_of_the_partial(
    opened: Project, outside: Path
) -> None:
    planted = outside / "wav48" / PARTIAL
    before = _sha256(planted)
    _swap_kcut_for_a_link(opened, outside)
    _discard(opened, opened.layout.wav48 / PARTIAL, "wav48 de a1")
    assert planted.is_file() and _sha256(planted) == before


def test_kcut_root_link_a_real_kcut_still_passes_and_its_partial_is_deleted(
    opened: Project,
) -> None:
    """The control: with a real `.kcut` the same calls pass and `_discard` does delete."""
    partial = opened.layout.wav48 / PARTIAL
    partial.write_bytes(b"mio")
    assert_in_cache(opened, partial)
    assert assert_own_folder(opened, opened.layout.wav48) == opened.layout.wav48
    _discard(opened, partial, "wav48 de a1")
    assert not partial.exists()
