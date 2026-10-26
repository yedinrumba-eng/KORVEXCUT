"""Ids, slugs, paths and `id_high` of an inventory from `.kcut/` are checked, never trusted."""

import re
from pathlib import Path
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.ingest.inventory import Inventory, load_inventory, save_inventory
from tests.unit.inventory_fakes import (
    set_clip,
    set_work,
    valid_inventory,
    written,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proyecto ñandú"
    (folder / ".kcut").mkdir(parents=True)
    return folder


@pytest.mark.parametrize(
    "bad_id",
    ["../../x", "a1\n", "A1", "a", "a1234567", "1a", "a-1", "a1 ", "aa1", "", "a\u0661"],
)
def test_ids_are_refused_unless_a_letter_and_one_to_six_digits(root: Path, bad_id: str) -> None:
    with pytest.raises(ProjectError, match="id"):
        load_inventory(written(root, set_clip(id=bad_id)), root)


def test_the_id_prefix_must_match_the_class(root: Path) -> None:
    with pytest.raises(ProjectError, match="prefijo"):
        load_inventory(written(root, set_clip(id="b1")), root)


@pytest.mark.parametrize("bad_slug", ["../x", "A", "", "a" * 41, "a\n", "a b", "ñ", "a/b"])
def test_slugs_are_refused(root: Path, bad_slug: str) -> None:
    with pytest.raises(ProjectError, match="slug"):
        load_inventory(written(root, set_clip(slug=bad_slug)), root)


@pytest.mark.parametrize(
    "bad_file",
    [
        "../x.mov",
        "crudo/../../x.mov",
        "crudo/../edit/estrategia.md",
        "edit/estrategia.md",
        "crudo",
        "crudo/",
        "C:/Windows/x.mov",
        "//servidor/recurso/x.mov",
        "crudo/./cam a.mp4",
        "crudo/sub/../cam a.mp4",
        "crudo/a:b.mov",
        "",
    ],
)
def test_files_must_be_canonical_paths_under_crudo(root: Path, bad_file: str) -> None:
    with pytest.raises(ProjectError, match=r"file"):
        load_inventory(written(root, set_clip(file=bad_file)), root)


@pytest.mark.parametrize(
    ("changes", "fragment"),
    [
        ({"wav16": "crudo/cam a.mp4"}, "wav16"),
        ({"wav16": "../../x.wav"}, "wav16"),
        ({"wav16": ".kcut/proxy/a1_cam-a.wav"}, "wav16"),
        ({"wav16": ".kcut/wav16/../../crudo/cam a.mp4"}, "wav16"),
        ({"wav16": ".kcut/wav16"}, "wav16"),
        ({"proxy": "crudo/cam a.mp4"}, "proxy"),
        ({"proxy": ".kcut/wav16/a1_cam-a.mp4"}, "proxy"),
        ({"proxy": "C:/x.mp4"}, "proxy"),
    ],
)
def test_work_files_must_live_in_their_own_cache_folder(
    root: Path, changes: dict[str, Any], fragment: str
) -> None:
    with pytest.raises(ProjectError, match=fragment):
        load_inventory(written(root, set_work(**changes)), root)


def test_null_work_files_are_fine(root: Path) -> None:
    path = written(root, set_work(proxy=None, wav16=None))
    clip = load_inventory(path, root).clips[0]
    assert clip.work is not None
    assert (clip.work.proxy, clip.work.wav16) == (None, None)


@pytest.mark.parametrize(
    "high",
    [{"z": 1}, {"a": -1}, {"a": 1_000_000}, {"a": 0, "d": 1}, {"a": "1"}, {"a": 1.5}, {"a": True}],
)
def test_id_high_must_be_sane_and_cover_the_ids_present(root: Path, high: dict[str, Any]) -> None:
    with pytest.raises(ProjectError, match="id_high"):
        load_inventory(written(root, lambda d: d.update(id_high=high)), root)


def test_a_missing_id_high_is_rebuilt_from_the_ids(root: Path) -> None:
    inv = load_inventory(written(root, lambda d: d.pop("id_high")), root)
    assert dict(inv.id_high) == {"a": 2, "d": 1, "s": 2}


def test_duplicate_ids_are_refused(root: Path) -> None:
    def twin(data: dict[str, Any]) -> None:
        data["clips"][1].update(id="d1")
        data["clips"].append(dict(data["clips"][1]))

    with pytest.raises(ProjectError, match="repetido"):
        load_inventory(written(root, twin), root)


def test_every_failure_is_a_project_error_with_exit_3_naming_the_file(root: Path) -> None:
    path = written(root, set_clip(id="../../x"))
    with pytest.raises(ProjectError, match=re.escape("inventory.json")) as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3


def test_the_writer_never_emits_an_id_high_that_the_reader_would_refuse(root: Path) -> None:
    inv = Inventory("x", 30, valid_inventory().clips, id_high={})
    path = root / ".kcut" / "inventory.json"
    save_inventory(path, inv)
    assert dict(load_inventory(path, root).id_high) == {"a": 2, "d": 1, "s": 2}
