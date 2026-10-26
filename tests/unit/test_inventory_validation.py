"""The inventory lives in `.kcut/`, so it is never trusted: bad ids, slugs and paths are refused."""

import json
from pathlib import Path

import pytest

from kcut import cli
from kcut.errors import ProjectError
from kcut.ingest.inventory import load_inventory
from kcut.ingest.sync_reasons import ambiguity_message
from tests.unit.inventory_fakes import (
    HOSTILE_TEXT,
    MEMBER,
    REJECTED,
    set_clip,
    set_work,
    sync_block,
    valid_inventory,
    written,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proyecto ñandú"
    (folder / ".kcut").mkdir(parents=True)
    return folder


def test_a_valid_inventory_loads(root: Path) -> None:
    assert load_inventory(written(root), root) == valid_inventory()


def test_the_root_defaults_to_two_levels_above_the_file(root: Path) -> None:
    assert load_inventory(written(root)) == valid_inventory()


@pytest.mark.parametrize("key", ["lag_a_ms", "lag_b_ms"])
@pytest.mark.parametrize("value", [10**400, 172_800_001, -172_800_001])
def test_lag_range_outside_48_hours_is_invalid(root: Path, key: str, value: int) -> None:
    path = written(root, sync_block(rejected=[{**REJECTED, key: value}]))
    with pytest.raises(ProjectError, match=key) as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3


def test_lag_range_limits_of_48_hours_are_valid(root: Path) -> None:
    edge = {**REJECTED, "lag_a_ms": -172_800_000, "lag_b_ms": 172_800_000}
    loaded = load_inventory(written(root, sync_block(rejected=[edge])), root)
    assert (loaded.sync.rejected[0].lag_a_ms, loaded.sync.rejected[0].lag_b_ms) == (
        -172_800_000,
        172_800_000,
    )


@pytest.mark.parametrize("lag", [10**400, -(10**400), 172_800_001, None, 2.5, "x", True])
def test_lag_range_ambiguity_message_never_raises(lag: object) -> None:
    for first, second in ((lag, 4000), (4000, lag)):
        text = ambiguity_message(first, second)  # type: ignore[arg-type]
        assert text.startswith("sincronía ambigua") and "(" not in text  # no numbers to show


@pytest.mark.parametrize("flags", [[], ["--json"]])
def test_lag_range_hostile_inventory_is_rebuilt_and_ingest_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: list[str]
) -> None:
    project = tmp_path / "proyecto ñandú"
    assert cli.main(["new", str(project)]) == 0
    (project / "crudo" / "nota.txt").write_text("hola", encoding="utf-8")
    argv = ["ingest", "--project", str(project), "--no-proxy", *flags]
    assert cli.main(argv) == 0
    saved = project / ".kcut" / "inventory.json"
    data = json.loads(saved.read_text(encoding="utf-8"))
    data["sync"] = {"master": "a1", "members": [], "rejected": [{**REJECTED, "lag_a_ms": 10**400}]}
    saved.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()

    assert cli.main(argv) == 0

    assert "inventory_invalid" in capsys.readouterr().err
    assert cli.main(argv) == 0  # the rebuilt inventory is fine: the second run does not fail
    assert [c.id for c in load_inventory(saved, project).clips] == ["d1"]


@pytest.mark.parametrize("bad", HOSTILE_TEXT)
def test_reason_hygiene_refuses_escape_sequences_and_long_text(root: Path, bad: str) -> None:
    path = written(root, sync_block(rejected=[{**REJECTED, "reason": bad}]))
    with pytest.raises(ProjectError, match="reason") as info:
        load_inventory(path, root)
    assert "\x1b" not in info.value.message_es  # the message does not echo the value


@pytest.mark.parametrize("bad", HOSTILE_TEXT)
def test_method_hygiene_refuses_escape_sequences_and_long_text(root: Path, bad: str) -> None:
    path = written(root, sync_block(members=[{**MEMBER, "method": bad}]))
    with pytest.raises(ProjectError, match="method") as info:
        load_inventory(path, root)
    assert "\x1b" not in info.value.message_es


def test_reason_hygiene_keeps_every_text_kcut_writes(root: Path) -> None:
    reasons = [
        "pico de correlacion bajo",
        "pico ambiguo (hay otro casi igual de alto)",
        "sync_weak_refine: la correlacion del refinado (0.012) esta bajo min_refine_corr (0.1)",
        "sync_ambiguous: dos desfases posibles (-2800 ms y 4000 ms)",
    ]
    rejected = [{**REJECTED, "id": f"s{i}", "reason": r} for i, r in enumerate(reasons, start=2)]
    members = [{**MEMBER, "method": "envelope+raw"}, {**MEMBER, "id": "a3", "method": "manual"}]
    loaded = load_inventory(written(root, sync_block(rejected=rejected, members=members)), root)
    assert [r.reason for r in loaded.sync.rejected] == reasons
    assert [m.method for m in loaded.sync.members] == ["envelope+raw", "manual"]


