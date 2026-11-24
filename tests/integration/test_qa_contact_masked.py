"""The contact sheet of `kcut qa` does not show the text of the transcript unmasked (spec S1.9a
row 18; 001.39 D19 and 001.40).

Claude reads the sheet. The MP4 has the subtitles burned in, raw, so no frame of the sheet is taken
from it (001.41): every cell is the frame of the cut made from the proxy, and the ones that fall
where the graphics of the version are drawn (`active_frames` of `resolve`, no Chromium) have the
page of the graphics over it, with `masked=True`, which is the way `graphics still` makes a frame.
With `privacy.mask_pii = false` every frame comes from the video. If a cell cannot be made (no
Chromium, no proxy) the sheet is not written: `contact_sheet` is null, the warning
`contact_skipped` says so and the report comes out with the other checks.

The project is the synthetic one rendered with `--no-graphics` (`qa_helpers.built`) with the
phone number of `plant_words` in the transcript of a1 (972 808 3211): its words are in the output
frames 105 to 204, where the default subtitles are drawn. Chromium is replaced by a double that
answers an opaque magenta layer (`qa_contact_helpers`), except in the last test.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut import cli
from kcut.edl.check import check_edl_file
from kcut.gfx import capture as gfx_capture
from kcut.gfx.layer import page_for
from kcut.gfx.resolve import resolve
from kcut.project import load_inventory, open_project
from kcut.qa import ear
from kcut.qa.contact import cell_of, cell_size, cells_jpeg, contact_frames, contact_jpeg
from kcut.render.frame_fx import fx_context
from kcut.render.preview import base_frame
from tests.integration.fake_shooter import install_fake_shooter
from tests.integration.graphics_helpers import plant_words
from tests.integration.qa_contact_helpers import (
    MAGENTA,
    Spy,
    cell_pixels,
    install_solid_layer,
    mask_pii_off,
    sheet_plan,
)
from tests.integration.qa_helpers import VIDEO, built, check_of, copy_of
from tests.integration.view_frames_helpers import Run, project_args
from tests.unit.qa_fakes import NoModel

__all__ = ["built"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
RAW = ("972", "808", "3211")
TEXT_SUFFIXES = {".json", ".html", ".txt", ".log", ".md", ".toml", ".tsv"}
WRITTEN_UNDER = ("qa/v1/", ".kcut/build/v1/gfx/", ".kcut/qa_ear/", ".kcut/logs/")


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    found: dict[str, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if path.is_file():
            info = path.stat()
            found[path.relative_to(root).as_posix()] = (info.st_size, info.st_mtime_ns)
    return found


@dataclass
class Made:
    code: int
    doc: dict[str, Any]
    root: Path
    spy: Spy
    changed: list[str]


@pytest.fixture(autouse=True)
def _no_whisper(monkeypatch: pytest.MonkeyPatch) -> None:
    """The model of Whisper is not part of this test: the transcript check is skipped."""
    monkeypatch.setattr(ear, "Engine", NoModel)


@pytest.fixture
def planted(built: Path, tmp_path: Path) -> Path:
    root = copy_of(built, tmp_path)
    plant_words(root)
    return root


@pytest.fixture(scope="module")
def made(built: Path, tmp_path_factory: pytest.TempPathFactory) -> Made:
    """`kcut qa salida/v1.mp4` once on the project with the phone in its transcript."""
    root = copy_of(built, tmp_path_factory.mktemp("qamasked"))
    plant_words(root)
    before = _snapshot(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ear, "Engine", NoModel)
        spy = install_solid_layer(patch)
        code = cli.main(["qa", VIDEO, *project_args(root), "--json"])
    after = _snapshot(root)
    changed = sorted(rel for rel, stat in after.items() if before.get(rel) != stat)
    doc = json.loads((root / "qa" / "v1" / "report.json").read_text(encoding="utf-8"))
    return Made(code, doc, root, spy, changed)


def _plain_sheet(root: Path) -> bytes:
    """The sheet of the MP4 as it is, with no graphics (what the sheet was before 001.39, and what
    it is with `privacy.mask_pii = false`)."""
    return contact_jpeg(root / VIDEO, 345, 30, (1080, 1920), None)


def _proxy_sheet(root: Path) -> bytes:
    """The sheet of the frames of the cut made from the proxy, with no graphics over any (001.41):
    what a cell with no graphics is."""
    project = open_project(str(root))
    edl = _edl(root)
    ctx = fx_context(project, edl)
    inventory = load_inventory(project)
    cell = cell_size(1080, 1920)
    frames = contact_frames(345, 30)
    cells = (cell_of(base_frame(project, edl, inventory, f, ctx, log=None), cell) for f in frames)
    return cells_jpeg(cells, 345, 30, (1080, 1920))


def test_qa_contact_masked_the_frames_that_have_subtitles_are_built_from_the_masked_page(
    made: Made,
) -> None:
    with_graphics, without = sheet_plan(made.root)
    assert with_graphics and without  # there is something of each in the sheet
    assert made.code == 0, made.doc
    assert made.spy.frames == [with_graphics]  # one call, only with the frames that have graphics
    page = made.spy.pages[0]
    assert "**11" in page  # the masked word is there
    for digits in RAW:
        assert digits not in page, digits
    project = open_project(str(made.root))
    resolved = resolve(project, _edl(made.root), 1, inventory=load_inventory(project))
    assert RAW[2] in page_for(resolved, masked=False)  # control: the raw page does carry it


def _edl(root: Path) -> Any:
    project = open_project(str(root))
    checked = check_edl_file(project, load_inventory(project), None)
    assert checked.edl is not None
    return checked.edl


def test_qa_contact_masked_a_cell_with_graphics_is_the_still_and_the_rest_is_the_proxy(
    made: Made,
) -> None:
    with_graphics, without = sheet_plan(made.root)
    sheet = made.root / "qa" / "v1" / "contact.jpg"
    proxy = _proxy_sheet(made.root)  # 001.41: the reference is the proxy, no longer the MP4
    for f in with_graphics:  # the magenta of the layer, over the whole picture
        mean = cell_pixels(sheet, f // 60).reshape(-1, 3).mean(axis=0)
        assert np.abs(mean - np.array(MAGENTA)).max() < 12, (f, mean)
    for f in without:  # 001.41: the pixels of the frame of the proxy, reduced (before: the MP4)
        k = f // 60
        assert np.array_equal(cell_pixels(sheet, k), cell_pixels(proxy, k)), f


def test_qa_contact_masked_the_report_has_the_sheet_and_no_warning(made: Made) -> None:
    assert made.doc["contact_sheet"] == "qa/v1/contact.jpg"
    assert "warnings" not in made.doc  # a masked sheet is nothing to warn about
    assert check_of(made.doc, "frames")["status"] == "pass"


def test_qa_contact_masked_nothing_is_written_outside_the_folders_of_the_run(made: Made) -> None:
    outside = [rel for rel in made.changed if not rel.startswith(WRITTEN_UNDER)]
    assert outside == [], outside
    for rel in made.changed:
        path = made.root / rel
        if path.suffix.lower() in TEXT_SUFFIXES and not rel.startswith(".kcut/build/v1/gfx/"):
            text = path.read_text(encoding="utf-8", errors="replace")
            assert not any(digits in text for digits in RAW), rel


def test_qa_contact_masked_the_page_that_is_written_is_the_masked_one_and_only_under_gfx(
    planted: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_shooter(monkeypatch)  # the real Shooter writes the page; Chromium is not started
    code, doc, err = kcut_json("qa", VIDEO, *project_args(planted))
    assert code == 0, (doc, err)
    pages = sorted(p.relative_to(planted).as_posix() for p in planted.rglob("page.html"))
    assert pages == [".kcut/build/v1/gfx/stills_work/page.html"]
    text = (planted / pages[0]).read_text(encoding="utf-8")
    assert "**11" in text and not any(digits in text for digits in RAW)


def test_qa_contact_masked_with_masking_off_no_frame_is_built_and_the_report_warns(
    planted: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    mask_pii_off(planted)
    spy = install_solid_layer(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(planted))
    assert code == 0, (doc, err)
    assert spy.frames == [] and spy.pages == []  # Chromium was not asked for anything
    assert [w["code"] for w in doc["warnings"]] == ["pii_unmasked"]
    assert doc["contact_sheet"] == "qa/v1/contact.jpg"
    sheet = (planted / "qa" / "v1" / "contact.jpg").read_bytes()
    assert sheet == _plain_sheet(planted)  # every frame comes from the video
    assert not (planted / ".kcut" / "build" / "v1" / "gfx" / "stills_work").exists()


def test_qa_contact_masked_without_chromium_there_is_no_sheet_and_the_report_comes_out(
    planted: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gfx_capture.Shooter, "_boot", lambda self: "Chromium no arranca (prueba)")
    code, doc, err = kcut_json("qa", VIDEO, *project_args(planted))
    assert code == 0, (doc, err)
    assert doc["contact_sheet"] is None
    assert not (planted / "qa" / "v1" / "contact.jpg").exists()  # not a frame of the MP4 either
    skipped = [w for w in doc["warnings"] if w["code"] == "contact_skipped"]
    assert len(skipped) == 1
    from kcut.qa.contact_gfx import CHROMIUM_ES

    assert skipped[0]["message_es"] == CHROMIUM_ES
    on_disk = json.loads((planted / "qa" / "v1" / "report.json").read_text(encoding="utf-8"))
    assert on_disk == doc
    assert {c["id"]: c["status"] for c in doc["checks"]}["frames"] == "pass"
    assert "contact_skipped" in err  # and the console says it, as it does with every warning


def test_qa_contact_masked_with_no_subtitles_in_the_sheet_chromium_is_not_needed(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)  # no transcript: no subtitle, so no frame with graphics
    spy = install_solid_layer(monkeypatch)
    monkeypatch.setattr(gfx_capture.Shooter, "_boot", lambda self: "no debe llamarse")
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0, (doc, err)
    assert spy.frames == [] and doc["contact_sheet"] == "qa/v1/contact.jpg"
    assert (root / "qa" / "v1" / "contact.jpg").read_bytes() == _proxy_sheet(root)  # 001.41
    assert "warnings" not in doc


@pytest.mark.chromium
def test_qa_contact_masked_with_chromium_the_subtitles_are_drawn_on_the_cells_that_have_them(
    planted: Path, kcut_json: Run
) -> None:
    code, doc, err = kcut_json("qa", VIDEO, *project_args(planted))
    assert code == 0, (doc, err)
    assert doc["contact_sheet"] == "qa/v1/contact.jpg" and "warnings" not in doc
    with_graphics, without = sheet_plan(planted)
    sheet = planted / "qa" / "v1" / "contact.jpg"
    plain = _proxy_sheet(planted)  # 001.41: the proxy alone, with no subtitles drawn on it
    for f in with_graphics:
        drawn = cell_pixels(sheet, f // 60).astype(np.int16) - cell_pixels(plain, f // 60)
        assert np.abs(drawn).max() > 40, f  # the white of the letters is on the cell
    for f in without:
        assert np.array_equal(cell_pixels(sheet, f // 60), cell_pixels(plain, f // 60)), f
    text = (planted / ".kcut/build/v1/gfx/stills_work/page.html").read_text(encoding="utf-8")
    assert re.search(r"\*\*11", text) and not any(digits in text for digits in RAW)
