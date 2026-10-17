"""The inventory lives in `.kcut/`, so it is never trusted: bad ids, slugs and paths are refused."""

import json
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.errors import ProjectError
from kcut.ingest.inventory import Inventory, load_inventory, save_inventory
from kcut.ingest.sync_reasons import ambiguity_message
from tests.unit.inventory_fakes import HOSTILE_TEXT, MEMBER, REJECTED, valid_inventory

Mutation = Callable[[dict[str, Any]], object]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proyecto ñandú"
    (folder / ".kcut").mkdir(parents=True)
    return folder


def _written(root: Path, mutate: Mutation | None = None) -> Path:
    path = root / ".kcut" / "inventory.json"
    save_inventory(path, valid_inventory())
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
    assert load_inventory(_written(root), root) == valid_inventory()


def test_the_root_defaults_to_two_levels_above_the_file(root: Path) -> None:
    assert load_inventory(_written(root)) == valid_inventory()


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
    inv = Inventory("x", 30, valid_inventory().clips, id_high={})
    path = root / ".kcut" / "inventory.json"
    save_inventory(path, inv)
    assert dict(load_inventory(path, root).id_high) == {"a": 1, "d": 1}


def _sync(
    rejected: Sequence[dict[str, Any]] = (), members: Sequence[dict[str, Any]] = ()
) -> Mutation:
    """Replace the sync block with the given entries."""
    block = {"master": "a1", "members": list(members), "rejected": list(rejected)}
    return lambda d: d.update(sync=block)


@pytest.mark.parametrize("key", ["lag_a_ms", "lag_b_ms"])
@pytest.mark.parametrize("value", [10**400, 43_200_001, -43_200_001])
def test_lag_range_outside_12_hours_is_invalid(root: Path, key: str, value: int) -> None:
    path = _written(root, _sync(rejected=[{**REJECTED, key: value}]))
    with pytest.raises(ProjectError, match=key) as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3


def test_lag_range_limits_of_12_hours_are_valid(root: Path) -> None:
    edge = {**REJECTED, "lag_a_ms": -43_200_000, "lag_b_ms": 43_200_000}
    loaded = load_inventory(_written(root, _sync(rejected=[edge])), root)
    assert (loaded.sync.rejected[0].lag_a_ms, loaded.sync.rejected[0].lag_b_ms) == (
        -43_200_000,
        43_200_000,
    )


@pytest.mark.parametrize("lag", [10**400, -(10**400), 43_200_001, None, 2.5, "x", True])
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
    path = _written(root, _sync(rejected=[{**REJECTED, "reason": bad}]))
    with pytest.raises(ProjectError, match="reason") as info:
        load_inventory(path, root)
    assert "\x1b" not in info.value.message_es  # the message does not echo the value


@pytest.mark.parametrize("bad", HOSTILE_TEXT)
def test_method_hygiene_refuses_escape_sequences_and_long_text(root: Path, bad: str) -> None:
    path = _written(root, _sync(members=[{**MEMBER, "method": bad}]))
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
    loaded = load_inventory(_written(root, _sync(rejected=rejected, members=members)), root)
    assert [r.reason for r in loaded.sync.rejected] == reasons
    assert [m.method for m in loaded.sync.members] == ["envelope+raw", "manual"]


@pytest.mark.parametrize(
    ("key", "inside", "outside"),
    [
        ("offset_ms", 43_200_000, 43_200_001),
        ("offset_ms", -43_200_000, -43_200_001),
        ("offset_ms", 43_200_000, 10**400),
        ("drift_ms", 43_200_000, 43_200_001),
        ("drift_ms", -43_200_000, -43_200_001),
        ("drift_ms", 43_200_000, 10**400),
        ("drift_windows", 100_000, 100_001),
        ("drift_windows", 100_000, 10**400),
    ],
    ids=[
        "offset-high",
        "offset-low",
        "offset-huge",
        "drift-high",
        "drift-low",
        "drift-huge",
        "windows-high",
        "windows-huge",
    ],
)
def test_member_ranges_stop_at_the_limit(root: Path, key: str, inside: int, outside: int) -> None:
    loaded = load_inventory(_written(root, _sync(members=[{**MEMBER, key: inside}])), root)
    assert getattr(loaded.sync.members[0], key) == inside
    path = _written(root, _sync(members=[{**MEMBER, key: outside}]))
    with pytest.raises(ProjectError, match=key) as info:
        load_inventory(path, root)
    assert info.value.exit_code == 3


@pytest.mark.parametrize("key", ["offset_ms", "drift_ms", "drift_windows"])
def test_member_ranges_hostile_inventory_is_rebuilt_and_ingest_exits_0(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str
) -> None:
    project = tmp_path / "proyecto ñandú"
    assert cli.main(["new", str(project)]) == 0
    (project / "crudo" / "nota.txt").write_text("hola", encoding="utf-8")
    argv = ["ingest", "--project", str(project), "--no-proxy"]
    assert cli.main(argv) == 0
    saved = project / ".kcut" / "inventory.json"
    data = json.loads(saved.read_text(encoding="utf-8"))
    data["sync"] = {"master": "a1", "members": [{**MEMBER, key: 10**9}], "rejected": []}
    saved.write_text(json.dumps(data), encoding="utf-8")
    capsys.readouterr()

    assert cli.main(argv) == 0

    assert "inventory_invalid" in capsys.readouterr().err
    assert load_inventory(saved, project).sync.members == ()  # re-measured: no stale member
