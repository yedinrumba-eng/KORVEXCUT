"""A path that the system cannot resolve is a `ProjectError`, never an `InternalError` (spec S1.8b
step 0, 001.36 point 5; row 16). `Path.resolve` raises `ValueError` (`stat: path too long for
Windows`) or `OSError` for a path that is too long or that the system refuses; before this it left
`resolve_in_project` as it came and the command ended in exit 10. The message does not carry the
path, which can be a person's. The same text comes out of the manifest of resources when one of its
`file` is such a path.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.paths import resolve_in_project
from kcut.project import Project
from kcut.recursos.manifest import require_approved
from tests.unit.gfx_resolve_fakes import make_project

UNRESOLVABLE = "la ruta no se puede resolver"


def test_resolve_too_long_a_path_of_40000_characters_is_a_project_error(tmp_path: Path) -> None:
    with pytest.raises(ProjectError) as info:
        resolve_in_project(tmp_path, "a" * 40000)
    assert info.value.message_es == UNRESOLVABLE and info.value.exit_code == 3


@pytest.mark.parametrize(
    "error",
    [
        ValueError("stat: path too long for Windows"),
        OSError(206, "The filename or extension is too long", "C:/Maria-809-555-1234"),
        OSError(1920, "The file cannot be accessed by the system", "C:/Maria-809-555-1234"),
    ],
    ids=["value-error", "path-too-long", "refused"],
)
def test_resolve_too_long_an_error_of_resolve_is_the_same_project_error_without_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def refuse(self: Path, strict: bool = False) -> Path:
        raise error

    monkeypatch.setattr(Path, "resolve", refuse)
    with pytest.raises(ProjectError) as info:
        resolve_in_project(tmp_path, "recursos/Maria-809-555-1234.png")
    assert info.value.message_es == UNRESOLVABLE


def test_resolve_too_long_a_good_path_and_the_old_refusals_are_the_same(tmp_path: Path) -> None:
    assert resolve_in_project(tmp_path, "recursos/x.png").name == "x.png"
    with pytest.raises(ProjectError) as info:
        resolve_in_project(tmp_path, "../x.png")
    assert info.value.message_es != UNRESOLVABLE  # leaving the project is still its own message


def _manifest(project: Project, file: str) -> None:
    item: dict[str, Any] = {
        "file": file,
        "kind": "imagen",
        "origin": "propio",
        "license": "propia",
        "obtained": "2026-10-28",
        "approved_by": "test",
    }
    text = json.dumps({"schema": "kcut.recursos/1", "items": [item]})
    (project.root / "recursos" / "recursos.json").write_text(text, encoding="utf-8")


def test_resolve_too_long_a_file_of_40000_characters_in_the_manifest_is_exit_3_with_that_text(
    tmp_path: Path,
) -> None:
    project = make_project(tmp_path)
    _manifest(project, "recursos/" + "a" * 40000)
    with pytest.raises(ProjectError) as info:
        require_approved(project, "recursos/x.png")  # not a ValueError, which was exit 10
    assert info.value.exit_code == 3
    assert UNRESOLVABLE in info.value.message_es and "aaaa" not in info.value.message_es
