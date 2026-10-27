"""The sidecar of a work file is put in its place like the file itself (spec S1.6b round 1, 001.31
point 1; row 19): `sidecar.land_sidecar` writes `<sidecar>.<pid>.tmp` new and moves it with
`wait_to_land`. If the move is refused (the other render has the sidecar open, because it is
reading it to see if the file is fresh) it waits for the reader to let go, and if the sidecar that
is there is already the good one (the other render put it) that one is used and the temporary
goes.

Collected from `test_workfiles.py`, whose `project` fixture (a project with `.kcut/wav16/` and
`crudo/`) these use. `mezz_sidecar_land_cases.py` has the same cases for a mezzanine; the helpers
`SidecarMoves` and `open_reader` are shared with it.
"""

import json
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.errors import ProjectError
from kcut.ingest import sidecar as sidecar_module
from kcut.ingest import workfiles
from kcut.project import Project
from tests.unit.workfiles_land_wait_cases import FakeClock, fake_clock

__all__ = ["SidecarMoves", "TestSidecarLandShared", "TestSidecarLandWork", "open_reader"]
JOB = ("sha256:abc", {"sr": 48000}, 1.0)
SIDECAR = {"qhash": "sha256:abc", "params": {"sr": 48000}}
OTHER = {"qhash": "sha256:other", "params": {"sr": 16000}}
CLOSE = "cierra el sidecar del wav48 de a1 en el reproductor y repite"


class SidecarMoves:
    """`os.replace` where every move onto a `.json` is refused with a `PermissionError`, and the
    ones onto anything else go through. `planted` is what is written at the sidecar the first time
    it is refused (what the other render did while this one was moving), `None` for nothing."""

    def __init__(self, planted: str | None = None) -> None:
        self.planted, self.refused = planted, 0
        self._real = os.replace

    def __call__(self, src: Any, to: Any) -> None:
        if not str(to).endswith(".json"):
            self._real(src, to)
            return
        self.refused += 1
        if self.refused == 1 and self.planted is not None:
            Path(to).write_text(self.planted, encoding="utf-8")
        raise PermissionError(13, "Access is denied", str(to))


@contextmanager
def open_reader(path: Path, seconds: float) -> Iterator[None]:
    """`path` open for reading by a real `open`, let go after `seconds`. On Windows that is what
    makes `os.replace` onto it fail: the handle does not share the delete."""
    handle = path.open("rb")
    timer = threading.Timer(seconds, handle.close)
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        timer.join()
        handle.close()


