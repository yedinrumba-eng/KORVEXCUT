"""The guard of `.kcut/` names a work file by class and clip (spec S1.6b step 0, 001.30 point 2;
row 14): with a `label`, `assert_in_cache` says `wav48 de a1` where it used to say the path, and
`workfiles._build` always gives it one, because the name of a work file has the slug of the original
clip and that slug may hold a phone number.

Collected from `test_workfiles.py`, whose `project` fixture (a project with `.kcut/wav16/` and
`crudo/`) these use.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from kcut import proc
from kcut.errors import ProjectError
from kcut.ingest import workfiles
from kcut.ingest.cache_guard import assert_in_cache
from kcut.project import Project
from tests.fixtures.links import make_dir_link, remove_dir_link

__all__ = ["TestCacheGuardLabel"]
NAME = "a1_ana-perez-809-555-1234.wav"
LEAKS = ("809", "555", "1234", "ana", "perez", ":\\")
JOB = ("sha256:abc", {"sr": 48000}, 1.0)
LABEL = "wav48 de a1"


def _clean(message: str) -> bool:
    return not any(piece in message.lower() for piece in LEAKS)


class TestCacheGuardLabel:
    @pytest.fixture
    def outside(self, tmp_path: Path) -> Path:
        folder = tmp_path / "ajeno"
        folder.mkdir()
        return folder

    @pytest.fixture
    def dst(self, project: Project) -> Path:
        dst = project.layout.wav48 / NAME
        dst.parent.mkdir(parents=True, exist_ok=True)
        return dst

    @pytest.fixture
    def ffmpeg_never_runs(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[list[object]]:
        runs: list[object] = []
        monkeypatch.setattr(proc, "run", lambda *a, **_k: runs.append(a))
        yield runs

    @staticmethod
    def _build(project: Project, dst: Path) -> None:
        workfiles._build(project, lambda out: ["ffmpeg", str(out)], dst, JOB, None)

    def test_cache_guard_label_a_label_replaces_the_path_in_the_message(
        self, project: Project, tmp_path: Path
    ) -> None:
        target = tmp_path / "afuera" / NAME
        with pytest.raises(ProjectError) as info:
            assert_in_cache(project, target, label=LABEL)
        assert info.value.message_es == (
            "wav48 de a1 queda fuera de .kcut/: kcut no escribe, mueve ni borra ahí"
        )
        assert _clean(info.value.message_es) and info.value.exit_code == 3

    def test_cache_guard_label_without_one_the_message_names_the_path_as_before(
        self, project: Project, tmp_path: Path
    ) -> None:
        target = tmp_path / "afuera" / NAME
        with pytest.raises(ProjectError) as info:
            assert_in_cache(project, target)
        assert info.value.message_es == (
            f"{target} queda fuera de .kcut/: kcut no escribe, mueve ni borra ahí"
        )

    def test_cache_guard_label_a_label_does_not_change_a_path_that_is_inside(
        self, project: Project, dst: Path
    ) -> None:
        assert assert_in_cache(project, dst, label=LABEL) == assert_in_cache(project, dst)

    @pytest.mark.parametrize("which", ["dst", "partial", "sidecar"])
    def test_cache_guard_label_build_with_a_junction_out_of_the_cache_says_class_and_clip(
        self,
        project: Project,
        dst: Path,
        outside: Path,
        ffmpeg_never_runs: list[object],
        which: str,
    ) -> None:
        partial = dst.with_name(f"{dst.stem}.{os.getpid()}.partial{dst.suffix}")
        link = {"dst": dst, "partial": partial, "sidecar": workfiles.sidecar_path(dst)}[which]
        make_dir_link(link, outside)
        try:
            with pytest.raises(ProjectError) as info:
                self._build(project, dst)
        finally:
            remove_dir_link(link)
        message = info.value.message_es
        assert info.value.exit_code == 3 and message.startswith(f"{LABEL} queda fuera de .kcut/")
        assert _clean(message)
        assert ffmpeg_never_runs == []  # it stopped before touching the disk
