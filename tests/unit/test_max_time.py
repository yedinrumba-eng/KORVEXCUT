"""One time cap for every stored time of the inventory and for `kcut.toml` (spec 001.9, point 4)."""

from pathlib import Path

import pytest

from kcut import timebase
from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.ingest import inventory, sync_reasons
from kcut.ingest.inventory import load_inventory
from kcut.ingest.sync_reasons import ambiguity_message
from tests.unit.inventory_fakes import MEMBER, REJECTED, sync_block, written

_HOUR_MS = 3_600_000


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proyecto ñandú"
    (folder / ".kcut").mkdir(parents=True)
    return folder


def test_max_time_is_48_hours_in_milliseconds() -> None:
    assert timebase.MAX_TIME_MS == 48 * _HOUR_MS == 172_800_000


def test_max_time_has_no_other_copy_in_the_sync_modules() -> None:
    assert not hasattr(sync_reasons, "MAX_LAG_MS")
    assert not hasattr(inventory, "MAX_LAG_MS")


@pytest.mark.parametrize(
    ("block", "key"),
    [
        ("rejected", "lag_a_ms"),
        ("rejected", "lag_b_ms"),
        ("members", "offset_ms"),
        ("members", "drift_ms"),
    ],
)
@pytest.mark.parametrize("sign", [1, -1])
def test_max_time_is_the_cap_of_the_four_inventory_fields(
    root: Path, block: str, key: str, sign: int
) -> None:
    base = MEMBER if block == "members" else REJECTED
    edge = sign * timebase.MAX_TIME_MS

    loaded = load_inventory(written(root, sync_block(**{block: [{**base, key: edge}]})), root)
    entries = loaded.sync.members if block == "members" else loaded.sync.rejected
    assert getattr(entries[0], key) == edge

    path = written(root, sync_block(**{block: [{**base, key: edge + sign}]}))
    with pytest.raises(ProjectError, match=key) as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3


def test_max_time_is_the_cap_of_the_ambiguity_message_lags() -> None:
    cap = timebase.MAX_TIME_MS
    assert ambiguity_message(cap, -cap) == (
        "sincronía ambigua: clip corto con dos desfases posibles (172800 s y -172800 s); "
        "revísalo a mano"
    )
    assert "(" not in ambiguity_message(cap + 1, 0)  # past the cap: the text has no numbers


def test_max_time_is_the_maximum_of_max_duration_h_in_kcut_toml() -> None:
    hours = timebase.MAX_TIME_MS / _HOUR_MS
    assert hours == 48.0
    config = parse_config(f"[ingest]\nmax_duration_h = {hours}\n", default_name="x")
    assert config.ingest.max_duration_h == 48.0
    with pytest.raises(ProjectError, match=r"ingest\.max_duration_h.*entre 0\.1 y 48\.0") as info:
        parse_config(f"[ingest]\nmax_duration_h = {hours + 0.5}\n", default_name="x")
    assert info.value.exit_code == 3
