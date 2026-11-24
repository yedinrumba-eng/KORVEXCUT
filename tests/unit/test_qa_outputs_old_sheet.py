"""The message when the old contact sheet cannot be deleted (spec S1.9b step 0, row 13; 001.43
point 7, 001.47 point 6): the cure is to close whatever has it open, and run again.
"""

from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.project import Project
from kcut.qa.outputs import write_sheet
from tests.unit.gfx_resolve_fakes import make_project

REL = "qa/v1/contact.jpg"


@pytest.fixture
def project(tmp_path: Path) -> Project:
    made = make_project(tmp_path)
    (made.root / "qa" / "v1").mkdir(parents=True)
    (made.root / REL).write_bytes(b"vieja")
    return made


def _unlink_fails(monkeypatch: pytest.MonkeyPatch, error: OSError) -> None:
    def unlink(self: Path, missing_ok: bool = False) -> None:
        raise error

    monkeypatch.setattr(Path, "unlink", unlink)


def test_qa_old_sheet_message_a_sheet_that_is_open_says_to_close_it_and_repeat(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unlink_fails(monkeypatch, PermissionError(13, "Acceso denegado"))
    with pytest.raises(ProjectError) as info:
        write_sheet(project, REL, None)
    assert info.value.message_es == (
        f"no pude borrar la hoja de contacto vieja {REL} (Acceso denegado); ciérrala y repite"
    )


def test_old_sheet_message_without_a_strerror_the_reason_is_the_name_of_the_error(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    _unlink_fails(monkeypatch, PermissionError())
    with pytest.raises(ProjectError) as info:
        write_sheet(project, REL, None)
    assert info.value.message_es == (
        f"no pude borrar la hoja de contacto vieja {REL} (PermissionError); ciérrala y repite"
    )
