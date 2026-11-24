"""The contact sheet does not hold the PNGs of Chromium (spec S1.9b step 0, row 8; 001.43 point 7,
001.47 point 1), with no ffmpeg and no Chromium (`qa_contact_fakes`).

`capture_stills` hands each PNG to `on_shot(f, png)` as soon as it is made, and the sheet makes the
cell of that frame there, so nothing keeps the bytes. The double of Chromium zeroes each PNG as soon
as `on_shot` returns: a sheet that kept the bytes to decode them later would get zeros and be
another sheet (or none).
"""

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from kcut.ingest.inventory import Notice
from kcut.project import Project
from kcut.qa.contact_gfx import masked_cells
from tests.unit.edl_fakes import inventory, parsed
from tests.unit.gfx_resolve_fakes import fake_kept, make_project
from tests.unit.qa_contact_fakes import CELL, SHEET, SHOWN, WORDS, install


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Project:
    fake_kept(monkeypatch, WORDS, SHOWN)
    return make_project(tmp_path)


def _cells(project: Project, notices: list[Notice]) -> list[Image.Image]:
    return list(masked_cells(project, parsed(), 1, inventory(), SHEET, CELL, notices, None))


def test_qa_contact_one_shot_a_double_that_zeroes_each_png_gives_the_same_sheet(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as intact:
        shooter, _ = install(intact, (255, 0, 255, 255))
        kept = [np.asarray(cell).copy() for cell in _cells(project, [])]
        assert shooter.frames == [[120]]  # control: Chromium was asked
    with monkeypatch.context() as zeroing:
        shooter, _ = install(zeroing, (255, 0, 255, 255), zero_after=True)
        notices: list[Notice] = []
        zeroed = [np.asarray(cell).copy() for cell in _cells(project, notices)]
        assert shooter.frames == [[120]]
    assert [n for n in notices if n.code == "contact_skipped"] == []
    assert len(zeroed) == len(kept) == len(SHEET)
    for same, other in zip(kept, zeroed, strict=True):
        assert np.array_equal(same, other)
    assert kept[SHEET.index(120)].reshape(-1, 3).mean(axis=0).tolist() == [255.0, 0.0, 255.0]


def test_qa_contact_one_shot_chromium_is_asked_with_an_on_shot_and_gives_nothing_back(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    shooter, base = install(monkeypatch, zero_after=True)
    _cells(project, [])
    assert shooter.frames == [[120]]
    assert sorted(base.asked) == SHEET  # the proxy gives each frame of the sheet once, no more
    assert base.asked[0] == 120  # the one with graphics is made inside `on_shot`, the rest after
    assert base.asked[1:] == [f for f in SHEET if f != 120]
