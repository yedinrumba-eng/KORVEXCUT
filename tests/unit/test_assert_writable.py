"""`project.assert_writable`: the gate before every write outside `.kcut/` (spec 0.9, 001.15 T4).

It refuses a path that breaks the rules of 0.10.7, one that goes through a symlink or a junction,
one that leaves the project or lands in `crudo/`, and a target that is a folder or a hard link.
"""

import os
from pathlib import Path

import pytest

from kcut.errors import ProjectError, UsageError
from kcut.paths import Layout
from kcut.project import Project, assert_writable, open_project
from tests.fixtures.links import make_dir_link, make_hard_link, remove_dir_link


@pytest.fixture
def project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto ñandú"
    root.mkdir()
    (root / "kcut.toml").write_text("", encoding="utf-8")
    for folder in Layout(root).all_paths():
        folder.mkdir(parents=True, exist_ok=True)
    return open_project(str(root))


def _refused(project: Project, rel: str) -> ProjectError:
    with pytest.raises(ProjectError) as info:
        assert_writable(project, rel)
    assert info.value.exit_code == 3
    return info.value


class TestAllowed:
    def test_writable_a_new_file_in_an_existing_folder(self, project: Project) -> None:
        path = assert_writable(project, "edit/transcripcion.md")
        assert path == project.root.resolve() / "edit" / "transcripcion.md"
        assert path.is_absolute()

    def test_writable_an_existing_regular_file_is_fine(self, project: Project) -> None:
        (project.root / "edit" / "palabras.tsv").write_text("x", encoding="utf-8")
        assert assert_writable(project, "edit/palabras.tsv").name == "palabras.tsv"

    def test_writable_does_not_create_the_folders_it_names(self, project: Project) -> None:
        path = assert_writable(project, "qa/v3/contact.jpg")
        assert path.parent == project.root.resolve() / "qa" / "v3"
        assert not path.parent.exists()

    def test_writable_backslashes_and_dots_are_read_like_the_rest_of_the_paths(
        self, project: Project
    ) -> None:
        expected = project.root.resolve() / "edit" / "a.png"
        assert assert_writable(project, "edit\\a.png") == expected
        assert assert_writable(project, "./edit/./a.png") == expected
        assert assert_writable(project, "edit/sub/../a.png") == expected

    def test_writable_a_name_that_only_looks_like_crudo_is_fine(self, project: Project) -> None:
        assert assert_writable(project, "crudo2/a.png").name == "a.png"
        assert assert_writable(project, "crudo.txt").name == "crudo.txt"
        assert assert_writable(project, "edit/crudo/a.png").name == "a.png"


class TestRulesOfThePaths:
    @pytest.mark.parametrize(
        "rel",
        [
            "",
            "C:/Windows/x.png",
            "c:x.png",
            "//servidor/carpeta/x.png",
            "\\\\servidor\\carpeta\\x.png",
            "/etc/x.png",
            "\\x.png",
            "../fuera.png",
            "edit/../../fuera.png",
            "edit/x.png:flujo",
            "edit/x\x00.png",
            "con.png",
            "edit/NUL",
            "edit/lpt1.txt",
            "COM3",
        ],
    )
    def test_writable_refuses_what_resolve_in_project_refuses(
        self, project: Project, rel: str
    ) -> None:
        _refused(project, rel)

    def test_writable_a_path_with_nothing_in_it_is_refused(self, project: Project) -> None:
        for rel in (".", "./", "edit/..", "//"):
            _refused(project, rel)


class TestOutsideAndCrudo:
    @pytest.mark.parametrize(
        "rel",
        [
            "crudo/x.png",
            "crudo",
            "CRUDO/x.png",
            "Crudo/sub/x.png",
            "crudo./x.png",
            "crudo /x.png",
            "edit/../crudo/x.png",
            "./crudo/x.png",
            "crudo\\x.png",
        ],
    )
    def test_writable_nothing_goes_into_crudo(self, project: Project, rel: str) -> None:
        error = _refused(project, rel)
        assert "kcut no escribe en" in error.message_es

    def test_writable_a_name_with_trailing_dots_in_a_sub_path_of_crudo_is_still_crudo(
        self, project: Project
    ) -> None:
        _refused(project, "crudo/sub./x.png")

    def test_writable_a_file_inside_crudo_that_exists_stays_untouched(
        self, project: Project
    ) -> None:
        clip = project.root / "crudo" / "cam.mp4"
        clip.write_bytes(b"video")
        _refused(project, "crudo/cam.mp4")
        assert clip.read_bytes() == b"video"


