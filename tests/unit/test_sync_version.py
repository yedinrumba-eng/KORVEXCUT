"""A stored sync result carries the version of the algorithm that measured it (001.7, point 15)."""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.ingest import sync as sync_module
from kcut.ingest import sync_stage
from kcut.ingest.inventory import (
    Clip,
    Inventory,
    SyncInfo,
    SyncMember,
    SyncRejected,
    load_inventory,
    save_inventory,
)

MASTER = Clip("s1", "crudo/a.wav", "a", "audio", "sha256:aaaaaaaa", 10)
MEMBER = Clip("s2", "crudo/b.wav", "b", "audio", "sha256:bbbbbbbb", 10)


def _previous(sync: SyncInfo, member_qhash: str = "sha256:bbbbbbbb") -> Inventory:
    member = Clip("s2", "crudo/b.wav", "b", "audio", member_qhash, 10)
    return Inventory("x", 30, (MASTER, member), sync=sync)


def _accepted(*version: int) -> SyncInfo:
    entry = SyncMember("s2", 2000, 0.9, 0.3, 3.0, 0, 9, "envelope+raw", 0.99, *version)
    return SyncInfo("s1", (entry,))


def _rejected(*version: int) -> SyncInfo:
    entry = SyncRejected("s2", 0.9, 4.0, "sync_ambiguous: x", 0.85, -2800, 4000, *version)
    return SyncInfo("s1", (), (entry,))


def _reuse(sync: SyncInfo, qhash: str = "sha256:bbbbbbbb") -> object:
    return sync_stage._reusable(_previous(sync, qhash), MASTER, MEMBER, 0.1)


def test_sync_version_001_7_is_version_2() -> None:
    assert sync_module.SYNC_VERSION == 2


@pytest.mark.parametrize("make", [_accepted, _rejected])
def test_sync_version_the_current_one_with_the_same_qhash_is_reused(make: Any) -> None:
    sync = make(sync_module.SYNC_VERSION)
    assert _reuse(sync) is (sync.members or sync.rejected)[0]


@pytest.mark.parametrize("make", [_accepted, _rejected])
@pytest.mark.parametrize("version", [1, 3, 1000])
def test_sync_version_another_one_is_measured_again(make: Any, version: int) -> None:
    assert _reuse(make(version)) is None


@pytest.mark.parametrize("make", [_accepted, _rejected])
def test_sync_version_missing_counts_as_version_1(make: Any) -> None:
    assert make()  # built without a version: the default is 1, the version of 001.6 and before
    assert _reuse(make()) is None


@pytest.mark.parametrize("make", [_accepted, _rejected])
def test_sync_version_never_overrides_a_changed_qhash(make: Any) -> None:
    assert _reuse(make(sync_module.SYNC_VERSION), "sha256:cccccccc") is None


def _saved(tmp_path: Path, change: Any = None) -> Path:
    path = tmp_path / "inventory.json"
    sync = SyncInfo("s1", _accepted(2).members, _rejected(2).rejected)
    save_inventory(path, Inventory("x", 30, (MASTER, MEMBER), sync=sync))
    if change is not None:
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data["sync"])
        path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_sync_version_is_written_and_read_back(tmp_path: Path) -> None:
    data = json.loads(_saved(tmp_path).read_text(encoding="utf-8"))["sync"]
    assert data["members"][0]["sync_version"] == 2 and data["rejected"][0]["sync_version"] == 2
    loaded = load_inventory(_saved(tmp_path)).sync
    assert (loaded.members[0].sync_version, loaded.rejected[0].sync_version) == (2, 2)


def test_sync_version_a_file_without_the_field_is_valid_and_counts_as_1(tmp_path: Path) -> None:
    def strip(sync: dict[str, Any]) -> None:
        sync["members"][0].pop("sync_version")
        sync["rejected"][0].pop("sync_version")

    loaded = load_inventory(_saved(tmp_path, strip)).sync
    assert (loaded.members[0].sync_version, loaded.rejected[0].sync_version) == (1, 1)


@pytest.mark.parametrize("where", ["members", "rejected"])
@pytest.mark.parametrize("bad", [0, -1, 1001, "2", 2.5, True])
def test_sync_version_must_be_an_integer_from_1_to_1000(
    tmp_path: Path, where: str, bad: object
) -> None:
    path = _saved(tmp_path, lambda sync: sync[where][0].update(sync_version=bad))
    with pytest.raises(ProjectError, match="sync_version"):
        load_inventory(path)


@pytest.mark.parametrize("limit", [1, 1000])
def test_sync_version_limits_are_valid(tmp_path: Path, limit: int) -> None:
    path = _saved(tmp_path, lambda sync: sync["members"][0].update(sync_version=limit))
    assert load_inventory(path).sync.members[0].sync_version == limit
