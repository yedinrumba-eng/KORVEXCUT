"""Small behaviours of the work-file helpers: copying, directories in the way, safe names."""

from pathlib import Path

import pytest

from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.ingest import workfiles
from kcut.ingest.workfiles import _copy
from kcut.paths import Layout
from kcut.project import Project
from tests.fixtures.links import make_dir_link


@pytest.fixture
def project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto ñandú"
    (root / ".kcut" / "wav16").mkdir(parents=True)
    (root / "crudo").mkdir()
    return Project(root, parse_config("", default_name="x"), Layout(root))


class TestCopy:
    def test_copy_same_path_does_nothing_and_keeps_the_file(self, tmp_path: Path) -> None:
        f = tmp_path / "a.wav"
        f.write_bytes(b"audio")
        _copy(f, f)
        assert f.read_bytes() == b"audio"

    def test_copy_same_file_through_another_spelling_keeps_it(self, tmp_path: Path) -> None:
        folder = tmp_path / "carpeta"
        folder.mkdir()
        f = folder / "a.wav"
        f.write_bytes(b"audio")
        _copy(f, folder / ".." / "carpeta" / "a.wav")
        assert f.read_bytes() == b"audio"

    def test_copy_same_file_through_a_link_keeps_it(self, tmp_path: Path) -> None:
        folder = tmp_path / "real"
        folder.mkdir()
        f = folder / "a.wav"
        f.write_bytes(b"audio")
        make_dir_link(tmp_path / "enlace", folder)
        _copy(f, tmp_path / "enlace" / "a.wav")
        assert f.read_bytes() == b"audio"

    def test_a_real_copy_replaces_the_destination(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "a.wav", tmp_path / "b.wav"
        src.write_bytes(b"nuevo")
        dst.write_bytes(b"viejo y mas largo")
        _copy(src, dst)
        assert dst.read_bytes() == b"nuevo"
        assert src.read_bytes() == b"nuevo"

    def test_adopt_copy_with_the_same_source_and_destination_keeps_the_file(
        self, project: Project
    ) -> None:
        wav = project.layout.wav16 / "a1_x.wav"
        wav.write_bytes(b"audio")
        workfiles.sidecar_path(wav).write_text("{}", encoding="utf-8")
        workfiles.adopt(project, wav, wav, copy=True)
        assert wav.read_bytes() == b"audio"
        assert workfiles.sidecar_path(wav).read_text(encoding="utf-8") == "{}"

    def test_a_directory_where_the_copy_goes_is_a_clear_error(self, tmp_path: Path) -> None:
        src, dst = tmp_path / "a.wav", tmp_path / "b.wav"
        src.write_bytes(b"x")
        dst.mkdir()
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            _copy(src, dst)


class TestDirectoryInTheWay:
    def test_replace_onto_a_directory_names_the_problem(self, project: Project) -> None:
        src = project.layout.wav16 / "stage.wav"
        src.write_bytes(b"x")
        dst = project.layout.wav16 / "a1_x.wav"
        dst.mkdir()
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            workfiles.adopt(project, src, dst)
        assert src.is_file()

    def test_the_message_is_not_the_player_one(self, project: Project) -> None:
        dst = project.layout.wav16 / "a1_x.wav"
        dst.mkdir()
        with pytest.raises(ProjectError) as info:
            workfiles.adopt(project, project.layout.wav16 / "no-existe.wav", dst)
        assert "reproductor" not in info.value.message_es
