"""The calls of the guard of `.kcut/` that had no label (spec S1.6b round 1, 001.31 point 8;
row 26):
`workfiles.adopt`, `workfiles.discard` and `mezz_files.build_mezz` name a work file by class and
clip (`wav16 de a1`, `mezz de a1`) and its sidecar by the one of the file it goes with (`el sidecar
del wav16 de a1`), like `_build` does since 001.30: the name of a work file has the slug of the
original clip, and that slug may hold a phone number.

Collected from `test_workfiles.py`, whose `project` fixture (a project with `.kcut/wav16/` and
`crudo/`) these use; the mezzanine one is collected from `test_mezz_plan.py` (`mezz_project`).
"""

from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.ingest import workfiles
from kcut.project import Project
from kcut.render.mezz_files import build_mezz
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.unit.mezz_build_cases import _Fake
from tests.unit.mezz_files_cases import FPS, _a1, _job

__all__ = ["TestCacheGuardLabelV2", "TestCacheGuardLabelV2Mezz"]
NAME = "a1_ana-perez-809-555-1234.wav"
LEAKS = ("809", "555", "1234", "ana", "perez", ":\\")


def _clean(message: str) -> bool:
    return not any(piece in message.lower() for piece in LEAKS)


class TestCacheGuardLabelV2:
    @pytest.fixture
    def outside(self, tmp_path: Path) -> Path:
        folder = tmp_path / "ajeno"
        folder.mkdir()
        return folder

    @staticmethod
    def _stage(project: Project) -> Path:
        stage = project.layout.wav16 / "stage-1.wav"
        stage.write_bytes(b"audio")
        return stage

    def test_cache_guard_label_v2_adopt_into_a_junction_says_the_class_and_the_clip(
        self, project: Project, outside: Path
    ) -> None:
        stage, dst = self._stage(project), project.layout.wav16 / NAME
        make_dir_link(dst, outside)
        try:
            with pytest.raises(ProjectError) as info:
                workfiles.adopt(project, stage, dst)
        finally:
            remove_dir_link(dst)
        message = info.value.message_es
        assert info.value.exit_code == 3 and message.startswith("wav16 de a1 queda fuera de .kcut/")
        assert _clean(message) and stage.read_bytes() == b"audio"
        assert list(outside.iterdir()) == []

    def test_cache_guard_label_v2_adopt_with_a_sidecar_that_is_a_junction_names_the_sidecar(
        self, project: Project, outside: Path
    ) -> None:
        stage, dst = self._stage(project), project.layout.wav16 / NAME
        workfiles.sidecar_path(stage).write_text("{}", encoding="utf-8")
        link = workfiles.sidecar_path(dst)
        make_dir_link(link, outside)
        try:
            with pytest.raises(ProjectError) as info:
                workfiles.adopt(project, stage, dst)
        finally:
            remove_dir_link(link)
        message = info.value.message_es
        assert message.startswith("el sidecar del wav16 de a1 queda fuera de .kcut/"), message
        assert _clean(message)

    def test_cache_guard_label_v2_adopt_from_a_junction_names_the_source_without_its_path(
        self, project: Project, outside: Path
    ) -> None:
        stage = project.layout.wav16 / "stage-1.wav"
        make_dir_link(stage, outside)
        try:
            with pytest.raises(ProjectError) as info:
                workfiles.adopt(project, stage, project.layout.wav16 / NAME)
        finally:
            remove_dir_link(stage)
        message = info.value.message_es
        assert message.startswith("wav16 de stage-1.wav queda fuera de .kcut/"), message
        assert ":\\" not in message

    def test_cache_guard_label_v2_discard_of_a_junction_says_the_class_and_the_clip(
        self, project: Project, outside: Path
    ) -> None:
        path = project.layout.wav16 / NAME
        make_dir_link(path, outside)
        try:
            with pytest.raises(ProjectError) as info:
                workfiles.discard(project, path)
        finally:
            remove_dir_link(path)
        message = info.value.message_es
        assert message.startswith("wav16 de a1 queda fuera de .kcut/"), message
        assert _clean(message) and list(outside.iterdir()) == []

    def test_cache_guard_label_v2_discard_with_a_sidecar_that_is_a_junction_names_the_sidecar(
        self, project: Project, outside: Path
    ) -> None:
        path = project.layout.wav16 / NAME
        path.write_bytes(b"audio")
        link = workfiles.sidecar_path(path)
        make_dir_link(link, outside)
        try:
            with pytest.raises(ProjectError) as info:
                workfiles.discard(project, path)
        finally:
            remove_dir_link(link)
        message = info.value.message_es
        assert message.startswith("el sidecar del wav16 de a1 queda fuera de .kcut/"), message
        assert _clean(message) and path.read_bytes() == b"audio"  # nothing was deleted

    def test_cache_guard_label_v2_a_file_that_is_inside_is_adopted_and_discarded_as_before(
        self, project: Project
    ) -> None:
        stage, dst = self._stage(project), project.layout.wav16 / NAME
        workfiles.sidecar_path(stage).write_text("{}", encoding="utf-8")
        workfiles.adopt(project, stage, dst)
        assert dst.read_bytes() == b"audio" and workfiles.sidecar_path(dst).is_file()
        workfiles.discard(project, dst)
        assert not dst.exists() and not workfiles.sidecar_path(dst).exists()


class TestCacheGuardLabelV2Mezz:
    def test_cache_guard_label_v2_build_mezz_with_a_junction_out_of_the_cache_says_the_clip(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        outside = mezz_project.root / "salida"  # inside the project, outside `.kcut/`
        outside.mkdir()
        dst = mezz_project.root / job.path
        make_dir_link(dst, outside)
        fake = _Fake(monkeypatch, made=90)
        try:
            with pytest.raises(ProjectError) as info:
                build_mezz(mezz_project, job, _a1(), FPS, None)
        finally:
            remove_dir_link(dst)
        message = info.value.message_es
        assert info.value.exit_code == 3 and message.startswith("mezz de a1 queda fuera de .kcut/")
        assert ":\\" not in message and fake.runs == []  # it stopped before touching the disk
        assert list(outside.iterdir()) == []
