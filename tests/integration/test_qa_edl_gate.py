"""`kcut qa` judges the EDL it is going to use as `render`, `mix` and `graphics` do (spec S1.9a
row 33; 001.43, point 2).

Before, it only parsed it, so the ear limit (row 27) and the time limits (row 30) came from the
`frames` that the file declares. With errors the command is exit 1 through `refuse_edl`, before
anything is measured: no tool runs and nothing is written or deleted in `qa/vN/`.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.integration.qa_helpers import VIDEO, built, copy_of, spy_on_ffmpeg
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["built"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
Change = Callable[[dict[str, Any]], None]
SNAPSHOT = "qa/v1/inputs/edl-v1.json"
EDIT = "edit/edl-v1.json"


def _frames(document: dict[str, Any]) -> None:
    document["frames"] = 1080000  # E08: the spans and the clips add up to far less


def _look(document: dict[str, Any]) -> None:
    document["look"] = "no_existe"  # E14


def _version(document: dict[str, Any]) -> None:
    document["version"] = 2  # the file is edl-v1.json: E02


def _output(document: dict[str, Any]) -> None:
    document["output"] = {"w": 60000, "h": 60000}


CASES = [
    pytest.param(_frames, EDIT, id="frames_that_the_file_declares"),
    pytest.param(_look, SNAPSHOT, id="a_look_that_does_not_exist_in_the_snapshot"),
    pytest.param(_version, EDIT, id="a_file_that_says_another_version"),
    pytest.param(_output, EDIT, id="an_output_of_60000_by_60000"),
]


@pytest.mark.parametrize(("change", "rel"), CASES)
def test_qa_edl_gate_an_edl_with_errors_is_exit_1_before_anything_is_measured(
    built: Path,
    tmp_path: Path,
    kcut_json: Run,
    monkeypatch: pytest.MonkeyPatch,
    change: Change,
    rel: str,
) -> None:
    root = copy_of(built, tmp_path)
    document = json.loads((root / EDIT).read_text(encoding="utf-8"))
    change(document)
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(json.dumps(document), encoding="utf-8")
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 1 and doc["error"]["kind"] == "CheckFailed", doc
    assert seen == []  # not ffprobe, not a measurement filter, not the reader of the sheet
    assert not (root / "qa" / "v1" / "report.json").exists()
    assert not (root / "qa" / "v1" / "contact.jpg").exists()


def test_qa_edl_gate_an_explicit_edl_with_errors_is_refused_too(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    document = json.loads((root / EDIT).read_text(encoding="utf-8"))
    _frames(document)
    (root / EDIT).write_text(json.dumps(document), encoding="utf-8")
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", VIDEO, "--edl", EDIT, *project_args(root))
    assert code == 1 and doc["error"]["kind"] == "CheckFailed" and seen == []


def test_qa_edl_gate_the_refusal_leaves_a_report_that_was_already_there_alone(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is deleted either: a sheet of an earlier run stays where it was."""
    root = copy_of(built, tmp_path)
    old = root / "qa" / "v1" / "contact.jpg"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_bytes(b"vieja")
    document = json.loads((root / EDIT).read_text(encoding="utf-8"))
    _frames(document)
    (root / EDIT).write_text(json.dumps(document), encoding="utf-8")
    seen = spy_on_ffmpeg(monkeypatch)
    code, _, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 1 and seen == [] and old.read_bytes() == b"vieja"


@pytest.mark.parametrize(
    ("rel", "remedy"),
    [
        pytest.param(SNAPSHOT, "corre kcut build otra vez", id="the_snapshot_asks_for_a_build"),
        pytest.param(EDIT, "corre kcut edl check y corrígelos", id="an_edl_of_edit_as_always"),
    ],
)
def test_qa_edl_gate_the_remedy_in_the_message_is_the_one_that_fits_the_file(
    built: Path, tmp_path: Path, kcut_json: Run, rel: str, remedy: str
) -> None:
    """001.47 point 8: a snapshot that does not pass is cured by `kcut build` (001.43 point 2);
    an EDL of `edit/` keeps the text that `render`, `mix` and `graphics` have."""
    root = copy_of(built, tmp_path)
    document = json.loads((root / EDIT).read_text(encoding="utf-8"))
    _look(document)
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(json.dumps(document), encoding="utf-8")
    code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 1 and doc["error"]["kind"] == "CheckFailed", doc
    message = doc["error"]["message"]
    assert message.startswith(f"{rel} tiene ") and message.endswith(f"; {remedy}"), message


def test_qa_edl_gate_the_example_edl_passes_the_gate(
    built: Path, tmp_path: Path, kcut_json: Run
) -> None:
    root = copy_of(built, tmp_path)
    code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0 and doc["edl"] == EDIT, doc
