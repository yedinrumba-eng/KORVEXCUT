"""Path safety (spec 0.10.7) and the project layout (spec 0.3)."""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.paths import (
    Layout,
    find_project,
    inside_kcut_repo,
    log_path,
    resolve_in_project,
    to_rel,
)
from tests.unit.paths_prefix_cases import *  # noqa: F403  (001.28: 300-line rule)


def _link_dir(link: Path, target: Path) -> None:
    """Symlink, or a directory junction on Windows when symlinks need a privilege we lack."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError as exc:
        reason = str(exc)
    if sys.platform == "win32":
        made = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        if made.returncode == 0:
            return
        reason += f"; mklink /J fallo con codigo {made.returncode}"
    pytest.skip(f"no se pudo crear un enlace de directorio: {reason}")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "proyecto ñandú"
    folder.mkdir()
    return folder


class TestResolveAccepts:
    @pytest.mark.parametrize(
        "rel",
        [
            "recursos/logos/logo.png",
            "crudo/cámara ñandú/clip 1.mov",
            "edit/edl-v1.json",
            "a/../b/c.txt",
            "./edit/./x.json",
            "recursos//doble.png",
            "recursos\\con-barra-invertida.png",
            "console/x.png",
            "comx.txt",
            "auxiliar.png",
        ],
    )
    def test_safe_relative_paths(self, root: Path, rel: str) -> None:
        target = resolve_in_project(root, rel)
        assert target.is_absolute()
        assert os.path.normcase(str(target)).startswith(os.path.normcase(str(root.resolve())))

    def test_result_is_resolved_and_inside_root(self, root: Path) -> None:
        target = resolve_in_project(root, "a/../b/c.txt")
        assert target == root.resolve() / "b" / "c.txt"

    def test_file_does_not_need_to_exist(self, root: Path) -> None:
        assert not resolve_in_project(root, "salida/v1.mp4").exists()


class TestResolveRejects:
    @pytest.mark.parametrize(
        "rel",
        [
            "../fuera.txt",
            "a/../../fuera.txt",
            "..",
            "a/b/../../..",
            "..\\fuera.txt",
        ],
    )
    def test_traversal(self, root: Path, rel: str) -> None:
        with pytest.raises(ProjectError):
            resolve_in_project(root, rel)

    @pytest.mark.parametrize(
        "rel",
        ["/etc/passwd", "\\windows\\system32", "C:/Windows/x.dll", "c:x.txt", "D:\\datos\\a.mov"],
    )
    def test_absolute_and_drive_letters(self, root: Path, rel: str) -> None:
        with pytest.raises(ProjectError):
            resolve_in_project(root, rel)

    @pytest.mark.parametrize("rel", ["\\\\servidor\\recurso\\x.png", "//servidor/recurso/x.png"])
    def test_unc(self, root: Path, rel: str) -> None:
        with pytest.raises(ProjectError, match="UNC"):
            resolve_in_project(root, rel)

    @pytest.mark.parametrize("rel", ["archivo.txt:oculto", "crudo/a.mov::$DATA", "x:y"])
    def test_alternate_data_streams(self, root: Path, rel: str) -> None:
        with pytest.raises(ProjectError):
            resolve_in_project(root, rel)

    def test_nul_byte(self, root: Path) -> None:
        with pytest.raises(ProjectError, match="NUL"):
            resolve_in_project(root, "crudo/a\x00.mov")

    @pytest.mark.parametrize(
        "rel",
        [
            "CON",
            "con.txt",
            "recursos/aux/logo.png",
            "NUL.json",
            "crudo/Prn.mp4",
            "COM1",
            "com9.log",
            "LPT1",
            "lpt9.txt",
            "recursos/CON .png",
        ],
    )
    def test_reserved_windows_names(self, root: Path, rel: str) -> None:
        with pytest.raises(ProjectError, match="reservado"):
            resolve_in_project(root, rel)

    @pytest.mark.parametrize("rel", ["", ".", "./", "a/.."])
    def test_empty_or_pointing_at_nothing(self, root: Path, rel: str) -> None:
        with pytest.raises(ProjectError):
            resolve_in_project(root, rel)

    def test_symlink_escaping_the_project_is_rejected(self, root: Path, tmp_path: Path) -> None:
        outside = tmp_path / "afuera"
        outside.mkdir()
        _link_dir(root / "enlace", outside)
        with pytest.raises(ProjectError, match="sale del proyecto"):
            resolve_in_project(root, "enlace/x.txt")

    def test_errors_are_exit_code_3(self, root: Path) -> None:
        with pytest.raises(ProjectError) as info:
            resolve_in_project(root, "../x")
        assert info.value.exit_code == 3


class TestToRel:
    def test_posix_relative(self, root: Path) -> None:
        assert to_rel(root, root / "crudo" / "cámara 1" / "a.mov") == "crudo/cámara 1/a.mov"

    def test_outside_the_project_is_an_error(self, root: Path, tmp_path: Path) -> None:
        with pytest.raises(ProjectError):
            to_rel(root, tmp_path / "otro.txt")


class TestLayout:
    def test_every_path_of_spec_0_3(self, root: Path) -> None:
        lay = Layout(root)
        assert lay.crudo == root / "crudo"
        assert lay.manifest == root / "recursos" / "recursos.json"
        assert lay.edit == root / "edit"
        assert lay.salida == root / "salida"
        assert lay.qa == root / "qa"
        assert lay.cache == root / ".kcut"
        assert lay.inventory == root / ".kcut" / "inventory.json"
        for name in ("proxy", "wav16", "wav48", "mezz", "transcripts", "view", "frames", "build"):
            assert getattr(lay, name) == root / ".kcut" / name
        assert lay.storyboard_cache == root / ".kcut" / "storyboard"
        assert lay.logs == root / ".kcut" / "logs"
        assert lay.locks == root / ".kcut" / "locks"

    def test_versioned_dirs(self, root: Path) -> None:
        lay = Layout(root)
        assert lay.build_dir(3) == root / ".kcut" / "build" / "v3"
        assert lay.qa_dir(2) == root / "qa" / "v2"


class TestFindProject:
    def test_climbs_to_kcut_toml(self, root: Path) -> None:
        (root / "kcut.toml").write_text("", encoding="utf-8")
        deep = root / "crudo" / "sub"
        deep.mkdir(parents=True)
        assert find_project(deep) == root.resolve()

    def test_not_found_is_project_error(self, tmp_path: Path) -> None:
        lonely = tmp_path / "vacio"
        lonely.mkdir()
        with pytest.raises(ProjectError, match=r"kcut\.toml"):
            find_project(lonely)


class TestInsideKcutRepo:
    def test_a_folder_under_a_kcut_checkout(self, tmp_path: Path) -> None:
        package = tmp_path / "repo" / "src" / "kcut"
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        assert inside_kcut_repo(tmp_path / "repo" / "videos" / "nuevo") is True
        assert inside_kcut_repo(tmp_path / "repo") is True

    def test_an_unrelated_folder(self, tmp_path: Path) -> None:
        assert inside_kcut_repo(tmp_path / "mis videos") is False


def test_log_path_name() -> None:
    when = datetime(2026, 10, 16, 9, 5, 7)
    expected = Path("x") / "ingest-20261016-090507-1234.log"
    assert log_path(Path("x"), "ingest", when, pid=1234) == expected
    assert log_path(Path("x"), "ingest", when).name == f"ingest-20261016-090507-{os.getpid()}.log"
