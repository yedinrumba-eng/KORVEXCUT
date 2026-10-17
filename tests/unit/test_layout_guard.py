"""`check_layout_inside` names a file that sits where the layout expects a folder (001.7)."""

from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.paths import Layout
from kcut.project import check_layout_inside


@pytest.mark.parametrize("rel", ["crudo", "edit", "qa", ".kcut", ".kcut/wav16", ".kcut/logs"])
def test_layout_folder_is_file_is_named_with_its_relative_path(tmp_path: Path, rel: str) -> None:
    root = tmp_path / "proyecto ñandú"
    layout = Layout(root)
    for folder in layout.all_paths():
        folder.mkdir(parents=True, exist_ok=True)
    victim = root / rel
    for child in sorted(victim.rglob("*"), reverse=True):
        child.rmdir()
    victim.rmdir()
    victim.write_text("soy un archivo", encoding="utf-8")
    with pytest.raises(ProjectError) as info:
        check_layout_inside(root, layout)
    assert info.value.exit_code == 3
    assert info.value.message_es == f"hay un archivo donde kcut espera una carpeta: {rel}"


def test_a_complete_layout_of_real_folders_passes(tmp_path: Path) -> None:
    layout = Layout(tmp_path / "p")
    for folder in layout.all_paths():
        folder.mkdir(parents=True, exist_ok=True)
    check_layout_inside(layout.root, layout)