class TestSidecarLandWork:
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

    @staticmethod
    def _names(dst: Path) -> list[str]:
        return sorted(p.name for p in dst.parent.iterdir())

    @pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses a file that is open")
    def test_sidecar_land_a_reader_with_the_sidecar_open_for_half_a_second_is_waited_for(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The ALTO of the verifier: the other render reads the sidecar to see if the file is
        fresh, the replace of this one is refused, and it used to give up at once."""
        dst = self._dst(project)
        dst.write_bytes(b"old, from before")
        sidecar = workfiles.sidecar_path(dst)
        sidecar.write_text(json.dumps(OTHER), encoding="utf-8")  # not fresh: it is ours to write
        self._ffmpeg(monkeypatch)
        started = time.monotonic()
        with open_reader(sidecar, 0.5):
            self._build(project, dst)
        assert time.monotonic() - started >= 0.4  # the reader was really in the way
        assert dst.read_bytes() == b"mine"
        assert json.loads(sidecar.read_text(encoding="utf-8")) == SIDECAR
        assert self._names(dst) == [dst.name, sidecar.name]  # no temporary, no partial

    def test_sidecar_land_the_others_sidecar_that_is_already_there_is_used_without_error(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        moves = SidecarMoves(planted=json.dumps(SIDECAR))
        monkeypatch.setattr(os, "replace", moves)
        clock = fake_clock(monkeypatch, FakeClock())
        self._ffmpeg(monkeypatch)
        self._build(project, dst)  # no ProjectError
        assert dst.read_bytes() == b"mine" and moves.refused >= 1
        assert clock.sleeps == []  # it looked first and the sidecar was good: no turn
        sidecar = workfiles.sidecar_path(dst)
        assert json.loads(sidecar.read_text(encoding="utf-8")) == SIDECAR
        assert self._names(dst) == [dst.name, sidecar.name]  # and no `.tmp`

    def test_sidecar_land_a_different_sidecar_that_is_never_let_go_is_the_error_of_today(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        sidecar = workfiles.sidecar_path(dst)
        sidecar.write_text(json.dumps(OTHER), encoding="utf-8")
        monkeypatch.setattr(os, "replace", SidecarMoves())
        clock = fake_clock(monkeypatch, FakeClock())
        self._ffmpeg(monkeypatch)
        with pytest.raises(ProjectError) as info:
            self._build(project, dst)
        assert info.value.exit_code == 3 and info.value.message_es == CLOSE
        assert 99 <= len(clock.sleeps) <= 101  # about 100 turns of 0.1 s, as for the file
        assert 10.0 - 1e-6 <= clock.now - 1000.0 < 10.2  # and not past the 10 s
        assert json.loads(sidecar.read_text(encoding="utf-8")) == OTHER  # theirs, as it was
        assert self._names(dst) == [dst.name, sidecar.name]  # the temporary is gone

    def test_sidecar_land_a_move_that_is_let_through_in_a_later_turn_leaves_the_own_sidecar(
        self, project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dst = self._dst(project)
        sidecar = workfiles.sidecar_path(dst)
        sidecar.write_text(json.dumps(OTHER), encoding="utf-8")
        real = os.replace
        monkeypatch.setattr(os, "replace", SidecarMoves())

        def let_go(n: int) -> None:
            if n == 3:  # the reader lets go: the fourth move works
                monkeypatch.setattr(os, "replace", real)

        clock = fake_clock(monkeypatch, FakeClock(let_go))
        self._ffmpeg(monkeypatch)
        self._build(project, dst)
        assert len(clock.sleeps) == 3
        assert json.loads(sidecar.read_text(encoding="utf-8")) == SIDECAR
        assert self._names(dst) == [dst.name, sidecar.name]


class TestSidecarLandShared:
    """`land_sidecar` itself, with no work file around it."""

    def test_sidecar_land_without_a_refusal_writes_the_json_and_finds_nothing(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "x.wav.json"
        looks: list[int] = []
        found = sidecar_module.land_sidecar(target, {"ñ": "ú"}, lambda: looks.append(1) or None)
        assert found is None and looks == []  # nobody looked: the move worked at once
        raw = target.read_bytes()
        assert b"\r" not in raw and raw.endswith(b"\n") and "ñ".encode() in raw
        assert json.loads(raw.decode("utf-8")) == {"ñ": "ú"}
        assert [p.name for p in tmp_path.iterdir()] == [target.name]

    def test_sidecar_land_what_look_finds_is_what_comes_back_and_the_temporary_goes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "x.wav.json"
        monkeypatch.setattr(os, "replace", SidecarMoves())
        fake_clock(monkeypatch, FakeClock())
        found = sidecar_module.land_sidecar(target, {"a": 1}, lambda: "theirs")
        assert found == "theirs"
        assert list(tmp_path.iterdir()) == []

    def test_sidecar_land_without_a_label_the_error_names_the_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "x.wav.json"
        monkeypatch.setattr(os, "replace", SidecarMoves())
        monkeypatch.setattr(sidecar_module, "LAND_WAIT_S", 0.0)  # no real wait
        with pytest.raises(ProjectError) as info:
            sidecar_module.land_sidecar(target, {"a": 1}, lambda: None)
        assert info.value.message_es == f"cierra el archivo {target} en el reproductor y repite"
        assert list(tmp_path.iterdir()) == []

    def test_sidecar_land_a_folder_at_the_sidecar_is_the_error_of_a_folder(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "x.wav.json"
        target.mkdir()
        with pytest.raises(ProjectError, match="hay una carpeta donde kcut espera un archivo"):
            sidecar_module.land_sidecar(
                target, {"a": 1}, lambda: None, label="el sidecar del wav48 de a1"
            )
        assert [p.name for p in tmp_path.iterdir()] == [target.name]
