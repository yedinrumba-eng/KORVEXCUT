"""Paths that come with the extended-length prefix of Windows (spec 001.28, point 1; row 22).

`Path.resolve` leaves `\\\\?\\` on a file that another process is creating or replacing at that
very moment (CPython 3.12 `ntpath.realpath`), and `kcut render` then sometimes refused its own
`.kcut/mezz/...` as "outside the project". Every comparison of two resolved paths takes the prefix
off both sides (`plain_path`): `resolve_in_project`, `to_rel`, `is_inside`, `same_path` and the lock
key of the logs. Here `Path.resolve` is patched to do what Windows does.

Collected from `test_paths.py`. The copy and the build folder are in `workfiles_prefix_cases.py`
and `render_step0_cases.py`.
"""

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from kcut import logfile
from kcut.errors import ProjectError
from kcut.ingest import cache_guard
from kcut.paths import is_inside, plain_path, resolve_in_project, same_path, to_rel
from tests.fixtures.links import make_dir_link

__all__ = ["TestExtendedPrefixPaths"]
PREFIX = "\\\\?\\"
UNC_PREFIX = "\\\\?\\UNC\\"
windows_only = pytest.mark.skipif(
    sys.platform != "win32", reason="the prefix is how Windows resolves"
)


def prefixed(monkeypatch: pytest.MonkeyPatch, which: Callable[[Path], bool]) -> None:
    """`Path.resolve` leaves the `\\\\?\\` prefix on the paths for which `which(path)` is true."""
    real = Path.resolve

    def resolve(self: Path, strict: bool = False) -> Path:
        out = real(self, strict=strict)
        return Path(PREFIX + str(out)) if which(out) else out

    monkeypatch.setattr(Path, "resolve", resolve)


def _under_mezz(out: Path) -> bool:
    return ".kcut" in out.parts and "mezz" in out.parts


@windows_only
class TestExtendedPrefixPaths:
    @pytest.fixture
    def root(self, tmp_path: Path) -> Path:
        folder = tmp_path / "proyecto ñandú"
        (folder / ".kcut" / "mezz").mkdir(parents=True)
        return folder

    def test_extended_prefix_resolve_in_project_gives_the_path_without_it(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plain = root.resolve() / ".kcut" / "mezz" / "x.mp4"
        prefixed(monkeypatch, _under_mezz)
        assert str((root / ".kcut" / "mezz" / "x.mp4").resolve()).startswith(PREFIX)  # the trap
        found = resolve_in_project(root, ".kcut/mezz/x.mp4")
        assert str(found) == str(plain) and not str(found).startswith(PREFIX)

    def test_extended_prefix_resolve_in_project_with_it_on_the_root_too(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plain = root.resolve() / ".kcut" / "mezz" / "x.mp4"
        prefixed(monkeypatch, lambda _out: True)
        assert str(resolve_in_project(root, ".kcut/mezz/x.mp4")) == str(plain)

    def test_extended_prefix_resolve_in_project_still_refuses_what_leaves_the_project(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outside = root.parent / "afuera"
        outside.mkdir()
        make_dir_link(root / "enlace", outside)  # `enlace/` leaves the project
        prefixed(monkeypatch, lambda _out: True)
        with pytest.raises(ProjectError, match="sale del proyecto"):
            resolve_in_project(root, "enlace/x.mp4")

    def test_extended_prefix_to_rel_gives_the_relative_path(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = root / ".kcut" / "mezz" / "x.mp4"
        prefixed(monkeypatch, _under_mezz)
        assert to_rel(root, target) == ".kcut/mezz/x.mp4"

    def test_extended_prefix_to_rel_with_it_on_the_root_side(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = root / ".kcut" / "mezz" / "x.mp4"
        prefixed(monkeypatch, lambda out: out.name == root.name)
        assert to_rel(root, target) == ".kcut/mezz/x.mp4"

    def test_extended_prefix_to_rel_still_refuses_a_path_outside_the_project(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prefixed(monkeypatch, lambda _out: True)
        with pytest.raises(ProjectError, match="no está dentro del proyecto"):
            to_rel(root, root.parent / "otro" / "x.mp4")

    @pytest.mark.parametrize("wide", ["root", "target", "both"])
    def test_extended_prefix_is_inside_and_same_path_say_yes_with_it_on_either_side(
        self, root: Path, wide: str
    ) -> None:
        base, child = root.resolve(), root.resolve() / "a" / "x.mp4"
        a = Path(PREFIX + str(base)) if wide in ("root", "both") else base
        b = Path(PREFIX + str(child)) if wide in ("target", "both") else child
        assert is_inside(a, b)
        assert same_path(a, base) and same_path(base, a) and same_path(b, child)

    def test_extended_prefix_is_inside_and_same_path_say_no_for_what_is_not(
        self, root: Path
    ) -> None:
        base = root.resolve()
        other = Path(PREFIX + str(base.parent / "otro"))
        assert not is_inside(Path(PREFIX + str(base)), other)
        assert not is_inside(base, other)
        assert not same_path(Path(PREFIX + str(base)), other)
        assert not same_path(base, base / "a")
        # `proyecto` is not inside `proyecto ñandú`: the border of the folder name is respected
        sibling = Path(PREFIX + str(base) + "-copia" + "\\x")
        assert not is_inside(base, sibling)

    def test_extended_prefix_unc_paths_match_with_and_without_it(self) -> None:
        wide, plain = Path(UNC_PREFIX + "server\\share\\x"), Path("\\\\server\\share\\x")
        assert same_path(wide, plain) and same_path(plain, wide)
        assert is_inside(wide, Path("\\\\server\\share\\x\\y\\z.mp4"))
        assert is_inside(plain, Path(UNC_PREFIX + "server\\share\\x\\y\\z.mp4"))
        assert is_inside(wide, Path(UNC_PREFIX + "server\\share\\x\\y"))
        assert not is_inside(wide, Path("\\\\server\\share\\y"))
        assert not same_path(wide, Path("\\\\server\\share\\y"))

    def test_extended_prefix_the_lock_of_a_log_is_the_same_with_it_or_without_it(
        self, root: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        log = root / ".kcut" / "logs" / "render-1.log"
        log.parent.mkdir()
        plain = logfile._lock_for(log)
        prefixed(monkeypatch, lambda out: out.name == "render-1.log")
        assert logfile._lock_for(log) is plain  # the same lock: two writers do not race

    def test_extended_prefix_plain_path_moved_to_paths_and_is_still_in_cache_guard(self) -> None:
        assert cache_guard.plain_path is plain_path
        assert str(plain_path(Path(PREFIX + "C:\\p\\x"))) == "C:\\p\\x"
