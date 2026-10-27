"""The wait of a refused move (spec 001.29, point 1; row 29): `workfiles._land` and, in
`mezz_land_wait_cases.py`, `mezz_files._land`.

When `os.replace(partial, dst)` is refused with a `PermissionError`, the landing does not give up
at the first one: for `LAND_WAIT_S` = 10 s, every `LAND_POLL_S` = 0.1 s, it looks at `dst` (fresh:
it is used) and, if it is not, moves again (it worked: it is moved). If the time runs out, the
`ProjectError` of always. Here the clock is a fake: `time.monotonic` and `time.sleep` of
`kcut.ingest.sidecar` count turns and no real second goes by.

Collected from `test_workfiles.py`, whose `project` fixture (a project with `.kcut/wav16/` and
`crudo/`) these use.
"""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.errors import ProjectError
from kcut.ingest import sidecar as sidecar_module
from kcut.ingest import workfiles
from kcut.project import Project

__all__ = ["TestLandWaitShared", "TestLandWaitWork"]
JOB = ("sha256:abc", {"sr": 48000}, 1.0)
SIDECAR = {"qhash": "sha256:abc", "params": {"sr": 48000}}
CLOSE = "cierra el wav48 de a1 en el reproductor y repite"


class FakeClock:
    """A `time` for `kcut.ingest.sidecar`: `sleep` moves `monotonic` by what it is told, and
    `on_sleep(n)` runs after the n-th sleep (the moment something happens in another process)."""

    def __init__(self, on_sleep: Callable[[int], None] | None = None) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []
        self._on_sleep = on_sleep

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        if self._on_sleep is not None:
            self._on_sleep(len(self.sleeps))


class Moves:
    """`os.replace` as the tests need it: the moves onto `dst` (not the ones of the sidecar's
    temporary) raise `PermissionError` for the first `refuse` calls (all of them if `None`) and
    then go through. `calls` counts the moves onto `dst`."""

    def __init__(self, dst: Path, refuse: int | None) -> None:
        self.dst, self.refuse, self.calls = dst, refuse, 0
        self._real = os.replace

    def __call__(self, src: Any, to: Any) -> None:
        if Path(to).name != self.dst.name:  # the sidecar and its temporary go through
            self._real(src, to)
            return
        self.calls += 1
        if self.refuse is None or self.calls <= self.refuse:
            raise PermissionError(13, "Access is denied", str(to))
        self._real(src, to)


def fake_clock(monkeypatch: pytest.MonkeyPatch, clock: FakeClock) -> FakeClock:
    monkeypatch.setattr(sidecar_module, "time", clock)
    return clock


