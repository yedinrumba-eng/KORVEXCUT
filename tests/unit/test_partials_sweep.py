"""The sweep of orphan partial files (spec S1.6a step 0, 001.27 point 1; row 12).

A partial file or a temporary of a sidecar with a pid, more than 24 h old, in `.kcut/mezz`,
`.kcut/wav16`, `.kcut/wav48` or `.kcut/proxy`, belongs to a render that was killed. Everything that
is not exactly that stays where it is.
"""

import os
from pathlib import Path

import pytest

from kcut.config.load import parse_config
from kcut.ingest.partials import ORPHAN_AGE_S, sweep_orphan_partials
from kcut.paths import Layout
from kcut.project import Project
from tests.fixtures.links import make_dir_link, make_hard_link, remove_dir_link

NOW = 1_800_000_000.0
HOUR = 3600.0


@pytest.fixture
def project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto ñandú"
    for folder in ("mezz", "wav16", "wav48", "proxy"):
        (root / ".kcut" / folder).mkdir(parents=True)
    (root / "crudo").mkdir()
    return Project(root, parse_config("", default_name="x"), Layout(root))


def _plant(path: Path, hours: float, content: bytes = b"half a file") -> Path:
    """A file whose modification time is `hours` before `NOW`."""
    path.write_bytes(content)
    when = NOW - hours * HOUR
    os.utime(path, (when, when))
    return path


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_the_age_is_a_day() -> None:
    assert ORPHAN_AGE_S == 86400


class TestSweep:
    def test_orphan_partials_old_ones_go_and_the_rest_stays(self, project: Project) -> None:
        wav48, mezz = project.layout.wav48, project.layout.mezz
        _plant(wav48 / "a1_x.4242.partial.wav", 25)
        _plant(mezz / "a1_x.mp4.json.4242.tmp", 25)
        _plant(wav48 / "a1_y.4242.partial.wav", 1)  # a render that is alive
        _plant(wav48 / "a1_x.wav", 25)  # old, but not a partial
        _plant(wav48 / "a1_x.wav.json", 25)
        assert sweep_orphan_partials(project, now=NOW) == 2
        assert _names(wav48) == ["a1_x.wav", "a1_x.wav.json", "a1_y.4242.partial.wav"]
        assert _names(mezz) == []

    def test_orphan_partials_the_four_folders_are_swept(self, project: Project) -> None:
        layout = project.layout
        _plant(layout.mezz / "a1_45-135_1440x2560_tm2.17.partial.mp4", 30)
        _plant(layout.wav16 / "a1_x.123456.partial.wav", 30)
        _plant(layout.wav48 / "a1_x.4242.partial.wav", 30)
        _plant(layout.proxy / "b1_x.9.partial.mp4", 30)
        _plant(layout.wav16 / "a1_x.wav.json.55.tmp", 30)
        _plant(layout.proxy / "b1_x.5.partial", 30)  # no extension: `voice_raw.f32.<pid>.partial`
        assert sweep_orphan_partials(project, now=NOW) == 6
        assert all(_names(f) == [] for f in (layout.mezz, layout.wav16, layout.wav48, layout.proxy))

    def test_orphan_partials_exactly_a_day_old_stays_and_a_second_more_goes(
        self, project: Project
    ) -> None:
        folder = project.layout.wav48
        _plant(folder / "a1_x.4242.partial.wav", 24)
        assert sweep_orphan_partials(project, now=NOW) == 0
        assert sweep_orphan_partials(project, now=NOW + 1) == 1
        assert _names(folder) == []

    @pytest.mark.parametrize(
        "name",
        [
            "a1_x.12345678901.partial.wav",  # a pid has at most 10 digits
            "a1_x.4242.partial.verylongext",  # an extension of at most 8 characters
            "a1_x.4242.partial.wav.bak",
            "a1_x.partial.wav",  # no pid
            "a1_x.abc.partial.wav",
            "a1_x.4242.tmp.bak",
            ".4242.tmp",  # no name before the pid
            "a1_x.tmp",
            "a1_x.wav",
        ],
    )
    def test_orphan_partials_a_name_that_is_not_exactly_a_partial_stays(
        self, project: Project, name: str
    ) -> None:
        _plant(project.layout.wav48 / name, 100)
        assert sweep_orphan_partials(project, now=NOW) == 0
        assert _names(project.layout.wav48) == [name]

    def test_orphan_partials_without_now_the_clock_is_used(self, project: Project) -> None:
        old = project.layout.mezz / "a1_x.4242.partial.mp4"
        old.write_bytes(b"x")
        when = old.stat().st_mtime - 2 * ORPHAN_AGE_S
        os.utime(old, (when, when))
        assert sweep_orphan_partials(project) == 1
        assert not old.exists()

    def test_orphan_partials_missing_folders_are_not_an_error(self, tmp_path: Path) -> None:
        root = tmp_path / "proyecto"
        root.mkdir()
        project = Project(root, parse_config("", default_name="x"), Layout(root))
        assert sweep_orphan_partials(project, now=NOW) == 0