class TestLinks:
    def test_writable_a_component_that_is_a_link_is_refused(
        self, project: Project, tmp_path: Path
    ) -> None:
        outside = tmp_path / "afuera"
        outside.mkdir()
        link = project.root / "qa" / "enlace"
        make_dir_link(link, outside)
        try:
            error = _refused(project, "qa/enlace/x.png")
            assert "pasa por un enlace (symlink o junction)" in error.message_es
            assert "qa/enlace/x.png" in error.message_es
            assert list(outside.iterdir()) == []
        finally:
            remove_dir_link(link)

    def test_writable_a_link_that_points_inside_the_project_is_refused_too(
        self, project: Project
    ) -> None:
        link = project.root / "qa" / "atajo"
        make_dir_link(link, project.root / "edit")
        try:
            _refused(project, "qa/atajo/x.png")
        finally:
            remove_dir_link(link)

    def test_writable_a_link_to_crudo_is_refused_as_a_link(self, project: Project) -> None:
        link = project.root / "salida" / "vista"
        make_dir_link(link, project.root / "crudo")
        try:
            error = _refused(project, "salida/vista/x.png")
            assert "enlace" in error.message_es
        finally:
            remove_dir_link(link)

    def test_writable_the_last_component_being_a_link_is_refused(
        self, project: Project, tmp_path: Path
    ) -> None:
        outside = tmp_path / "afuera"
        outside.mkdir()
        link = project.root / "qa" / "carpeta"
        make_dir_link(link, outside)
        try:
            _refused(project, "qa/carpeta")
        finally:
            remove_dir_link(link)


class TestTargetKinds:
    def test_writable_a_folder_where_a_file_goes_is_refused_with_the_known_message(
        self, project: Project
    ) -> None:
        (project.root / "qa" / "v1").mkdir()
        error = _refused(project, "qa/v1")
        assert "hay una carpeta donde kcut espera un archivo" in error.message_es

    def test_writable_a_hard_link_is_refused(self, project: Project, tmp_path: Path) -> None:
        secret = tmp_path / "secreto.md"
        secret.write_text("no tocar", encoding="utf-8")
        planted = project.root / "edit" / "transcripcion.md"
        make_hard_link(planted, secret)
        assert os.lstat(planted).st_nlink > 1
        error = _refused(project, "edit/transcripcion.md")
        assert "enlace duro" in error.message_es
        assert secret.read_text(encoding="utf-8") == "no tocar"

    def test_writable_a_file_with_one_name_is_not_a_hard_link(self, project: Project) -> None:
        (project.root / "edit" / "a.md").write_text("x", encoding="utf-8")
        assert assert_writable(project, "edit/a.md").is_file()


class TestOutNoOverwrite:
    """001.20 point 9: a file that is already there outside `.kcut/` is not replaced unless the
    caller says so (`replace=True`, which is what `--force` means)."""

    def test_out_no_overwrite_an_existing_file_is_a_usage_error_that_names_it(
        self, project: Project
    ) -> None:
        (project.root / "recursos" / "logo.png").write_bytes(b"LOGO")
        with pytest.raises(UsageError) as info:
            assert_writable(project, "recursos/logo.png", replace=False)
        assert info.value.exit_code == 2
        assert "recursos/logo.png" in info.value.message_es and "--force" in info.value.message_es
        assert (project.root / "recursos" / "logo.png").read_bytes() == b"LOGO"

    def test_out_no_overwrite_a_new_file_is_fine(self, project: Project) -> None:
        assert assert_writable(project, "edit/nuevo.png", replace=False).name == "nuevo.png"

    def test_out_no_overwrite_with_replace_the_existing_file_passes(self, project: Project) -> None:
        (project.root / "edit" / "a.png").write_bytes(b"x")
        assert assert_writable(project, "edit/a.png", replace=True).name == "a.png"

    def test_out_no_overwrite_the_default_is_to_replace_as_pack_does_every_run(
        self, project: Project
    ) -> None:
        (project.root / "edit" / "transcripcion.md").write_text("viejo", encoding="utf-8")
        assert assert_writable(project, "edit/transcripcion.md").name == "transcripcion.md"

    def test_out_no_overwrite_the_other_refusals_come_first(self, project: Project) -> None:
        with pytest.raises(ProjectError):
            assert_writable(project, "crudo/x.png", replace=False)
        (project.root / "qa" / "carpeta").mkdir()
        with pytest.raises(ProjectError, match="hay una carpeta"):
            assert_writable(project, "qa/carpeta", replace=False)


class TestKcutDirReplaces:
    """001.21 point 6: `.kcut/` is kcut's own folder; a file there is replaced without `--force`
    (001.20, point 9 spoke of what is outside it)."""

    def test_kcut_dir_replaces_an_existing_file_under_kcut_passes_without_force(
        self, project: Project
    ) -> None:
        folder = project.root / ".kcut" / "frames"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "a1_f30.png").write_bytes(b"viejo")
        path = assert_writable(project, ".kcut/frames/a1_f30.png", replace=False)
        assert path.name == "a1_f30.png"

    @pytest.mark.parametrize(
        "rel", ["otra/a.png", ".kcut2/a.png", "kcut/a.png", "edit/.kcut/a.png"]
    )
    def test_kcut_dir_replaces_only_the_folder_called_kcut_does(
        self, project: Project, rel: str
    ) -> None:
        target = project.root.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"viejo")
        with pytest.raises(UsageError) as info:
            assert_writable(project, rel, replace=False)
        assert info.value.exit_code == 2 and rel in info.value.message_es

    def test_kcut_dir_replaces_the_other_refusals_still_apply_under_kcut(
        self, project: Project
    ) -> None:
        (project.root / ".kcut" / "carpeta").mkdir(parents=True, exist_ok=True)
        with pytest.raises(ProjectError, match="hay una carpeta"):
            assert_writable(project, ".kcut/carpeta", replace=False)