class TestLandWaitWork:
    @staticmethod
    def _dst(project: Project) -> Path:
        dst = project.layout.wav48 / "a1_ana-perez-809-555-1234.wav"
        dst.parent.mkdir(parents=True, exist_ok=True)
        return dst

    @staticmethod
    def _ffmpeg(monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(proc, "run", lambda args, **_k: Path(args[-1]).write_bytes(b"mine"))

    @staticmethod
    def _build(project: Project, dst: Path) -> None:
        workfiles._build(project, lambda out: ["ffmpeg", str(out)], dst, JOB, None)

    def test_land_wait_the_other_ones_sidecar_in_the_third_turn_makes_its_file_the_one_used(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        dst.write_bytes(b"theirs")  # the other process moved it; its sidecar is not there yet

        def appears(n: int) -> None:
            if n == 2:  # it is there when the third turn looks
                workfiles.sidecar_path(dst).write_text(json.dumps(SIDECAR), encoding="utf-8")

        clock = fake_clock(monkeypatch, FakeClock(appears))
        moves = Moves(dst, refuse=None)
        monkeypatch.setattr(os, "replace", moves)
        self._ffmpeg(monkeypatch)
        self._build(project, dst)
        assert dst.read_bytes() == b"theirs"
        assert moves.calls == 3 and clock.sleeps == [0.1, 0.1]  # the first try and two turns
        names = sorted(p.name for p in dst.parent.iterdir())
        assert names == [dst.name, f"{dst.name}.json"]  # no partial, and their sidecar is kept
        assert json.loads(workfiles.sidecar_path(dst).read_text(encoding="utf-8")) == SIDECAR

    def test_land_wait_a_move_refused_twice_and_then_let_through_is_moved_with_its_own_sidecar(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        dst.write_bytes(b"old, nobody vouches for it")
        clock = fake_clock(monkeypatch, FakeClock())
        moves = Moves(dst, refuse=2)
        monkeypatch.setattr(os, "replace", moves)
        self._ffmpeg(monkeypatch)
        self._build(project, dst)
        assert dst.read_bytes() == b"mine"
        assert moves.calls == 3 and clock.sleeps == [0.1]
        assert json.loads(workfiles.sidecar_path(dst).read_text(encoding="utf-8")) == SIDECAR
        assert sorted(p.name for p in dst.parent.iterdir()) == [dst.name, f"{dst.name}.json"]

    def test_land_wait_a_move_that_is_always_refused_is_the_old_error_after_10_seconds(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        dst.write_bytes(b"not a work file, no sidecar")
        clock = fake_clock(monkeypatch, FakeClock())
        moves = Moves(dst, refuse=None)
        monkeypatch.setattr(os, "replace", moves)
        self._ffmpeg(monkeypatch)
        with pytest.raises(ProjectError) as info:
            self._build(project, dst)
        assert info.value.exit_code == 3 and info.value.message_es == CLOSE
        assert 99 <= len(clock.sleeps) <= 101  # about 100 turns of 0.1 s
        assert 10.0 - 1e-6 <= clock.now - 1000.0 < 10.2  # and it did not wait past the 10 s
        assert dst.read_bytes() == b"not a work file, no sidecar"
        assert [p.name for p in dst.parent.iterdir()] == [dst.name]  # its partial is gone


class TestLandWaitShared:
    """`wait_to_land` itself: the numbers of the spec and the order of what it does."""

    def test_land_wait_the_numbers_are_the_ones_of_the_spec(self) -> None:
        assert sidecar_module.LAND_WAIT_S == 10.0 and sidecar_module.LAND_POLL_S == 0.1

    def test_land_wait_it_looks_before_it_moves_in_each_turn_and_stops_at_what_it_finds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []
        found = iter([None, None, "theirs"])

        def look() -> str | None:
            events.append("look")
            return next(found)

        def refused(*_a: object) -> None:
            events.append("move")
            raise PermissionError(13, "Access is denied")

        clock = fake_clock(monkeypatch, FakeClock(lambda _n: events.append("sleep")))
        monkeypatch.setattr(os, "replace", refused)
        got = sidecar_module.wait_to_land(tmp_path / "a", tmp_path / "b", look)
        assert got == "theirs" and clock.sleeps == [0.1, 0.1]
        assert events == ["look", "move", "sleep", "look", "move", "sleep", "look"]

    def test_land_wait_a_move_that_works_returns_none_and_does_not_look_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "a").write_bytes(b"x")
        looks: list[int] = []
        clock = fake_clock(monkeypatch, FakeClock())
        got = sidecar_module.wait_to_land(
            tmp_path / "a", tmp_path / "b", lambda: looks.append(1) or None
        )
        assert got is None and looks == [1] and clock.sleeps == []
        assert (tmp_path / "b").read_bytes() == b"x"

    def test_land_wait_an_error_that_is_not_a_permission_error_goes_up_at_once(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(*_a: object) -> None:
            raise OSError(5, "Input/output error")

        clock = fake_clock(monkeypatch, FakeClock())
        monkeypatch.setattr(os, "replace", broken)
        with pytest.raises(OSError, match="Input/output error") as info:
            sidecar_module.wait_to_land(tmp_path / "a", tmp_path / "b", lambda: None)
        assert not isinstance(info.value, PermissionError) and clock.sleeps == []
