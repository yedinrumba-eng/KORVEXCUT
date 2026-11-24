"""`kcut catalog` (spec S1.9a, row 4): it needs no project, `--json` is one document of
`kcut.catalog/1`, `--category` lists one category, and the human output is a table by category with
one line for each item: `[disponible] graphic/title - Título grande - costo bajo - <para qué>`.
"""

import json
from pathlib import Path

import pytest

from kcut import __version__, cli
from kcut.catalog.collect import collect
from tests.conftest import run_kcut


def _json(args: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    capsys.readouterr()
    assert cli.main([*args, "--json"]) == 0
    document: dict[str, object] = json.loads(capsys.readouterr().out)
    return document


def test_catalog_cli_json_outside_a_project_is_the_document_of_the_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)  # a folder with no kcut.toml above it
    document = _json(["catalog"], capsys)
    assert list(document) == ["schema", "engine_version", "items"]
    assert document["schema"] == "kcut.catalog/1" and document["engine_version"] == __version__
    assert document["items"] == [item.to_json() for item in collect()]


def test_catalog_cli_runs_as_the_command_of_the_spec_in_a_fresh_interpreter(tmp_path: Path) -> None:
    done = run_kcut("catalog", "--json", cwd=tmp_path)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["schema"] == "kcut.catalog/1"


def test_catalog_cli_a_category_lists_only_that_one(capsys: pytest.CaptureFixture[str]) -> None:
    document = _json(["catalog", "--category", "look"], capsys)
    items = document["items"]
    assert isinstance(items, list) and {item["category"] for item in items} == {"look"}
    assert len(items) == 6 and document["schema"] == "kcut.catalog/1"


@pytest.mark.parametrize("bad", ["looks", "LOOK", "", "all"])
def test_catalog_cli_a_category_that_does_not_exist_is_exit_2(
    bad: str, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert cli.main(["catalog", "--category", bad, "--json"]) == 2
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["kind"] == "UsageError" and "graphic" in error["message"]


def test_catalog_cli_the_human_output_is_a_table_by_category(
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    assert cli.main(["catalog"]) == 0
    lines = capsys.readouterr().out.splitlines()
    title = (
        "[disponible] graphic/title - Título grande - costo bajo - "
        "Nombra la marca o la idea clave en la palabra que la dice"
    )
    assert title in lines
    # 001.39 (D22): was `camera/face_follow`, which Yedin discarded; `crossfade` is still planned
    assert any(line.startswith("[planeado] transition/crossfade - ") for line in lines)
    headers = [line for line in lines if line.startswith("== ")]
    assert headers == [f"== {c} ==" for c in ("graphic", "look", "sfx", "music", "camera",
                                              "transition", "workflow")]  # fmt: skip
    assert len(lines) == len(collect()) + len(headers)
    assert all("—" not in line for line in lines)  # ASCII punctuation (spec 0.4)


def test_catalog_cli_it_does_not_create_a_log_without_a_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _json(["catalog"], capsys)
    assert list(tmp_path.iterdir()) == []
