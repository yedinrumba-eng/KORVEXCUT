"""`kcut qa salida/vN.mp4 --edl <EDL of another version>` is a UsageError (spec S1.9a row 23;
001.41, point 3).

The sheet and the diff of the transcript are made from the EDL, and an EDL of another version is
another cut: two versions mixed in one report. The refusal comes before anything is measured, so no
tool runs and nothing is written. The version of an EDL is the N of its name, `edl-vN.json`, as
everywhere else (`find_edl`).
"""

import json
from pathlib import Path

import pytest

from tests.integration.qa_helpers import VIDEO, built, copy_of, spy_on_ffmpeg
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["built"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
MESSAGE = "el EDL es de la versión {edl} y el video de la {video}; usa el EDL de la misma versión"


def _plant(root: Path, version: int) -> str:
    """`edit/edl-v<version>.json`, the example EDL with that version in it; its path."""
    document = json.loads((root / "edit" / "edl-v1.json").read_text(encoding="utf-8"))
    document["version"] = version
    rel = f"edit/edl-v{version}.json"
    (root / rel).write_text(json.dumps(document), encoding="utf-8")
    return rel


@pytest.mark.parametrize("other", [2, 3, 10])
def test_qa_edl_version_an_edl_of_another_version_is_exit_2_and_no_tool_runs(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, other: int
) -> None:
    root = copy_of(built, tmp_path)
    rel = _plant(root, other)
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", VIDEO, "--edl", rel, *project_args(root))
    assert code == 2 and doc["error"]["kind"] == "UsageError", doc
    assert doc["error"]["message"] == MESSAGE.format(edl=other, video=1)
    assert seen == []  # not ffprobe, not a measurement filter, not the reader of the sheet
    assert not (root / "qa" / "v1" / "report.json").exists()


def test_qa_edl_version_the_edl_of_the_same_version_is_accepted(
    built: Path, tmp_path: Path, kcut_json: Run
) -> None:
    root = copy_of(built, tmp_path)
    code, doc, _ = kcut_json("qa", VIDEO, "--edl", "edit/edl-v1.json", *project_args(root))
    assert code == 0 and doc["edl"] == "edit/edl-v1.json", doc


def test_qa_edl_version_an_edl_that_is_not_named_edl_vn_is_still_refused_as_before(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    (root / "edit" / "otro.json").write_text("{}", encoding="utf-8")
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", VIDEO, "--edl", "edit/otro.json", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError" and seen == []