class TestWhatStays:
    """A folder, a link and a file that does not let itself be deleted stay, with no error."""

    def test_orphan_partials_a_subfolder_is_not_entered_and_a_folder_with_a_partial_name_stays(
        self, project: Project
    ) -> None:
        mezz = project.layout.mezz
        folder = mezz / "a1_d.4242.partial.mp4"
        folder.mkdir()
        os.utime(folder, (NOW - 100 * HOUR, NOW - 100 * HOUR))
        (mezz / "sub").mkdir()
        inner = _plant(mezz / "sub" / "a1_x.4242.partial.mp4", 100)
        assert sweep_orphan_partials(project, now=NOW) == 0
        assert folder.is_dir() and inner.is_file()

    def test_orphan_partials_a_junction_or_symlink_with_a_partial_name_stays_with_its_target(
        self, project: Project, tmp_path: Path
    ) -> None:
        target = tmp_path / "carpeta ajena"
        target.mkdir()
        precious = _plant(target / "precious.txt", 100, b"PRECIOUS")
        link = project.layout.wav48 / "a1_j.4242.partial.wav"
        make_dir_link(link, target)
        try:
            assert sweep_orphan_partials(project, now=NOW) == 0
            assert os.path.lexists(link)
            assert precious.read_bytes() == b"PRECIOUS"
        finally:
            remove_dir_link(link)

    def test_orphan_partials_a_hard_link_with_a_partial_name_stays_and_so_does_its_twin(
        self, project: Project, tmp_path: Path
    ) -> None:
        outside = _plant(tmp_path / "ajeno.mp4", 100, b"FOOTAGE-OF-SOMEONE")
        link = project.layout.mezz / "a1_h.4242.partial.mp4"
        make_hard_link(link, outside)
        assert sweep_orphan_partials(project, now=NOW) == 0
        assert link.read_bytes() == outside.read_bytes() == b"FOOTAGE-OF-SOMEONE"
        assert outside.stat().st_nlink == 2

    def test_orphan_partials_a_file_that_cannot_be_deleted_stays_without_an_error(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        folder = project.layout.wav48
        stuck = _plant(folder / "a1_s.4242.partial.wav", 100)
        gone = _plant(folder / "a1_g.4242.partial.wav", 100)
        real = Path.unlink

        def unlink(self: Path, missing_ok: bool = False) -> None:
            if self.name == stuck.name:  # on Windows, a file another process has open
                raise PermissionError(13, "Access is denied", str(self))
            real(self, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", unlink)
        assert sweep_orphan_partials(project, now=NOW) == 1  # only the one that was deleted
        assert stuck.exists() and not gone.exists()

    def test_orphan_partials_a_folder_of_the_cache_that_leads_outside_is_not_swept(
        self, project: Project, tmp_path: Path
    ) -> None:
        outside = tmp_path / "fuera"
        outside.mkdir()
        victim = _plant(outside / "a1_x.4242.partial.wav", 100)
        project.layout.wav48.rmdir()
        make_dir_link(project.layout.wav48, outside)  # `.kcut/wav48` leads out of `.kcut/`
        try:
            assert sweep_orphan_partials(project, now=NOW) == 0
            assert victim.exists()
        finally:
            remove_dir_link(project.layout.wav48)
