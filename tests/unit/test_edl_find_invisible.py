"""`find_edl` refuses a path with invisible characters (spec 001.51 point 9, row 34a)."""

from pathlib import Path

import pytest

from kcut.edl.files import find_edl
from kcut.errors import ProjectError
from kcut.project import open_project


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proyecto"
    (root / "edit").mkdir(parents=True)
    (root / "kcut.toml").write_text("", encoding="utf-8")
    return root


@pytest.mark.parametrize(
    "char", ["\u202e", "\u200b", "\x1b", "\ufe0f"], ids=["rlo", "zwsp", "esc", "vs"]
)
def test_find_edl_invisible_characters_in_the_path_are_exit_3(tmp_path: Path, char: str) -> None:
    project = open_project(str(_project(tmp_path)))
    rel = f"edit/a{char}b/edl-v1.json"
    with pytest.raises(ProjectError) as caught:
        find_edl(project, rel)
    assert caught.value.exit_code == 3
    assert char not in str(caught.value)  # the message does not carry the character either


def test_find_edl_invisible_a_plain_accented_path_still_passes(tmp_path: Path) -> None:
    project = open_project(str(_project(tmp_path)))
    assert find_edl(project, "edit/ñandú/edl-v2.json") == ("edit/ñandú/edl-v2.json", 2)


@pytest.mark.parametrize("char", ["\n", "\r", "\r\n"], ids=["lf", "cr", "crlf"])
def test_find_edl_invisible_line_break_in_the_path_is_one_line_exit_3(
    tmp_path: Path, char: str
) -> None:
    project = open_project(str(_project(tmp_path)))
    rel = f"edit/a{char}[OK] listo/edl-v1.json"  # 001.52
    with pytest.raises(ProjectError) as caught:
        find_edl(project, rel)
    message = str(caught.value)
    assert caught.value.exit_code == 3
    assert "\n" not in message
    assert "\r" not in message
