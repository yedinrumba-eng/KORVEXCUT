"""The snapshot of the inputs of a build (spec S1.9b; 001.51 points 2, 3 and 8; rows 27, 28, 33).

`snapshot_guard`: a copy in `qa/vN/inputs/` that is a hard link to a file of `crudo/` is exit 3 and
that file stays as it was. `snapshot_stale`: a copy of a file that is not there any more is
deleted and its key is not in `inputs.json`. `snapshot_frozen`: the bytes written are the ones
given, and the second reading names what changed.
"""

import hashlib
import json
from pathlib import Path

import pytest

from kcut.errors import CheckFailed, ProjectError
from kcut.pipeline.snapshot import (
    Inputs,
    Unreadable,
    clear_stale,
    confirm_inputs,
    input_files,
    read_inputs,
    snapshot_inputs,
)
from kcut.project import Project, open_project
from tests.fixtures.links import make_hard_link


def _project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto"
    for folder in ("edit", "crudo", "qa/v1/inputs"):
        (root / folder).mkdir(parents=True)
    (root / "kcut.toml").write_text("", encoding="utf-8")
    (root / "edit" / "edl-v1.json").write_text("{}", encoding="utf-8")
    return open_project(str(root))


def _read(given: dict[str, bytes | None] | None = None) -> Inputs:
    """What `read_inputs` would give: every input absent, except the ones in `given`."""
    read: Inputs = {rel: None for rel in input_files(1)}
    read.update(given or {})
    return read


def test_snapshot_guard_a_copy_that_is_a_hard_link_to_crudo_is_exit_3_and_crudo_stays(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    secret = project.root / "crudo" / "toma.bin"
    secret.write_bytes(b"the footage of the client")
    make_hard_link(project.root / "qa/v1/inputs/graphics.json", secret)
    with pytest.raises(ProjectError) as caught:
        snapshot_inputs(project, 1, read=_read({"edit/graphics.json": b'{"schema": "x"}'}))
    assert caught.value.exit_code == 3
    assert secret.read_bytes() == b"the footage of the client"


def test_snapshot_stale_a_copy_of_a_file_that_is_gone_is_deleted_and_its_key_is_not_listed(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    old = project.root / "qa/v1/inputs/music.json"
    old.write_text('{"from": "an earlier build"}', encoding="utf-8")  # edit/music.json is gone
    snapshot_inputs(project, 1, read=_read({"kcut.toml": b""}))
    assert not old.exists()
    document = json.loads((project.root / "qa/v1/inputs/inputs.json").read_text(encoding="utf-8"))
    assert "edit/music.json" not in document["files"]


def test_snapshot_frozen_it_writes_the_bytes_it_was_given_and_not_what_edit_says_now(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    (project.root / "edit" / "edl-v1.json").write_bytes(b'{"look": "another"}')
    snapshot_inputs(project, 1, read=_read({"edit/edl-v1.json": b'{"look": "first"}'}))
    copy = project.root / "qa/v1/inputs/edl-v1.json"
    assert copy.read_bytes() == b'{"look": "first"}'
    document = json.loads((project.root / "qa/v1/inputs/inputs.json").read_text(encoding="utf-8"))
    assert document["files"]["edit/edl-v1.json"] == hashlib.sha256(b'{"look": "first"}').hexdigest()


def test_snapshot_frozen_an_input_that_could_not_be_read_is_a_project_error(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    read = _read()
    read["kcut.toml"] = Unreadable("PermissionError")
    with pytest.raises(ProjectError, match=r"kcut.toml"):
        snapshot_inputs(project, 1, read=read)


def test_snapshot_frozen_the_second_reading_names_what_changed_appeared_or_went_away(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    first = read_inputs(project, 1)
    confirm_inputs(project, first, 1, None)  # nothing changed: no error
    (project.root / "edit" / "edl-v1.json").write_text('{"a": 1}', encoding="utf-8")
    with pytest.raises(CheckFailed, match=r"edit/edl-v1\.json cambió mientras se construía"):
        confirm_inputs(project, first, 1, None)
    first = read_inputs(project, 1)
    (project.root / "edit" / "music.json").write_text("{}", encoding="utf-8")  # appeared
    with pytest.raises(CheckFailed, match=r"edit/music\.json cambió"):
        confirm_inputs(project, first, 1, None)
    first = read_inputs(project, 1)
    (project.root / "edit" / "music.json").unlink()  # went away
    with pytest.raises(CheckFailed, match=r"edit/music\.json cambió"):
        confirm_inputs(project, first, 1, None)


def test_snapshot_frozen_an_input_that_cannot_be_read_the_second_time_is_exit_3(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    first = read_inputs(project, 1)
    (project.root / "edit" / "sfx.json").write_bytes(b"x" * (65 * 1024 * 1024))  # over the cap
    with pytest.raises(ProjectError, match=r"edit/sfx\.json"):
        confirm_inputs(project, first, 1, None)


def test_snapshot_stale_clear_stale_removes_the_report_the_sheet_and_the_copies(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    folder = project.root / "qa" / "v1"
    for name in ("report.json", "contact.jpg", "inputs/inputs.json", "inputs/edl-v1.json"):
        (folder / name).write_bytes(b"old")
    clear_stale(project, 1)
    assert sorted(p.name for p in folder.rglob("*") if p.is_file()) == []


def test_snapshot_stale_clear_stale_with_a_hard_link_deletes_nothing(tmp_path: Path) -> None:
    project = _project(tmp_path)
    secret = project.root / "crudo" / "toma.bin"
    secret.write_bytes(b"the footage")
    folder = project.root / "qa" / "v1"
    (folder / "report.json").write_bytes(b"old")
    make_hard_link(folder / "contact.jpg", secret)
    with pytest.raises(ProjectError):
        clear_stale(project, 1)
    assert (folder / "report.json").exists() and secret.read_bytes() == b"the footage"
