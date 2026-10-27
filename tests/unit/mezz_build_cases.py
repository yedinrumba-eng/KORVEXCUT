"""How a mezzanine is made and how fast they are looked for (spec S1.5b rows 38, 39 and 41; 001.25
points 7, 8 and 10). No ffmpeg: `proc.run` is replaced by a function that writes the file it was
asked for.

Collected from `test_mezz_plan.py`; the helpers are those of `mezz_files_cases.py`.
"""

import json
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.errors import CheckFailed
from kcut.ff.color import CHAIN_VERSION
from kcut.ingest.inventory import Inventory
from kcut.project import Project
from kcut.render import mezz, mezz_files
from kcut.render.mezz import MezzJob, ensure_mezz
from kcut.render.mezz_files import MezzEntry, build_mezz, params_of
from tests.unit.edl_fakes import inventory
from tests.unit.mezz_files_cases import FPS, _a1, _job, mezz_project

__all__ = ["TestBuild", "TestManyFiles", "mezz_project"]


class _Fake:
    """`proc.run` and `frame_count` in place of ffmpeg and ffprobe."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, made: int | None = None) -> None:
        self.runs: list[list[str]] = []
        self.made = made
        monkeypatch.setattr(proc, "tool_path", lambda name: Path(name))
        monkeypatch.setattr(mezz_files.proc, "run", self._run)
        monkeypatch.setattr(mezz_files, "frame_count", self._count)

    def _run(self, args: list[str], **_k: Any) -> None:
        self.runs.append(args)
        Path(args[-1]).write_bytes(b"mp4" * 5)

    def _count(self, _path: Path, _log: Path | None) -> int:
        assert self.made is not None
        return self.made


class TestBuild:
    """Rows 38 and 39 (001.25 points 7 and 8)."""

    def test_mezz_concurrent_the_partial_has_the_pid_and_the_sidecar_says_bytes_and_frames(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _Fake(monkeypatch, made=90)
        entry = build_mezz(mezz_project, _job(), _a1(), FPS, None)
        assert Path(fake.runs[0][-1]).name == (
            f"a1_45-135_1440x2560_{CHAIN_VERSION}.{os.getpid()}.partial.mp4"
        )
        assert "-y" in fake.runs[0]  # `.partial.` in the name, as the spec 0.8 wants
        sidecar = json.loads(Path(f"{entry.path}.json").read_text(encoding="utf-8"))
        assert sidecar == {
            "qhash": _a1().qhash,
            "params": params_of(_job(), 45, 135, FPS),
            "size_bytes": 15,
            "frames": 90,
        }
        assert sorted(p.name for p in entry.path.parent.iterdir()) == [
            entry.path.name,
            f"{entry.path.name}.json",
        ]

    def test_mezz_concurrent_the_finally_deletes_only_its_own_partial(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Fake(monkeypatch, made=90)
        other = mezz_project.root / ".kcut" / "mezz"
        theirs = other / f"a1_45-135_1440x2560_{CHAIN_VERSION}.99999.partial.mp4"
        theirs.write_bytes(b"another process is writing this")
        build_mezz(mezz_project, _job(), _a1(), FPS, None)
        assert theirs.read_bytes() == b"another process is writing this"

    def test_mezz_concurrent_a_failed_build_leaves_no_partial_and_keeps_the_other_ones(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = _Fake(monkeypatch, made=90)

        def broken(args: list[str], **_k: Any) -> None:
            Path(args[-1]).write_bytes(b"half")
            raise RuntimeError("ffmpeg died")

        monkeypatch.setattr(mezz_files.proc, "run", broken)
        theirs = mezz_project.root / ".kcut" / "mezz" / "x.99999.partial.mp4"
        theirs.write_bytes(b"theirs")
        with pytest.raises(RuntimeError):
            build_mezz(mezz_project, _job(), _a1(), FPS, None)
        assert [p.name for p in theirs.parent.iterdir()] == ["x.99999.partial.mp4"]
        assert fake.runs == []

    def test_mezz_short_a_file_with_fewer_frames_is_a_check_failed_with_no_sidecar(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Fake(monkeypatch, made=60)  # the video ends 30 frames before the range does
        with pytest.raises(CheckFailed) as info:
            build_mezz(mezz_project, _job(), _a1(), FPS, None)
        assert info.value.exit_code == 1
        assert (
            info.value.message_es == "el video de a1 termina en el frame 105; el EDL pide hasta 135"
        )
        assert list((mezz_project.root / ".kcut" / "mezz").iterdir()) == []

    def test_mezz_short_one_frame_short_is_enough_and_the_exact_count_is_not(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Fake(monkeypatch, made=89)
        with pytest.raises(CheckFailed, match="termina en el frame 134"):
            build_mezz(mezz_project, _job(), _a1(), FPS, None)
        _Fake(monkeypatch, made=90)
        assert build_mezz(mezz_project, _job(), _a1(), FPS, None).end_f == 135


def _many(count_clips: int, per_clip: int) -> tuple[Inventory, list[MezzJob]]:
    base = _a1()
    clips = tuple(replace(base, id=f"a{n}", slug=f"a{n}") for n in range(1, count_clips + 1))
    inv = replace(inventory(), clips=clips)
    jobs = [
        _job(100 * k, 100 * k + 60, f"a{n}")
        for n in range(1, count_clips + 1)
        for k in range(per_clip)
    ]
    return inv, jobs


def _plant_any(project: Project, job: MezzJob, *, sidecar: bool = False) -> None:
    path = project.root / job.path
    path.write_bytes(b"x" * 10)
    if sidecar:
        data = {
            "qhash": _a1().qhash,
            "params": params_of(job, job.start_f, job.end_f, FPS),
            "size_bytes": 10,
            "frames": 60,
        }
        Path(f"{path}.json").write_text(json.dumps(data), encoding="utf-8")


def _count_listings(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every `os.listdir` of the test, as the path it was asked about."""
    listed: list[str] = []
    real = os.listdir

    def spy(path: Any = ".") -> list[str]:
        listed.append(str(path))
        return real(path)

    monkeypatch.setattr(mezz_files.os, "listdir", spy)
    return listed


