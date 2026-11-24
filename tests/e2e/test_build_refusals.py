"""`kcut build` refuses, and what a QA that fails does (spec 001.51 point 8, row 33).

- `build_order_edl`: a broken EDL does not change the order: with a video there and no `--force`
  the exit is 3, with no approval it is 5 (001.15).
- `build_refuses`: an error in the EDL, the manifest, the graphics or `sfx.json` is exit 1, and
  `salida/` ends without a new video or a partial.
- `build_qa_fail`: a QA that fails is exit 1 with the video made.
- `build_contact`: the contact sheet of the build exists and opens as a JPEG.

All run in this process (`build_inproc`) over copies of `prepared`, the project not built yet; the
refusals happen before any work, so each takes seconds.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tests.e2e.build_helpers import (
    VIDEO,
    BuildRun,
    build_inproc,
    built,
    copy,
    disapprove,
    prepared,
    sha256,
)
from tests.fixtures.synth_project import ProjectTruth

__all__ = ["built", "prepared"]
pytestmark = [  # 001.52: fixtures prepared/built cost ~290 s alone
    pytest.mark.ffmpeg,
    pytest.mark.slow,
    pytest.mark.e2e,
    pytest.mark.timeout(900),
]
Prepared = tuple[Path, ProjectTruth]


def _edit_json(root: Path, rel: str, change: Any) -> None:
    path = root / rel
    document = json.loads(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(json.dumps(document, indent=1), encoding="utf-8", newline="\n")


def _break_edl(root: Path) -> None:
    _edit_json(root, "edit/edl-v1.json", lambda d: d.update(look="no_existe"))  # E14


def _break_manifest(root: Path) -> None:
    (root / "recursos" / "recursos.json").write_text("{not json", encoding="utf-8")


def _break_graphics(root: Path) -> None:
    _edit_json(
        root, "edit/graphics.json", lambda d: d["cues"].append({"id": "x", "component": "?"})
    )


def _break_sfx(root: Path) -> None:
    _edit_json(root, "edit/sfx.json", lambda d: d["events"].append({"type": "no_existe", "at": 3}))


def test_build_order_edl_a_broken_edl_with_a_video_there_is_exit_3_without_force(
    prepared: Prepared, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = copy(prepared, tmp_path)
    _break_edl(root)
    (root / "salida").mkdir(exist_ok=True)
    (root / VIDEO).write_bytes(b"not a video, and not to be touched")
    before = sha256(root / VIDEO)
    code, doc, _ = build_inproc(capsys, root)
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert sha256(root / VIDEO) == before


def test_build_order_edl_a_broken_edl_with_no_approval_is_exit_5(
    prepared: Prepared, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = copy(prepared, tmp_path)
    _break_edl(root)
    disapprove(root)
    code, doc, _ = build_inproc(capsys, root)
    assert code == 5 and doc["error"]["kind"] == "GateError", doc
    assert not (root / VIDEO).exists()


@pytest.mark.parametrize(
    "breaker", [_break_edl, _break_manifest, _break_graphics, _break_sfx],
    ids=["edl", "manifest", "graphics", "sfx"],
)  # fmt: skip
def test_build_refuses_an_error_in_what_it_reads_is_exit_1_and_makes_no_video(
    prepared: Prepared, tmp_path: Path, capsys: pytest.CaptureFixture[str], breaker: Any
) -> None:
    root = copy(prepared, tmp_path)
    breaker(root)
    code, doc, err = build_inproc(capsys, root)
    assert code == 1 and doc["error"]["kind"] == "CheckFailed", (doc, err)
    assert not (root / VIDEO).exists() and not (root / "salida" / "v1.partial.mp4").exists()


def test_build_qa_fail_a_threshold_that_cannot_be_met_is_exit_1_with_the_video_made(
    prepared: Prepared, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = copy(prepared, tmp_path)
    config = root / "kcut.toml"
    text = config.read_text(encoding="utf-8")
    assert "max_tp = -1.0" in text
    config.write_text(
        text.replace("max_tp = -1.0", "max_tp = -6.0"), encoding="utf-8", newline="\n"
    )
    code, doc, err = build_inproc(capsys, root)  # the delivery peaks at about -1.5 dBTP
    assert code == 1 and doc["ok"] is False and doc["verdict"] == "fail", (doc, err)
    assert (root / VIDEO).is_file() and doc["video"] == VIDEO


def test_build_contact_the_sheet_of_the_build_exists_and_opens_as_a_jpeg(built: BuildRun) -> None:
    _, doc, root = built
    sheet = root / "qa" / "v1" / "contact.jpg"
    assert sheet.is_file() and doc["report"]["contact_sheet"] == "qa/v1/contact.jpg"
    with Image.open(sheet) as image:
        image.load()
        assert image.format == "JPEG" and image.width > 0 and image.height > 0
