"""The inventory lives in `.kcut/`, so it is never trusted: bad ids, slugs and paths are refused."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.ingest.inventory import (
    Clip,
    ClipAudio,
    Inventory,
    WorkFiles,
    load_inventory,
    save_inventory,
)
from tests.unit.media_fakes import make_video

Mutation = Callable[[dict[str, Any]], object]


def _valid() -> Inventory:
    clip = Clip(
        "a1",
        "crudo/cam a.mp4",
        "cam-a",
        "video_voz",
        "sha256:aaaaaaaa",
        10,
        12000,
        360,
        make_video(),
        ClipAudio("aac", 44100, 1, 0, 1, -3.0, False),
        None,
        WorkFiles(".kcut/proxy/a1_cam-a.mp4", ".kcut/wav16/a1_cam-a.wav", 540, 960),
        (),
    )
    doc = Clip("d1", "crudo/brief.txt", "brief", "doc", "sha256:bbbbbbbb", 3)
    return Inventory("2026-10-16T10:00:00", 30, (clip, doc), id_high={"a": 1, "d": 1})


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proyecto ñandú"
    (folder / ".kcut").mkdir(parents=True)
    return folder


def _written(root: Path, mutate: Mutation | None = None) -> Path:
    path = root / ".kcut" / "inventory.json"
    save_inventory(path, _valid())
    if mutate is not None:
        data = json.loads(path.read_text(encoding="utf-8"))
        mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _set_clip(**changes: Any) -> Mutation:
    return lambda d: d["clips"][0].update(changes)


def _set_work(**changes: Any) -> Mutation:
    return lambda d: d["clips"][0]["work"].update(changes)


def test_a_valid_inventory_loads(root: Path) -> None:
    assert load_inventory(_written(root), root) == _valid()


def test_the_root_defaults_to_two_levels_above_the_file(root: Path) -> None:
    assert load_inventory(_written(root)) == _valid()


@pytest.mark.parametrize(
    "bad_id",
    ["../../x", "a1\n", "A1", "a", "a1234567", "1a", "a-1", "a1 ", "aa1", "", "a\u0661"],
)
def test_ids_are_refused_unless_a_letter_and_one_to_six_digits(root: Path, bad_id: str) -> None:
    with pytest.raises(ProjectError, match="id"):
        load_inventory(_written(root, _set_clip(id=bad_id)), root)


def test_the_id_prefix_must_match_the_class(root: Path) -> None:
    with pytest.raises(ProjectError, match="prefijo"):
        load_inventory(_written(root, _set_clip(id="b1")), root)


@pytest.mark.parametrize("bad_slug", ["../x", "A", "", "a" * 41, "a\n", "a b", "ñ", "a/b"])
def test_slugs_are_refused(root: Path, bad_slug: str) -> None:
    with pytest.raises(ProjectError, match="slug"):
        load_inventory(_written(root, _set_clip(slug=bad_slug)), root)


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
        load_inventory(_written(root, _set_clip(file=bad_file)), root)


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
        load_inventory(_written(root, _set_work(**changes)), root)


def test_null_work_files_are_fine(root: Path) -> None:
    path = _written(root, _set_work(proxy=None, wav16=None))
    clip = load_inventory(path, root).clips[0]
    assert clip.work is not None
    assert (clip.work.proxy, clip.work.wav16) == (None, None)


@pytest.mark.parametrize(
    "high",
    [{"z": 1}, {"a": -1}, {"a": 1_000_000}, {"a": 0, "d": 1}, {"a": "1"}, {"a": 1.5}, {"a": True}],
)
def test_id_high_must_be_sane_and_cover_the_ids_present(root: Path, high: dict[str, Any]) -> None:
    with pytest.raises(ProjectError, match="id_high"):
        load_inventory(_written(root, lambda d: d.update(id_high=high)), root)


def test_a_missing_id_high_is_rebuilt_from_the_ids(root: Path) -> None:
    inv = load_inventory(_written(root, lambda d: d.pop("id_high")), root)
    assert dict(inv.id_high) == {"a": 1, "d": 1}


def test_duplicate_ids_are_refused(root: Path) -> None:
    def twin(data: dict[str, Any]) -> None:
        data["clips"][1].update(id="d1")
        data["clips"].append(dict(data["clips"][1]))

    with pytest.raises(ProjectError, match="repetido"):
        load_inventory(_written(root, twin), root)


def test_every_failure_is_a_project_error_with_exit_3_naming_the_file(root: Path) -> None:
    path = _written(root, _set_clip(id="../../x"))
    with pytest.raises(ProjectError, match=re.escape("inventory.json")) as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3


def test_the_writer_never_emits_an_id_high_that_the_reader_would_refuse(root: Path) -> None:
    inv = Inventory("x", 30, _valid().clips, id_high={})
    path = root / ".kcut" / "inventory.json"
    save_inventory(path, inv)
    assert dict(load_inventory(path, root).id_high) == {"a": 1, "d": 1}
