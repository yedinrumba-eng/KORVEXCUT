"""The contact sheet when the project masks, from the side of the video (spec S1.9a rows 22 and 26;
001.41, points 2 and 6), with no ffmpeg and no Chromium (`qa_contact_fakes`).

With `privacy.mask_pii = true` the video is not read for the sheet, whatever the graphics of now
say: the subtitles on, off, or hidden. The sheet has a place for each 2 s of the video or of the
EDL, whichever is shorter (the proxy has nothing past the cut). An `edit/graphics.json` that cannot
be read is no sheet and a fixed warning, not a run that falls after everything was measured.
"""

import io
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from kcut.ff.reader import FrameReader
from kcut.ingest.inventory import Notice
from kcut.project import Project
from kcut.qa import contact, contact_gfx
from kcut.qa.contact_gfx import GRAPHICS_ES, contact_sheet
from tests.unit.edl_fakes import inventory, parsed
from tests.unit.gfx_resolve_fakes import fake_kept, make_project, with_captions, write_graphics
from tests.unit.qa_contact_fakes import RAW, SHEET, SHOWN, WORDS, H, W, install

VIDEO = Path("salida") / "v1.mp4"


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Project:
    fake_kept(monkeypatch, WORDS, SHOWN)
    return make_project(tmp_path)


@pytest.fixture(autouse=True)
def _video_is_a_trap(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Any read of the video, by the reader or by `contact_jpeg`, is recorded and is a failure."""
    opened: list[Path] = []

    def trap(path: Path, *_args: Any, **_kwargs: Any) -> None:
        opened.append(Path(path))
        raise AssertionError("the video was opened for the sheet")

    monkeypatch.setattr(FrameReader, "__init__", lambda self, path, *a, **k: trap(path))
    monkeypatch.setattr(contact, "contact_jpeg", trap)
    monkeypatch.setattr(contact_gfx, "contact_jpeg", trap)
    return opened


def _sheet(project: Project, frames: int = 345) -> tuple[bytes | None, list[Notice]]:
    notices: list[Notice] = []
    done = contact_sheet(project, parsed(), 1, inventory(), VIDEO, frames, (W, H), notices, None)
    return done, notices


def test_qa_contact_never_from_video_the_sheet_is_the_proxy_and_the_video_is_not_opened(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    shooter, base = install(monkeypatch)
    done, notices = _sheet(project)
    assert done is not None and notices == []
    picture = Image.open(io.BytesIO(done))
    assert picture.format == "JPEG" and picture.size == (6 * 216, 384 + 24)
    # 001.47: the frame with graphics is made inside `on_shot`, so it is asked of the proxy first
    assert base.asked == [120, *(f for f in SHEET if f != 120)] and shooter.frames == [[120]]
    page = shooter.pages[0]
    assert "**11" in page and not any(digits in page for digits in RAW)


def test_qa_contact_never_from_video_with_the_subtitles_turned_off_now_it_is_still_the_proxy(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MP4 was rendered with subtitles; now they are off, so no frame has graphics. Before
    001.41 every frame came from the MP4 and showed what it had burned in."""
    shooter, base = install(monkeypatch)
    done, notices = _sheet(with_captions(project, enabled=False))
    assert done is not None and notices == []
    assert base.asked == SHEET and shooter.frames == []


def test_qa_contact_never_from_video_with_every_frame_hidden_it_is_still_the_proxy(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_graphics(
        project,
        {
            "schema": "kcut.graphics/1",
            "captions": {"enabled": True, "hide": [{"start": 0, "end": 345}]},
            "cues": [],
        },
    )
    shooter, base = install(monkeypatch)
    done, notices = _sheet(project)
    assert done is not None and notices == []
    assert base.asked == SHEET and shooter.frames == []


@pytest.mark.parametrize(("frames", "asked"), [(100, [0, 60]), (700, SHEET)])
def test_qa_contact_never_from_video_the_sheet_ends_where_the_cut_or_the_video_ends(
    project: Project, monkeypatch: pytest.MonkeyPatch, frames: int, asked: list[int]
) -> None:
    """A video shorter than the EDL has fewer places; one longer has no more than the proxy has."""
    _, base = install(monkeypatch)
    done, notices = _sheet(project, frames)
    live_first = [f for f in asked if f == 120] + [f for f in asked if f != 120]  # 001.47
    assert done is not None and notices == [] and base.asked == live_first
    assert Image.open(io.BytesIO(done)).size[0] == len(asked) * 216


def test_qa_contact_graphics_unreadable_is_no_sheet_and_a_fixed_warning(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project.root / "edit" / "graphics.json").write_text("{ 972 808 3211", encoding="utf-8")
    shooter, base = install(monkeypatch)
    done, notices = _sheet(project)
    assert done is None
    assert notices == [Notice("contact_skipped", GRAPHICS_ES)]
    assert GRAPHICS_ES == (
        "edit/graphics.json no se puede leer; la hoja de contacto no se escribió; "
        "corre kcut graphics check"
    )
    assert not any(digits in GRAPHICS_ES for digits in RAW)
    assert base.asked == [] and shooter.frames == []  # nothing was built, and no frame of the video


def test_qa_contact_graphics_unreadable_a_folder_in_its_place_is_the_same(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project.root / "edit" / "graphics.json").mkdir()
    install(monkeypatch)
    done, notices = _sheet(project)
    assert done is None and notices == [Notice("contact_skipped", GRAPHICS_ES)]