class TestManyFiles:
    """Row 41 (001.25 point 10): `.kcut/mezz/` is listed once; files are looked at by clip."""

    def test_mezz_candidates_once_3000_jobs_against_3000_files_plan_in_under_3_seconds(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """300 clips with 10 ranges each. No sidecars: what is measured is the search for a file
        that holds each range, which used to be a `glob` of the whole folder for every job."""
        inv, jobs = _many(300, 10)
        for job in jobs:
            _plant_any(mezz_project, job)
        listed = _count_listings(monkeypatch)
        monkeypatch.setattr(
            mezz, "build_mezz", lambda p, j, c, f, log: MezzEntry(Path("x"), 0, 1, 1, 1)
        )
        started = time.monotonic()
        index = ensure_mezz(mezz_project, jobs, inv=inv)
        elapsed = time.monotonic() - started
        assert (index.built, index.reused) == (3000, 0)
        assert len(listed) == 1 and Path(listed[0]).name == "mezz"
        assert elapsed < 3.0, f"{elapsed:.1f} s"

    def test_mezz_candidates_once_with_every_file_fresh_the_folder_is_still_listed_once(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inv, jobs = _many(30, 10)
        for job in jobs:
            _plant_any(mezz_project, job, sidecar=True)
        listed = _count_listings(monkeypatch)
        monkeypatch.setattr(mezz, "build_mezz", lambda *a, **k: pytest.fail("a fresh file is made"))
        index = ensure_mezz(mezz_project, jobs, inv=inv)
        assert (index.built, index.reused) == (0, 300) and len(listed) == 1

    def test_mezz_candidates_once_the_files_of_the_other_clips_are_not_looked_at(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        inv, jobs = _many(3, 1)
        for job in jobs[1:]:  # a2 and a3 have a file, a1 does not
            _plant_any(mezz_project, job)
        seen: list[str] = []
        real = mezz_files.workfiles.sidecar_path
        monkeypatch.setattr(
            mezz_files.workfiles, "sidecar_path", lambda p: (seen.append(p.name), real(p))[1]
        )
        monkeypatch.setattr(
            mezz, "build_mezz", lambda p, j, c, f, log: MezzEntry(Path("x"), 0, 1, 1, 1)
        )
        ensure_mezz(mezz_project, jobs[:1], inv=inv)
        assert seen and all(name.startswith("a1_") for name in seen)
