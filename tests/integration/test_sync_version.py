"""A sync result from an older algorithm is measured again, not reused (001.7, point 15)."""

import json
import math
from pathlib import Path

import pytest

from kcut import cli
from kcut.audio.wavio import write_wav_s16_mono
from kcut.ingest import sync as sync_module
from kcut.ingest import sync_stage
from kcut.ingest.inventory import load_inventory
from tests.unit.sync_signals import SR, speechlike, world

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]


def _argv(root: Path) -> list[str]:
    return ["ingest", "--project", str(root), "--json", "--no-proxy"]


def _master_is_s1(root: Path) -> None:
    toml = root / "kcut.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace('master = ""', 'master = "s1"'))


@pytest.fixture
def tones_pair(blank: Path) -> Path:
    """Periodic audio, 12 s, B 4 s later: 001.6 accepted it with -2800, 001.7 rejects it."""
    write_wav_s16_mono(blank / "crudo" / "a.wav", world(0.0), SR)
    write_wav_s16_mono(blank / "crudo" / "b.wav", world(4.0), SR)
    _master_is_s1(blank)
    return blank


@pytest.fixture
def voice_pair(blank: Path) -> Path:
    """Speech-like audio, B 2 s later: accepted."""
    scene = speechlike(60, 7)
    write_wav_s16_mono(blank / "crudo" / "a.wav", scene[: 30 * SR], SR)
    write_wav_s16_mono(blank / "crudo" / "b.wav", scene[2 * SR : 32 * SR], SR)
    _master_is_s1(blank)
    return blank


@pytest.mark.parametrize(
    ("fixture", "key"), [("tones_pair", "rejected"), ("voice_pair", "members")]
)
def test_sync_version_is_stored_with_accepted_and_rejected_results(
    request: pytest.FixtureRequest, fixture: str, key: str
) -> None:
    root: Path = request.getfixturevalue(fixture)
    assert cli.main(_argv(root)) == 0
    saved = json.loads((root / ".kcut" / "inventory.json").read_text(encoding="utf-8"))
    assert saved["sync"][key][0]["sync_version"] == sync_module.SYNC_VERSION


def test_sync_version_an_inventory_of_001_6_is_measured_again_without_resync(
    tones_pair: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as algorithm_of_001_6:
        algorithm_of_001_6.setattr(sync_module, "AMBIGUITY_LAG_MS", math.inf)
        assert cli.main(_argv(tones_pair)) == 0
    saved = tones_pair / ".kcut" / "inventory.json"
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert abs(data["sync"]["members"][0]["offset_ms"] + 2800) <= 10  # the wrong lag, accepted
    for member in data["sync"]["members"]:
        member.pop("sync_version")  # an inventory written before 001.7 has no version
    saved.write_text(json.dumps(data), encoding="utf-8")

    assert cli.main(_argv(tones_pair)) == 0  # a normal ingest: no --resync

    loaded = load_inventory(saved).sync
    assert loaded.members == ()
    assert loaded.rejected[0].reason.startswith("sync_ambiguous")


def test_sync_version_a_current_result_is_reused_and_an_old_one_is_not(
    tones_pair: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cli.main(_argv(tones_pair)) == 0
    calls: list[int] = []
    real = sync_stage.sync_pair

    def spy(*args: object, **kwargs: object) -> object:
        calls.append(1)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sync_stage, "sync_pair", spy)
    assert cli.main(_argv(tones_pair)) == 0
    assert calls == []  # same files, current version: nothing is measured

    saved = tones_pair / ".kcut" / "inventory.json"
    data = json.loads(saved.read_text(encoding="utf-8"))
    data["sync"]["rejected"][0]["sync_version"] = 1
    saved.write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(_argv(tones_pair)) == 0
    assert calls == [1]  # the version-1 result was measured again
    assert load_inventory(saved).sync.rejected[0].sync_version == sync_module.SYNC_VERSION
