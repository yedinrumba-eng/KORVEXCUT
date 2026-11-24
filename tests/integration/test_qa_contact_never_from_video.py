"""With `privacy.mask_pii = true` no frame of the contact sheet is taken from `salida/vN.mp4`
(spec S1.9a row 22; 001.41, point 2, the ALTO of security).

The MP4 has the subtitles burned in, raw, as the words were said when it was rendered. The graphics
of NOW (`edit/graphics.json`, `kcut.toml`, the transcript) can be others: the subtitles are turned
off or hidden after the render, and a frame of the sheet that "has no graphics" and came from the
MP4 shows the phone number all the same. So the sheet is made from the proxy (`render/preview`),
with the masked page over the frames that have graphics, and the MP4 is not opened for it.

Here the MP4 is painted green all over (`burn_green`) instead of burning real digits in it: green is
the stand-in for whatever the file holds, and a cell that is green is a cell taken from the file. A
spy on `FrameReader` says which files were opened. With `mask_pii = false` the cells do come from
the video, and the report says `pii_unmasked`. Chromium is a double that answers magenta.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.qa import ear
from tests.integration.graphics_helpers import plant_words
from tests.integration.qa_contact_helpers import (
    GREEN,
    MAGENTA,
    burn_green,
    cell_pixels,
    install_solid_layer,
    is_color,
    mask_pii_off,
    sheet_plan,
    spy_on_readers,
)
from tests.integration.qa_helpers import VIDEO, built, copy_of
from tests.integration.view_frames_helpers import Run, project_args
from tests.unit.qa_fakes import NoModel

__all__ = ["built"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
SHEET = ("qa", "v1", "contact.jpg")
K = range(6)  # the places of the sheet: the frames 0, 60, 120, 180, 240 and 300


@pytest.fixture(autouse=True)
def _no_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ear, "Engine", NoModel)


@pytest.fixture(scope="module")
def burned(built: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The finished video, painted green, with a phone number in the transcript of a1."""
    root = copy_of(built, tmp_path_factory.mktemp("qaburned"))
    plant_words(root)
    burn_green(root / VIDEO)
    return root


@pytest.fixture
def project(burned: Path, tmp_path: Path) -> Path:
    return copy_of(burned, tmp_path)


def _graphics(root: Path, captions: dict[str, Any]) -> None:
    document = {"schema": "kcut.graphics/1", "captions": captions, "cues": []}
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


def _qa(root: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, Any], int]:
    """`kcut qa` in process: the report and how many times the video was opened by a reader."""
    opened = spy_on_readers(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code in (0, 1) and "error" not in doc, (
        code,
        doc,
        err,
    )  # the other checks: not the point
    assert opened  # the sheet was read from somewhere: the proxies
    video = (root / VIDEO).resolve()
    return doc, sum(1 for path in opened if path.resolve() == video)


def _colors(root: Path) -> list[tuple[bool, bool]]:
    """`(is green, is magenta)` for each cell of the sheet."""
    sheet = root.joinpath(*SHEET)
    cells = [cell_pixels(sheet, k) for k in K]
    return [(is_color(cell, GREEN), is_color(cell, MAGENTA)) for cell in cells]


def test_qa_contact_never_from_video_with_the_subtitles_off_in_graphics_json(
    project: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    _graphics(project, {"enabled": False})  # the render had subtitles; now there are none
    spy = install_solid_layer(monkeypatch)
    doc, from_video = _qa(project, kcut_json, monkeypatch)
    assert from_video == 0  # the MP4 was not opened for the sheet, not even for one frame
    assert doc["contact_sheet"] == "qa/v1/contact.jpg" and "warnings" not in doc
    assert spy.frames == []  # nothing has graphics now, so Chromium was not asked
    assert _colors(project) == [(False, False)] * 6  # no cell is the green of the file


def test_qa_contact_never_from_video_with_a_captions_hide_that_covers_the_cut(
    project: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    _graphics(project, {"enabled": True, "hide": [{"start": 0, "end": 345}]})
    spy = install_solid_layer(monkeypatch)
    doc, from_video = _qa(project, kcut_json, monkeypatch)
    assert from_video == 0 and doc["contact_sheet"] == "qa/v1/contact.jpg"
    assert spy.frames == []
    assert _colors(project) == [(False, False)] * 6


def test_qa_contact_never_from_video_the_cells_with_subtitles_are_the_masked_page_over_the_proxy(
    project: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The subtitles are on, as when the MP4 was rendered: the frames that have them are the page
    over the proxy (magenta, from the double of Chromium), and the others are the proxy alone."""
    with_graphics, _ = sheet_plan(project)
    assert with_graphics
    spy = install_solid_layer(monkeypatch)
    doc, from_video = _qa(project, kcut_json, monkeypatch)
    assert from_video == 0 and doc["contact_sheet"] == "qa/v1/contact.jpg"
    assert spy.frames == [with_graphics]
    colors = _colors(project)
    for k, (is_green, is_magenta) in enumerate(colors):
        assert not is_green, k
        assert is_magenta == (60 * k in with_graphics), k


def test_qa_contact_never_from_video_with_masking_off_the_cells_are_the_video_and_it_warns(
    project: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    mask_pii_off(project)
    install_solid_layer(monkeypatch)
    opened = spy_on_readers(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(project))
    assert code in (0, 1) and "error" not in doc, (code, doc, err)
    video = (project / VIDEO).resolve()
    assert [p.resolve() for p in opened] == [video]  # one reader, over the video: the whole sheet
    assert [w["code"] for w in doc["warnings"]] == ["pii_unmasked"]
    assert doc["contact_sheet"] == "qa/v1/contact.jpg"
    assert _colors(project) == [(True, False)] * 6
