"""`remove_tree` of `tests/tmp_cleanup.py` (spec S1.9b step 0, row 17; 001.45 point 3, 001.47 point
10): the folders that fixtures of a wide scope make with `tmp_path_factory.mktemp` are deleted when
the scope closes, read-only files included, and what cannot be deleted is a warning, not a failure.
"""

import os
import stat
import warnings
from pathlib import Path

import pytest

from tests.tmp_cleanup import remove_tree


def _tree(root: Path) -> Path:
    (root / "a" / "b").mkdir(parents=True)
    (root / "a" / "b" / "x.bin").write_bytes(b"x" * 100)
    (root / "a" / "y.txt").write_text("y", encoding="utf-8")
    return root


def test_tmp_cleanup_deletes_the_folder_and_everything_in_it(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "t")
    remove_tree(tree)
    assert not tree.exists()


def test_tmp_cleanup_deletes_read_only_files_too(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "t")
    for name in (tree / "a" / "b" / "x.bin", tree / "a" / "y.txt"):
        os.chmod(name, stat.S_IREAD)
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a warning here would be a failure of the test
        remove_tree(tree)
    assert not tree.exists()


def test_tmp_cleanup_a_folder_that_is_not_there_is_nothing_to_do(tmp_path: Path) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        remove_tree(tmp_path / "never made")


def test_tmp_cleanup_what_cannot_be_deleted_is_a_warning_not_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _tree(tmp_path / "t")

    def locked(_path: object, *_a: object, **_k: object) -> None:
        raise PermissionError(13, "Acceso denegado")

    monkeypatch.setattr(os, "unlink", locked)
    monkeypatch.setattr(os, "rmdir", locked)
    with pytest.warns(UserWarning, match="no pude borrar"):
        remove_tree(tree)  # it does not raise
    monkeypatch.undo()
    assert tree.exists()  # control: nothing was deleted, and the test goes on
    remove_tree(tree)
    assert not tree.exists()
