"""The wait of a refused move, for a mezzanine (spec 001.29, point 1; row 29): the same three
cases as `workfiles_land_wait_cases.py`, on `mezz_files._land` through `build_mezz`. The clock is a
fake (`FakeClock` of that module): no real second goes by. No ffmpeg: `proc.run` is replaced by
the function that writes the file it was asked for (`_Fake`).

Collected from `test_mezz_plan.py`; the helpers are those of `mezz_files_cases.py`,
`mezz_build_cases.py` and `mezz_land_cases.py`.
"""

import json
import os
from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.project import Project
from kcut.render.mezz_files import MezzEntry, build_mezz
from tests.unit.mezz_build_cases import _Fake
from tests.unit.mezz_files_cases import FPS, _a1, _job, _plant
from tests.unit.mezz_land_cases import _files
from tests.unit.workfiles_land_wait_cases import FakeClock, Moves, fake_clock

__all__ = ["TestLandWaitMezz"]


class TestLandWaitMezz:
    def test_land_wait_the_other_ones_sidecar_in_the_third_turn_makes_its_file_the_one_used(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        theirs = _plant(mezz_project, job, size=15, frames=90)
        sidecar = Path(f"{theirs}.json")
        saved = sidecar.read_text(encoding="utf-8")
        sidecar.unlink()  # the other process moved the file; its sidecar is not there yet

        def appears(n: int) -> None:
            if n == 2:  # it is there when the third turn looks
                sidecar.write_text(saved, encoding="utf-8")

        clock = fake_clock(monkeypatch, FakeClock(appears))
        moves = Moves(theirs, refuse=None)
        monkeypatch.setattr(os, "replace", moves)
        _Fake(monkeypatch, made=90)
        entry = build_mezz(mezz_project, job, _a1(), FPS, None)
        assert entry == MezzEntry(theirs.resolve(), 45, 135, 1440, 2560)
        assert theirs.read_bytes() == b"x" * 15  # theirs, not the partial (b"mp4" * 5)
        assert moves.calls == 3 and clock.sleeps == [0.1, 0.1]  # the first try and two turns
        assert _files(mezz_project) == [theirs.name, sidecar.name]  # no partial

    def test_land_wait_a_move_refused_twice_and_then_let_through_is_moved_with_its_own_sidecar(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        dst = mezz_project.root / job.path
        dst.write_bytes(b"old, nobody vouches for it")
        clock = fake_clock(monkeypatch, FakeClock())
        moves = Moves(dst, refuse=2)
        monkeypatch.setattr(os, "replace", moves)
        _Fake(monkeypatch, made=90)
        entry = build_mezz(mezz_project, job, _a1(), FPS, None)
        assert entry.path == dst.resolve() and entry.end_f == 135
        assert dst.read_bytes() == b"mp4" * 5  # the partial is what is there now
        assert moves.calls == 3 and clock.sleeps == [0.1]
        own = json.loads(Path(f"{dst}.json").read_text(encoding="utf-8"))
        assert own["size_bytes"] == 15 and own["frames"] == 90  # the sidecar of this process
        assert _files(mezz_project) == [dst.name, f"{dst.name}.json"]

    def test_land_wait_a_move_that_is_always_refused_is_the_old_error_after_10_seconds(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        dst = mezz_project.root / job.path
        dst.write_bytes(b"not a mezzanine")  # no sidecar
        clock = fake_clock(monkeypatch, FakeClock())
        moves = Moves(dst, refuse=None)
        monkeypatch.setattr(os, "replace", moves)
        _Fake(monkeypatch, made=90)
        with pytest.raises(ProjectError) as info:
            build_mezz(mezz_project, job, _a1(), FPS, None)
        message = info.value.message_es
        assert info.value.exit_code == 3 and "otro proceso tiene abierto" in message
        assert message.endswith("espera a que termine y repite")
        assert 99 <= len(clock.sleeps) <= 101  # about 100 turns of 0.1 s
        assert 10.0 - 1e-6 <= clock.now - 1000.0 < 10.2  # and it did not wait past the 10 s
        assert dst.read_bytes() == b"not a mezzanine"
        assert _files(mezz_project) == [dst.name]  # its partial is gone
