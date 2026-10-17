"""The `crudo/` scan never enters junctions or symlinked folders, and lists a path only once."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from kcut.config.load import parse_config
from kcut.ingest import scan as scan_module
from kcut.ingest.inventory import Notice
from kcut.ingest.scan import scan_crudo
from kcut.paths import Layout
from kcut.project import Project
from tests.conftest import run_kcut
from tests.fixtures.links import make_dir_link
from tests.integration.ingest_helpers import ingest, inventory, snapshot


@pytest.fixture
def blank(tmp_path: Path) -> Path:
    root = tmp_path / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    return root


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    folder = tmp_path / "otro disco"
    (folder / "sub").mkdir(parents=True)
    (folder / "ajeno.txt").write_text("no es de este proyecto", encoding="utf-8")
    (folder / "sub" / "mas.txt").write_text("tampoco", encoding="utf-8")
    return folder


def _project(root: Path) -> Project:
    return Project(root, parse_config("", default_name="x"), Layout(root))


def test_a_linked_folder_is_not_entered_and_is_reported(blank: Path, outside: Path) -> None:
    (blank / "crudo" / "propio.txt").write_text("mio", encoding="utf-8")
    make_dir_link(blank / "crudo" / "enlace", outside)
    before = snapshot(outside)

    code, doc = ingest(blank)

    assert code == 0
    assert [c.file for c in inventory(blank).clips] == ["crudo/propio.txt"]
    skipped = [w for w in doc["warnings"] if w["code"] == "skipped_link"]  # type: ignore[attr-defined]
    assert len(skipped) == 1
    assert skipped[0]["id"] is None
    assert "enlace" in skipped[0]["detail"]
    assert snapshot(outside) == before


def test_the_skipped_link_is_also_said_on_stderr(blank: Path, outside: Path) -> None:
    make_dir_link(blank / "crudo" / "enlace", outside)
    result = run_kcut("ingest", "--project", str(blank), "--json")
    assert result.returncode == 0
    assert "skipped_link" in result.stderr


@pytest.mark.slow
def test_a_link_pointing_back_at_crudo_does_not_loop(blank: Path) -> None:
    (blank / "crudo" / "una.txt").write_text("x", encoding="utf-8")
    make_dir_link(blank / "crudo" / "bucle", blank / "crudo")
    code, _ = ingest(blank)
    assert code == 0
    assert [c.file for c in inventory(blank).clips] == ["crudo/una.txt"]


def test_a_link_nested_in_a_subfolder_is_pruned_too(blank: Path, outside: Path) -> None:
    (blank / "crudo" / "dia 1").mkdir()
    (blank / "crudo" / "dia 1" / "nota.txt").write_text("x", encoding="utf-8")
    make_dir_link(blank / "crudo" / "dia 1" / "enlace", outside)
    notices: list[Notice] = []
    found = scan_crudo(_project(blank), notices)
    assert [f.rel for f in found] == ["crudo/dia 1/nota.txt"]
    assert [n.code for n in notices] == ["skipped_link"]
    assert "dia 1/enlace" in notices[0].detail


def test_a_symlinked_file_is_skipped_with_the_same_notice(blank: Path, tmp_path: Path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("x", encoding="utf-8")
    try:
        os.symlink(target, blank / "crudo" / "atajo.txt")
    except OSError as exc:
        pytest.skip(f"sin privilegio para crear symlinks: {exc}")
    notices: list[Notice] = []
    assert scan_crudo(_project(blank), notices) == []
    assert [n.code for n in notices] == ["skipped_link"]


def test_a_path_is_listed_only_once(blank: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (blank / "crudo" / "a.txt").write_text("x", encoding="utf-8")
    real_walk = os.walk

    def twice(top: str | Path) -> Iterator[tuple[str, list[str], list[str]]]:
        for _ in range(2):
            yield from real_walk(top)

    monkeypatch.setattr(scan_module.os, "walk", twice)
    found = scan_crudo(_project(blank), [])
    assert [f.rel for f in found] == ["crudo/a.txt"]


def test_paths_that_differ_only_in_case_count_as_one(
    blank: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (blank / "crudo" / "Foto.txt").write_text("x", encoding="utf-8")
    real_walk = os.walk

    def with_ghost(top: str | Path) -> Iterator[tuple[str, list[str], list[str]]]:
        for folder, dirs, names in real_walk(top):
            yield folder, dirs, [*names, *[n.lower() for n in names]]

    monkeypatch.setattr(scan_module.os, "walk", with_ghost)
    if os.path.normcase("A") == "A":
        pytest.skip("este sistema distingue mayúsculas: dos nombres son dos archivos")
    assert len(scan_crudo(_project(blank), [])) == 1


def test_hidden_folders_are_not_reported_as_links(blank: Path, outside: Path) -> None:
    make_dir_link(blank / "crudo" / ".oculta", outside)
    notices: list[Notice] = []
    assert scan_crudo(_project(blank), notices) == []
    assert notices == []