@pytest.mark.parametrize(
    ("key", "inside", "outside"),
    [
        ("offset_ms", 172_800_000, 172_800_001),
        ("offset_ms", -172_800_000, -172_800_001),
        ("offset_ms", 172_800_000, 10**400),
        ("drift_ms", 172_800_000, 172_800_001),
        ("drift_ms", -172_800_000, -172_800_001),
        ("drift_ms", 172_800_000, 10**400),
        ("drift_windows", 100_000, 100_001),
        ("drift_windows", 100_000, 10**400),
    ],
    ids=lambda v: "huge" if v == 10**400 else str(v),
)
def test_member_ranges_stop_at_the_limit(root: Path, key: str, inside: int, outside: int) -> None:
    loaded = load_inventory(written(root, sync_block(members=[{**MEMBER, key: inside}])), root)
    assert getattr(loaded.sync.members[0], key) == inside
    path = written(root, sync_block(members=[{**MEMBER, key: outside}]))
    with pytest.raises(ProjectError, match=key) as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("offset_ms", 10**9),
        ("drift_ms", 10**9),
        ("drift_windows", 10**9),
        pytest.param("score", 10**400, id="huge_float"),
    ],
)
def test_member_ranges_hostile_inventory_is_rebuilt_and_ingest_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str, value: int
) -> None:
    project = tmp_path / "proyecto ñandú"
    assert cli.main(["new", str(project)]) == 0
    (project / "crudo" / "nota.txt").write_text("hola", encoding="utf-8")
    argv = ["ingest", "--project", str(project), "--no-proxy"]
    assert cli.main(argv) == 0
    saved = project / ".kcut" / "inventory.json"
    data = json.loads(saved.read_text(encoding="utf-8"))
    data["sync"] = {"master": "a1", "members": [{**MEMBER, key: value}], "rejected": []}
    saved.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()

    assert cli.main(argv) == 0

    assert "inventory_invalid" in capsys.readouterr().err
    assert load_inventory(saved, project).sync.members == ()  # re-measured: no stale member


@pytest.mark.parametrize(
    ("block", "key"),
    [
        ("members", "score"),
        ("members", "refine_corr"),
        ("rejected", "ratio"),
    ],
)
def test_huge_float_in_the_sync_block_is_invalid_not_an_overflow(
    root: Path, block: str, key: str
) -> None:
    entry = {**(MEMBER if block == "members" else REJECTED), key: 10**400}
    path = written(root, sync_block(**{block: [entry]}))
    with pytest.raises(ProjectError, match=key) as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3
    assert "número finito" in info.value.message_es


def test_huge_float_in_a_clip_is_invalid_not_an_overflow(root: Path) -> None:
    path = written(root, lambda d: d["clips"][0]["audio"].update(peak_dbfs=-(10**400)))
    with pytest.raises(ProjectError, match="peak_dbfs") as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3


def _name(folder: str, length: int, ext: str) -> str:
    return folder + "x" * (length - len(folder) - len(ext)) + ext


@pytest.mark.parametrize(
    ("length", "ok"), [(260, True), (261, False), (1000, False)], ids=["260", "261", "1000"]
)
def test_path_len_of_a_clip_file(root: Path, length: int, ok: bool) -> None:
    change = set_clip(file=_name("crudo/", length, ".mp4"))
    if ok:
        assert load_inventory(written(root, change), root).clips[0].file.endswith(".mp4")
    else:
        with pytest.raises(ProjectError) as info:
            load_inventory(written(root, change), root)
        assert getattr(info.value, "field", "") == "clips[0].file"


@pytest.mark.parametrize("key", ["proxy", "wav16"])
@pytest.mark.parametrize(("length", "ok"), [(260, True), (261, False)], ids=["260", "261"])
def test_path_len_of_the_work_files(root: Path, key: str, length: int, ok: bool) -> None:
    folder = f".kcut/{key}/"
    change = set_work(**{key: _name(folder, length, ".mp4" if key == "proxy" else ".wav")})
    if ok:
        load_inventory(written(root, change), root)
    else:
        with pytest.raises(ProjectError) as info:
            load_inventory(written(root, change), root)
        assert getattr(info.value, "field", "") == f"clips[0].work.{key}"
