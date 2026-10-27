"""Work files, S1.6a step 0 (spec 001.27, points 5 and 8; rows 16 and 19): the temporary of the
sidecar of a work file has the pid, and a work file or a mezzanine that is not a regular file with
a single link is stale whatever its sidecar says.

Collected from `test_workfiles.py`, whose `project` fixture (a project with `.kcut/wav16/` and
`crudo/`) these use.
"""

import os
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.ingest import workfiles
from kcut.ingest.sidecar import is_lone_file
from kcut.project import Project
from kcut.render import mezz_files
from kcut.render.mezz_files import params_of
from tests.fixtures.links import make_hard_link
from tests.unit.mezz_files_cases import FPS, _a1, _job, _plant, mezz_project

__all__ = ["TestHardlinkStale", "TestSidecarTmpPid", "mezz_project"]
QHASH = "sha256:abc"
PARAMS: dict[str, Any] = {"sr": 48000}


class TestSidecarTmpPid:
    """Row 16: the sidecar of a wav16, a wav48 or a proxy is written through `<sidecar>.<pid>.tmp`
    and `os.replace`, not through the shared `<sidecar>.tmp` of before."""

    @pytest.mark.parametrize(
        ("folder", "name"),
        [("wav16", "a1_clip.wav"), ("wav48", "a1_clip.wav"), ("proxy", "a1_clip.mp4")],
    )
    def test_sidecar_tmp_pid_the_sidecar_of_a_work_file_goes_through_a_tmp_with_the_pid(
        self, project: Project, monkeypatch: pytest.MonkeyPatch, folder: str, name: str
    ) -> None:
        def run(args: list[str], **_k: object) -> None:
            Path(args[-1]).write_bytes(b"mine")

        monkeypatch.setattr(proc, "run", run)
        dst = getattr(project.layout, folder) / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        sidecar = workfiles.sidecar_path(dst)
        planted = sidecar.with_name(f"{sidecar.name}.tmp")  # the shared name of before
        planted.write_bytes(b"PLANTED-BY-ANOTHER-RENDER")
        moves: list[tuple[str, str]] = []
        real = os.replace

        def spy(src: Any, to: Any) -> None:
            moves.append((Path(src).name, Path(to).name))
            real(src, to)

        monkeypatch.setattr(os, "replace", spy)
        workfiles._build(project, lambda out: ["ffmpeg", str(out)], dst, (QHASH, PARAMS, 1.0), None)
        assert (f"{sidecar.name}.{os.getpid()}.tmp", sidecar.name) in moves
        assert (planted.name, sidecar.name) not in moves
        assert planted.read_bytes() == b"PLANTED-BY-ANOTHER-RENDER"
        assert workfiles.is_fresh(dst, QHASH, PARAMS)


class TestHardlinkStale:
    """Row 19: kcut reads only the files that are its own, a regular file with a single link."""

    @staticmethod
    def _fresh_work_file(path: Path) -> None:
        path.write_bytes(b"audio")
        workfiles.sidecar_path(path).write_text(
            '{"qhash": "sha256:abc", "params": {"sr": 48000}}', encoding="utf-8"
        )

    def test_hardlink_stale_a_regular_file_with_a_fresh_sidecar_is_fresh(
        self, project: Project
    ) -> None:
        wav = project.layout.wav16 / "a1_x.wav"
        self._fresh_work_file(wav)
        assert is_lone_file(wav)
        assert workfiles.sidecar_state(wav, QHASH, PARAMS) == "fresh"

    def test_hardlink_stale_a_work_file_that_is_a_hard_link_is_stale_with_a_fresh_sidecar(
        self, project: Project, tmp_path: Path
    ) -> None:
        outside = tmp_path / "ajeno.wav"
        outside.write_bytes(b"audio")
        wav = project.layout.wav16 / "a1_x.wav"
        make_hard_link(wav, outside)
        workfiles.sidecar_path(wav).write_text(
            '{"qhash": "sha256:abc", "params": {"sr": 48000}}', encoding="utf-8"
        )
        assert not is_lone_file(wav)
        assert workfiles.sidecar_state(wav, QHASH, PARAMS) == "stale"
        assert not workfiles.is_fresh(wav, QHASH, PARAMS)
        assert outside.read_bytes() == b"audio"  # nothing was written through it

    def test_hardlink_stale_a_work_file_that_is_a_symlink_is_stale_too(
        self, project: Project, tmp_path: Path
    ) -> None:
        outside = tmp_path / "ajeno.wav"
        outside.write_bytes(b"audio")
        wav = project.layout.wav16 / "a1_x.wav"
        try:
            os.symlink(outside, wav)
        except OSError as exc:
            pytest.skip(f"no se pudo crear un symlink: {exc}")
        workfiles.sidecar_path(wav).write_text(
            '{"qhash": "sha256:abc", "params": {"sr": 48000}}', encoding="utf-8"
        )
        assert workfiles.sidecar_state(wav, QHASH, PARAMS) == "stale"

    def test_hardlink_stale_what_is_not_there_is_not_a_lone_file(self, project: Project) -> None:
        assert not is_lone_file(project.layout.wav16 / "nope.wav")
        assert not is_lone_file(project.layout.wav16)  # a folder

    def test_hardlink_stale_a_mezzanine_that_is_a_hard_link_is_stale_with_a_fresh_sidecar(
        self, mezz_project: Project, tmp_path: Path
    ) -> None:
        job = _job()
        mezz = _plant(mezz_project, job, size=10)
        params = params_of(job, 45, 135, FPS)
        assert mezz_files._state(mezz, _a1().qhash, params, 90) == ("fresh", 90)
        outside = tmp_path / "ajeno.mp4"
        outside.write_bytes(mezz.read_bytes())  # same bytes, so the size in the sidecar matches
        mezz.unlink()
        make_hard_link(mezz, outside)
        assert mezz_files._state(mezz, _a1().qhash, params, 90) == ("stale", 0)
        assert outside.read_bytes() == b"x" * 10
