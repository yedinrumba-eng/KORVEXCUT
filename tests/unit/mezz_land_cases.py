"""A mezzanine whose video ends before its range, the one that another process made first, and the
temporary file of the sidecar (spec S1.5b rows 48, 50 and 55; 001.26 points 1, 2 and 7). No
ffmpeg: `proc.run` is replaced by a function that writes the file it was asked for (`_Fake`).

Collected from `test_mezz_plan.py`; the helpers are those of `mezz_files_cases.py` and
`mezz_build_cases.py`.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from kcut.errors import CheckFailed, ProjectError
from kcut.ingest import sidecar as sidecar_module
from kcut.jsonio import write_json_exclusive
from kcut.project import Project
from kcut.render import mezz_files
from kcut.render.mezz_files import MezzEntry, build_mezz, find_fresh, list_mezz, params_of
from tests.unit.mezz_build_cases import _Fake
from tests.unit.mezz_files_cases import FPS, _a1, _job, _plant

__all__ = ["TestFirstOneWins", "TestShortTail", "TestSidecarTmp"]


def _files(project: Project) -> list[str]:
    return sorted(p.name for p in (project.root / ".kcut" / "mezz").iterdir())


class TestShortTail:
    """Row 48: the check is against what the EDL reads, not against the range with its margin."""

    def test_mezz_short_tail_a_file_shorter_than_its_range_that_reaches_the_need_is_kept(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Fake(monkeypatch, made=80)  # the range has 90 frames; the video of the clip has 80
        job = _job(need=120)
        entry = build_mezz(mezz_project, job, _a1(), FPS, None)
        assert entry == MezzEntry(entry.path, 45, 125, 1440, 2560)  # [45, 45 + 80)
        sidecar = json.loads(Path(f"{entry.path}.json").read_text(encoding="utf-8"))
        assert sidecar["frames"] == 80 and sidecar["size_bytes"] == 15
        assert sidecar["params"] == params_of(job, 45, 135, FPS)  # the name keeps the plan's range
        assert _files(mezz_project) == [entry.path.name, f"{entry.path.name}.json"]

    def test_mezz_short_tail_the_same_job_finds_that_file_again_with_its_real_range(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Fake(monkeypatch, made=80)
        job = _job(need=120)
        built = build_mezz(mezz_project, job, _a1(), FPS, None)
        folder = (mezz_project.root / ".kcut" / "mezz").resolve()
        listed = list_mezz(folder)["a1"]
        found, corrupt = find_fresh(folder, job, _a1(), FPS, listed)
        assert found == built and found.end_f == 125 and not corrupt
        # a job of the same name that reads more than the file has is not served by it
        assert find_fresh(folder, _job(need=126), _a1(), FPS, listed)[0] is None

    def test_mezz_short_tail_one_frame_before_the_need_is_a_check_failed_with_nothing_left(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Fake(monkeypatch, made=74)  # 45 + 74 = 119; the EDL reads up to the frame 119 (need 120)
        with pytest.raises(CheckFailed) as info:
            build_mezz(mezz_project, _job(need=120), _a1(), FPS, None)
        assert info.value.exit_code == 1
        message = "el video de a1 termina en el frame 119; el EDL pide hasta 120"
        assert info.value.message_es == message
        assert _files(mezz_project) == []

    def test_mezz_short_tail_the_exact_need_is_enough(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Fake(monkeypatch, made=75)
        assert build_mezz(mezz_project, _job(need=120), _a1(), FPS, None).end_f == 120


class TestFirstOneWins:
    """Row 50: another process has the file of the job when ours is done."""

    def _replaces(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Every `os.replace` of a mezzanine, by the name of what was moved."""
        moved: list[str] = []
        real = os.replace

        def spy(src: Any, dst: Any) -> None:
            moved.append(Path(src).name)
            real(src, dst)

        monkeypatch.setattr(mezz_files.os, "replace", spy)
        return moved

    def test_mezz_concurrent_reader_a_file_that_is_fresh_already_is_used_and_the_partial_goes(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        theirs = _plant(mezz_project, job, size=15, frames=90)  # as the fake writes: 15 bytes
        moved = self._replaces(monkeypatch)
        _Fake(monkeypatch, made=90)
        entry = build_mezz(mezz_project, job, _a1(), FPS, None)
        assert entry == MezzEntry(theirs.resolve(), 45, 135, 1440, 2560)
        assert theirs.read_bytes() == b"x" * 15  # not replaced by the partial (b"mp4" * 5)
        assert moved == []  # not even tried
        assert _files(mezz_project) == [theirs.name, f"{theirs.name}.json"]

    def test_mezz_concurrent_reader_a_refused_replace_over_a_file_that_is_fresh_then_uses_it(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other process has not written its sidecar at the first look, and has at the
        second: the replace was refused because it is reading the file."""
        job = _job()
        theirs = _plant(mezz_project, job, size=15, frames=90)
        sidecar = Path(f"{theirs}.json")
        saved = sidecar.read_text(encoding="utf-8")
        sidecar.unlink()

        def refused(src: Any, dst: Any) -> None:
            sidecar.write_text(saved, encoding="utf-8")
            raise PermissionError(13, "Access is denied", str(dst))

        monkeypatch.setattr(mezz_files.os, "replace", refused)
        _Fake(monkeypatch, made=90)
        entry = build_mezz(mezz_project, job, _a1(), FPS, None)
        assert entry.path == theirs.resolve() and entry.end_f == 135
        assert _files(mezz_project) == [theirs.name, sidecar.name]  # no partial

    def test_mezz_concurrent_reader_a_refused_replace_over_a_file_that_is_not_fresh_is_exit_3(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        (mezz_project.root / job.path).write_bytes(b"not a mezzanine")  # no sidecar

        def refused(src: Any, dst: Any) -> None:
            raise PermissionError(13, "Access is denied", str(dst))

        monkeypatch.setattr(mezz_files.os, "replace", refused)
        monkeypatch.setattr(sidecar_module, "LAND_WAIT_S", 0.0)  # 001.29: no real wait
        _Fake(monkeypatch, made=90)
        with pytest.raises(ProjectError) as info:
            build_mezz(mezz_project, job, _a1(), FPS, None)
        message = info.value.message_es
        assert info.value.exit_code == 3 and "otro proceso tiene abierto" in message
        assert message.endswith("espera a que termine y repite") and "reproductor" not in message
        assert _files(mezz_project) == [Path(job.path).name]  # the partial is gone

    def test_mezz_concurrent_reader_a_fresh_file_that_is_too_short_for_the_job_is_replaced(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Fresh for a job that read less is not fresh for this one: the partial goes over it."""
        job = _job(need=135)
        _plant(mezz_project, job, size=15, frames=60)  # its video ends at 105
        _Fake(monkeypatch, made=90)
        entry = build_mezz(mezz_project, job, _a1(), FPS, None)
        assert entry.end_f == 135
        assert (mezz_project.root / job.path).read_bytes() == b"mp4" * 5

    @pytest.mark.skipif(sys.platform != "win32", reason="only Windows keeps a read file in place")
    def test_mezz_concurrent_reader_a_python_open_keeps_the_real_replace_from_working(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """As ffmpeg, a Python `open()` does not share the delete on Windows: the real `os.replace`
        over a file that is being read raises PermissionError. A fresh one is used; one that is
        not fresh is exit 3."""
        job = _job()
        path = _plant(mezz_project, job, size=15, frames=90)
        _Fake(monkeypatch, made=90)
        monkeypatch.setattr(sidecar_module, "LAND_WAIT_S", 0.0)  # 001.29: no real wait
        with path.open("rb"):
            assert build_mezz(mezz_project, job, _a1(), FPS, None).path == path.resolve()
            Path(f"{path}.json").unlink()  # now it is not fresh
            with pytest.raises(ProjectError, match="otro proceso tiene abierto"):
                build_mezz(mezz_project, job, _a1(), FPS, None)
        assert _files(mezz_project) == [path.name]


class TestSidecarTmp:
    """Row 55: the temporary file of the sidecar is created new."""

    def _race(self, tmp: Path, victim: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Plant a hard link to `victim` at `tmp` right after the first `unlink` of it."""
        real = Path.unlink
        planted: list[bool] = []

        def racing(self: Path, *args: Any, **kwargs: Any) -> None:
            real(self, *args, **kwargs)
            if self == tmp and not planted:
                planted.append(True)
                os.link(victim, tmp)

        monkeypatch.setattr(Path, "unlink", racing)

    def test_sidecar_tmp_exclusive_a_link_planted_after_the_unlink_is_exit_3(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        victim = tmp_path / "victim.bin"
        victim.write_bytes(b"PRECIOUS-FOOTAGE" * 4)
        sidecar = tmp_path / "x.mp4.json"
        tmp = sidecar.with_name(f"{sidecar.name}.{os.getpid()}.tmp")
        self._race(tmp, victim, monkeypatch)
        with pytest.raises(ProjectError) as info:
            write_json_exclusive(sidecar, {"a": 1})  # 001.27: it was `mezz_files._write_sidecar`
        assert info.value.exit_code == 3 and "no pude escribir" in info.value.message_es
        assert victim.read_bytes() == b"PRECIOUS-FOOTAGE" * 4
        assert not sidecar.exists()

    def test_sidecar_tmp_exclusive_a_link_that_was_there_before_is_removed_and_not_followed(
        self, tmp_path: Path
    ) -> None:
        victim = tmp_path / "victim.bin"
        victim.write_bytes(b"PRECIOUS-FOOTAGE" * 4)
        sidecar = tmp_path / "x.mp4.json"
        os.link(victim, sidecar.with_name(f"{sidecar.name}.{os.getpid()}.tmp"))
        write_json_exclusive(sidecar, {"a": 1})  # 001.27: it was `mezz_files._write_sidecar`
        assert victim.read_bytes() == b"PRECIOUS-FOOTAGE" * 4
        assert json.loads(sidecar.read_text(encoding="utf-8")) == {"a": 1}
        assert sorted(p.name for p in tmp_path.iterdir()) == ["victim.bin", "x.mp4.json"]

    def test_sidecar_tmp_exclusive_the_text_is_utf8_with_unix_newlines(
        self, tmp_path: Path
    ) -> None:
        sidecar = tmp_path / "x.mp4.json"
        write_json_exclusive(sidecar, {"ñ": "ú"})  # 001.27: it was `mezz_files._write_sidecar`
        raw = sidecar.read_bytes()
        assert b"\r" not in raw and raw.endswith(b"\n") and "ñ".encode() in raw

    def test_sidecar_tmp_pid_the_sidecar_of_a_mezzanine_goes_through_a_tmp_with_the_pid(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Row 16 (001.27 point 5): the temporary of the sidecar has the pid, and a
        `<sidecar>.tmp` planted by anyone (the shared name of before) is not touched."""
        _Fake(monkeypatch, made=90)
        sidecar = _job().path.rsplit("/", 1)[1] + ".json"
        planted = mezz_project.root / ".kcut" / "mezz" / f"{sidecar}.tmp"
        planted.write_bytes(b"PLANTED-BY-ANOTHER-RENDER")
        moves: list[tuple[str, str]] = []
        real = os.replace

        def spy(src: Any, dst: Any) -> None:
            moves.append((Path(src).name, Path(dst).name))
            real(src, dst)

        monkeypatch.setattr(os, "replace", spy)
        build_mezz(mezz_project, _job(), _a1(), FPS, None)
        assert (f"{sidecar}.{os.getpid()}.tmp", sidecar) in moves
        assert (f"{sidecar}.tmp", sidecar) not in moves
        assert planted.read_bytes() == b"PLANTED-BY-ANOTHER-RENDER"
