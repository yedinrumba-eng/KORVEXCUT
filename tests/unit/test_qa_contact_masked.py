"""The cells of the contact sheet when the project masks (spec S1.9a rows 18 and 22; 001.39 D19,
001.40, 001.41), with no ffmpeg and no Chromium (`qa_contact_fakes`): `resolve` is the real one over
a phone number said in the transcript, the proxy is a gray frame and Chromium is a double.

Every cell is the frame of the proxy (001.41); the ones in `active_frames` have the page with
`masked=True` over it, and only those are asked of Chromium. With `privacy.mask_pii = false` the
sheet is read from the video. A Chromium that is not there or a proxy that is not there is
`None` with the fixed warning `contact_skipped`; a folder of the cache that is a link is still
exit 3.
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from kcut.errors import MissingDependency, ProjectError, ToolError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.layer import page_for
from kcut.gfx.resolve import resolve
from kcut.ingest.inventory import Notice
from kcut.pack.pii import UNMASKED
from kcut.project import Project
from kcut.qa import contact_gfx
from kcut.qa.contact_gfx import CHROMIUM_ES, PROXY_ES, contact_sheet, masked_cells
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.unit.edl_fakes import inventory, parsed
from tests.unit.gfx_resolve_fakes import fake_kept, make_project, with_captions, with_privacy
from tests.unit.qa_contact_fakes import CELL, RAW, SHEET, SHOWN, WORDS, H, W, install

_install = install


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Project:
    fake_kept(monkeypatch, WORDS, SHOWN)
    return make_project(tmp_path)


def _cells(project: Project, notices: list[Notice]) -> list[Image.Image]:
    """The cell of each frame of the sheet (001.41: all of them, not only those with graphics)."""
    return list(masked_cells(project, parsed(), 1, inventory(), SHEET, CELL, notices, None))


def _sheet(project: Project, notices: list[Notice]) -> bytes | None:
    """`contact_sheet` of the 345 frames of the example: the JPEG, or `None` if a cell failed."""
    video = Path("salida") / "v1.mp4"  # with masking on, nothing opens it
    return contact_sheet(project, parsed(), 1, inventory(), video, 345, (W, H), notices, None)


def _live(project: Project) -> list[int]:
    resolved = resolve(project, parsed(), 1, inventory=inventory())
    live = set(gfx_capture.active_frames(resolved))
    return [f for f in SHEET if f in live]


def test_qa_contact_masked_only_the_frames_with_subtitles_are_asked_for_and_with_the_masked_page(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    shooter, base = _install(monkeypatch)
    notices: list[Notice] = []
    cells = _cells(project, notices)
    wanted = _live(project)
    assert wanted == [120]  # the frame 120 is inside the words; the other five are not
    assert len(cells) == len(SHEET)  # 001.41: a cell for every frame of the sheet, not only [120]
    assert [n for n in notices if n.code == "contact_skipped"] == []
    assert shooter.frames == [wanted]  # Chromium is asked for the frame with subtitles and no other
    # 001.41: the proxy gives every frame (before: only `wanted`); 001.47: the one with graphics
    # is made inside `on_shot`, so it comes first, and each frame is asked once
    assert base.asked == [*wanted, *(f for f in SHEET if f not in wanted)]
    page = shooter.pages[0]
    assert "**11" in page and not any(digits in page for digits in RAW)
    resolved = resolve(project, parsed(), 1, inventory=inventory())
    assert "3211" in page_for(resolved, masked=False)  # control: the raw page does carry it
    assert page == page_for(resolved, masked=True)


def test_qa_contact_masked_a_cell_is_the_layer_over_the_proxy_reduced_to_the_cell(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, (255, 0, 255, 255))
    cells = _cells(project, [])
    cell = cells[SHEET.index(120)]  # 001.41: a list in the order of the sheet, no longer a dict
    assert cell.mode == "RGB" and cell.size == CELL
    assert np.asarray(cell).reshape(-1, 3).mean(axis=0).tolist() == [255.0, 0.0, 255.0]
    for k, other in enumerate(cells):  # 001.41: the rest are the proxy alone, gray
        if SHEET[k] != 120:
            assert np.asarray(other).reshape(-1, 3).mean(axis=0).tolist() == [100.0] * 3


def test_qa_contact_masked_a_layer_with_nothing_drawn_leaves_the_proxy_as_it_is(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(monkeypatch, (0, 0, 0, 0))
    cells = _cells(project, [])
    cell = cells[SHEET.index(120)]  # 001.41: by place in the sheet
    assert np.asarray(cell).reshape(-1, 3).mean(axis=0).tolist() == [100.0, 100.0, 100.0]


def test_qa_contact_masked_with_masking_off_nothing_is_built_and_the_report_warns(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    shooter, base = _install(monkeypatch)
    read: list[tuple[Path, int]] = []
    monkeypatch.setattr(
        contact_gfx, "contact_jpeg", lambda video, frames, *_a: read.append((video, frames)) or b"x"
    )
    notices: list[Notice] = []
    video = Path("salida") / "v1.mp4"
    off = with_privacy(project, False)
    sheet = contact_sheet(off, parsed(), 1, inventory(), video, 345, (W, H), notices, None)
    assert sheet == b"x" and read == [
        (video, 345)
    ]  # 001.41: the whole sheet is read from the video
    assert shooter.frames == [] and base.asked == []  # nothing is built from the proxy or Chromium
    assert notices == [Notice("pii_unmasked", UNMASKED)]


def test_qa_contact_masked_no_frame_of_the_sheet_with_subtitles_does_not_start_chromium(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    shooter, base = _install(monkeypatch)
    off = with_captions(project, enabled=False)  # nothing to draw at all
    assert len(_cells(off, [])) == len(SHEET)  # 001.41: still a cell for each frame, from the proxy
    assert base.asked == SHEET  # 001.41
    # subtitles are drawn at 120, but this sheet does not sample it
    sparse = masked_cells(project, parsed(), 1, inventory(), [0, 60, 180], CELL, [], None)
    assert len(list(sparse)) == 3 and base.asked == [*SHEET, 0, 60, 180]  # 001.41
    assert shooter.frames == []  # Chromium: never


@pytest.mark.parametrize(
    "failure",
    [
        MissingDependency("Chromium no arrancó (C:/secreto/809-555-1234)"),
        ToolError("la página de gráficos dio errores: llama al 8095551234"),
    ],
)
def test_qa_contact_masked_a_chromium_that_fails_is_no_sheet_with_a_fixed_warning(
    project: Project, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    _, base = _install(monkeypatch, chromium=failure)
    notices: list[Notice] = []
    assert _sheet(project, notices) is None  # 001.41: through `contact_sheet`, which says why
    assert notices == [Notice("contact_skipped", CHROMIUM_ES)]
    assert base.asked == []  # and no frame of the video takes the place of the one with graphics
    assert "809" not in CHROMIUM_ES


def test_qa_contact_masked_a_png_that_chromium_gave_wrong_is_no_sheet_either(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    shooter, _ = _install(monkeypatch)
    shooter.layer = b"not a png"
    notices: list[Notice] = []
    assert _sheet(project, notices) is None  # 001.41
    assert notices == [Notice("contact_skipped", CHROMIUM_ES)]


@pytest.mark.parametrize(
    "failure",
    [ProjectError("falta el proxy de ana-perez-809-555-1234; corre kcut ingest"), ToolError("x")],
)
def test_qa_contact_masked_a_proxy_that_is_not_there_is_no_sheet_with_a_fixed_warning(
    project: Project, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    _install(monkeypatch, proxy=failure)
    notices: list[Notice] = []
    assert _sheet(project, notices) is None  # 001.41
    assert notices == [Notice("contact_skipped", PROXY_ES)]
    assert "809" not in PROXY_ES


def test_qa_contact_masked_a_gfx_folder_that_is_a_link_is_still_exit_3(
    project: Project, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch)
    build = project.layout.build_dir(1)
    build.mkdir(parents=True)
    outside = tmp_path / "ajeno"
    outside.mkdir()
    make_dir_link(build / "gfx", outside)
    try:
        with pytest.raises(ProjectError, match=r"fuera de \.kcut"):
            _sheet(project, [])  # 001.41: through `contact_sheet`; a link is not a `SheetSkipped`
    finally:
        remove_dir_link(build / "gfx")
    assert list(outside.iterdir()) == []  # nothing went through the link
