"""`_assert_in_cache` and the work-file functions: nothing outside `.kcut/` is written, moved
or deleted, even when the paths come from a poisoned cache."""

import json
import os
from pathlib import Path

import pytest

from kcut import proc
from kcut.config.load import parse_config
from kcut.errors import ProjectError
from kcut.ingest import workfiles
from kcut.ingest.examine import _audio_peak
from kcut.ingest.inventory import Clip, WorkFiles
from kcut.ingest.naming import qhash
from kcut.ingest.scan import Found
from kcut.paths import Layout
from kcut.project import Project
from tests.fixtures.links import make_dir_link


class TestAssertInCache:
    @pytest.fixture
    def project(self, tmp_path: Path) -> Project:
        root = tmp_path / "proyecto ñandú"
        (root / "crudo").mkdir(parents=True)
        (root / ".kcut" / "wav16").mkdir(parents=True)
        return Project(root, parse_config("", default_name="x"), Layout(root))

    def test_paths_inside_the_cache_pass_even_if_missing(self, project: Project) -> None:
        inside = project.layout.wav16 / "a1_x.wav"
        assert workfiles._assert_in_cache(project, inside) == inside.resolve()

    @pytest.mark.parametrize("rel", ["crudo/cam a.mp4", "edit/estrategia.md", "../fuera.txt", "x"])
    def test_paths_outside_the_cache_are_refused(self, project: Project, rel: str) -> None:
        with pytest.raises(ProjectError, match=r"fuera de \.kcut"):
            workfiles._assert_in_cache(project, project.root / rel)

    def test_dot_dot_that_climbs_out_of_the_cache_is_refused(self, project: Project) -> None:
        sneaky = project.layout.wav16 / ".." / ".." / "crudo" / "cam a.mp4"
        with pytest.raises(ProjectError):
            workfiles._assert_in_cache(project, sneaky)

    def test_a_link_inside_the_cache_that_points_out_is_refused(
        self, project: Project, tmp_path: Path
    ) -> None:
        outside = tmp_path / "afuera"
        outside.mkdir()
        make_dir_link(project.layout.proxy, outside)
        with pytest.raises(ProjectError):
            workfiles._assert_in_cache(project, project.layout.proxy / "a1_x.mp4")

    def test_adopt_refuses_a_source_in_crudo_and_leaves_it_alone(self, project: Project) -> None:
        raw = project.root / "crudo" / "cam a.mp4"
        raw.write_bytes(b"footage")
        with pytest.raises(ProjectError):
            workfiles.adopt(project, raw, project.layout.wav16 / "a1_cam-a.wav")
        assert raw.read_bytes() == b"footage"
        assert not (project.layout.wav16 / "a1_cam-a.wav").exists()

    def test_adopt_refuses_a_destination_in_crudo(self, project: Project) -> None:
        staged = project.layout.wav16 / "stage-1.wav"
        staged.write_bytes(b"wav")
        with pytest.raises(ProjectError):
            workfiles.adopt(project, staged, project.root / "crudo" / "stolen.wav")
        assert staged.read_bytes() == b"wav"
        assert list((project.root / "crudo").iterdir()) == []

    def test_adopt_checks_the_sidecars_too(self, project: Project, tmp_path: Path) -> None:
        staged = project.layout.wav16 / "stage-1.wav"
        staged.write_bytes(b"wav")
        workfiles.sidecar_path(staged).write_text("{}", encoding="utf-8")
        outside = tmp_path / "afuera"
        outside.mkdir()
        make_dir_link(project.layout.wav16 / "enlace", outside)
        with pytest.raises(ProjectError):
            workfiles.adopt(project, staged, project.layout.wav16 / "enlace" / "a1.wav")
        assert list(outside.iterdir()) == []
        assert staged.is_file()

    def test_discard_refuses_a_file_of_crudo(self, project: Project) -> None:
        raw = project.root / "crudo" / "cam a.mp4"
        raw.write_bytes(b"footage")
        with pytest.raises(ProjectError):
            workfiles.discard(project, raw)
        assert raw.read_bytes() == b"footage"

    def test_discard_removes_a_cache_file_and_its_sidecar(self, project: Project) -> None:
        staged = project.layout.wav16 / "stage-1.wav"
        staged.write_bytes(b"wav")
        workfiles.sidecar_path(staged).write_text("{}", encoding="utf-8")
        workfiles.discard(project, staged)
        assert not staged.exists() and not workfiles.sidecar_path(staged).exists()

    def test_build_refuses_a_destination_outside_the_cache_before_running_ffmpeg(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def never(*_a: object, **_k: object) -> object:
            raise AssertionError("ffmpeg must not run")

        monkeypatch.setattr(proc, "run", never)
        target = project.root / "crudo" / "cam a.mp4"
        target.write_bytes(b"footage")
        with pytest.raises(ProjectError):
            workfiles._build(project, lambda out: ["x", str(out)], target, ("h", {}, 1.0), None)
        assert target.read_bytes() == b"footage"

    def test_build_refuses_a_partial_file_that_is_a_link_out_of_the_cache(
        self, project: Project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        victim_dir = tmp_path / "victima"
        victim_dir.mkdir()
        # 001.26: the partial has the pid in its name, so this is the file the build would use
        victim = victim_dir / f"a1_x.{os.getpid()}.partial.wav"
        victim.write_bytes(b"mia")
        make_dir_link(project.layout.wav48, victim_dir)
        monkeypatch.setattr(proc, "run", lambda *_a, **_k: pytest.fail("ffmpeg must not run"))
        with pytest.raises(ProjectError):
            workfiles._build(
                project, lambda out: ["x"], project.layout.wav48 / "a1_x.wav", ("h", {}, 1.0), None
            )
        assert victim.read_bytes() == b"mia"  # 001.26: the same file as above, with the pid


class TestOldWavReuse:
    def test_an_old_wav_outside_wav16_is_never_reused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "proyecto ñandú"
        (root / "crudo").mkdir(parents=True)
        (root / ".kcut" / "wav16").mkdir(parents=True)
        project = Project(root, parse_config("", default_name="x"), Layout(root))
        raw = root / "crudo" / "cam a.mp4"
        raw.write_bytes(b"footage")
        digest = qhash(raw)
        (root / "crudo" / "cam a.mp4.json").write_text(
            json.dumps({"qhash": digest, "params": workfiles.wav_params(16000)}), encoding="utf-8"
        )
        poisoned = Clip(
            "a1",
            "crudo/cam a.mp4",
            "cam-a",
            "video_voz",
            digest,
            7,
            work=WorkFiles(None, "crudo/cam a.mp4", 540, 960),
        )
        staged = project.layout.wav16 / "stage-fake.wav"
        monkeypatch.setattr(workfiles, "stage_wav16", lambda *_a, **_k: staged)
        monkeypatch.setattr("kcut.ingest.examine.wav_peak", lambda _p: 0.5)
        item = Found(rel="crudo/cam a.mp4", path=raw, size=7, hash=digest)

        _audio_peak(project, item, {digest: poisoned}, root / "log.txt", [])

        assert item.wav == staged  # a fresh staging, not the raw file
        assert raw.read_bytes() == b"footage"


class TestTheCacheMustBeTheRealKcut:
    """001.6: `layout.cache` has to be `<root>/.kcut` itself, and nothing under `crudo/` passes."""

    @pytest.fixture
    def root(self, tmp_path: Path) -> Path:
        folder = tmp_path / "proyecto ñandú"
        (folder / "crudo").mkdir(parents=True)
        (folder / "crudo" / "cam a.mp4").write_bytes(b"footage")
        return folder

    def test_a_kcut_linked_to_crudo_is_refused_even_for_paths_inside_it(self, root: Path) -> None:
        make_dir_link(root / ".kcut", root / "crudo")
        project = Project(root, parse_config("", default_name="x"), Layout(root))
        for target in (root / ".kcut" / "wav16" / "a1.wav", root / ".kcut" / "cam a.mp4"):
            # both spellings of `.kcut` resolve to crudo/, so the "not under crudo/" rule fires
            with pytest.raises(ProjectError, match=r"fuera de \.kcut"):
                workfiles._assert_in_cache(project, target)
        with pytest.raises(ProjectError):
            workfiles.discard(project, root / ".kcut" / "cam a.mp4")
        assert (root / "crudo" / "cam a.mp4").read_bytes() == b"footage"

    def test_a_layout_whose_cache_lives_somewhere_else_is_refused(
        self, root: Path, tmp_path: Path
    ) -> None:
        class Elsewhere(Layout):
            @property
            def cache(self) -> Path:
                return tmp_path / "otra cache"

        (tmp_path / "otra cache").mkdir()
        project = Project(root, parse_config("", default_name="x"), Elsewhere(root))
        with pytest.raises(ProjectError, match=r"no es la carpeta \.kcut real"):
            workfiles._assert_in_cache(project, tmp_path / "otra cache" / "x.wav")

    def test_a_cache_nested_under_crudo_is_refused(self, root: Path) -> None:
        class UnderCrudo(Layout):
            @property
            def cache(self) -> Path:
                return self.root / "crudo" / ".kcut"

        (root / "crudo" / ".kcut").mkdir()
        project = Project(root, parse_config("", default_name="x"), UnderCrudo(root))
        with pytest.raises(ProjectError):
            workfiles._assert_in_cache(project, root / "crudo" / ".kcut" / "x.wav")

    def test_the_real_cache_still_passes(self, root: Path) -> None:
        (root / ".kcut").mkdir()
        project = Project(root, parse_config("", default_name="x"), Layout(root))
        target = root / ".kcut" / "wav16" / "a1.wav"
        assert workfiles._assert_in_cache(project, target) == target.resolve()
