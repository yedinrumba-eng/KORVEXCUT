"""The sidecar of a mezzanine is put in its place like the file itself (spec S1.6b round 1, 001.31
point 1; row 19): the same three cases as `workfiles_sidecar_land_cases.py`, on `build_mezz`. No
ffmpeg: `proc.run` is replaced by the function that writes the file it was asked for (`_Fake`).

Collected from `test_mezz_plan.py`; the helpers are those of `mezz_files_cases.py`,
`mezz_build_cases.py` and `workfiles_sidecar_land_cases.py`.
"""

import json
import os
import sys
import time
from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.project import Project
from kcut.render.mezz_files import MezzEntry, build_mezz, params_of
from tests.unit.mezz_build_cases import _Fake
from tests.unit.mezz_files_cases import FPS, _a1, _job, _plant
from tests.unit.mezz_land_cases import _files
from tests.unit.workfiles_land_wait_cases import FakeClock, fake_clock
from tests.unit.workfiles_sidecar_land_cases import SidecarMoves, open_reader

__all__ = ["TestSidecarLandMezz"]


def _good_sidecar() -> str:
    """The sidecar `build_mezz` writes for `_job()` when the file has 15 bytes and 90 frames."""
    document = {
        "qhash": _a1().qhash,
        "params": params_of(_job(), 45, 135, FPS),
        "size_bytes": 15,
        "frames": 90,
    }
    return json.dumps(document)


class TestSidecarLandMezz:
    @pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses a file that is open")
    def test_sidecar_land_a_reader_with_the_sidecar_open_for_half_a_second_is_waited_for(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        dst = _plant(mezz_project, job, size=7, qhash="sha256:not-this-clip")  # not fresh
        sidecar = Path(f"{dst}.json")
        _Fake(monkeypatch, made=90)
        started = time.monotonic()
        with open_reader(sidecar, 0.5):
            entry = build_mezz(mezz_project, job, _a1(), FPS, None)
        assert time.monotonic() - started >= 0.4  # the reader was really in the way
        assert entry == MezzEntry(dst.resolve(), 45, 135, 1440, 2560)
        assert json.loads(sidecar.read_text(encoding="utf-8")) == json.loads(_good_sidecar())
        assert _files(mezz_project) == [dst.name, sidecar.name]  # no temporary, no partial

    def test_sidecar_land_the_others_sidecar_that_is_already_there_is_used_without_error(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        dst = mezz_project.root / job.path
        moves = SidecarMoves(planted=_good_sidecar())
        monkeypatch.setattr(os, "replace", moves)
        clock = fake_clock(monkeypatch, FakeClock())
        _Fake(monkeypatch, made=90)
        entry = build_mezz(mezz_project, job, _a1(), FPS, None)  # no ProjectError
        assert entry == MezzEntry(dst.resolve(), 45, 135, 1440, 2560)
        assert moves.refused >= 1 and clock.sleeps == []  # it looked first: no turn
        assert dst.read_bytes() == b"mp4" * 5
        assert json.loads(Path(f"{dst}.json").read_text(encoding="utf-8")) == json.loads(
            _good_sidecar()
        )
        assert _files(mezz_project) == [dst.name, f"{dst.name}.json"]  # and no `.tmp`

    def test_sidecar_land_a_different_sidecar_that_is_never_let_go_is_the_error_of_today(
        self, mezz_project: Project, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _job()
        dst = _plant(mezz_project, job, size=7, qhash="sha256:not-this-clip")  # not fresh
        sidecar = Path(f"{dst}.json")
        before = sidecar.read_text(encoding="utf-8")
        monkeypatch.setattr(os, "replace", SidecarMoves())
        clock = fake_clock(monkeypatch, FakeClock())
        _Fake(monkeypatch, made=90)
        with pytest.raises(ProjectError) as info:
            build_mezz(mezz_project, job, _a1(), FPS, None)
        assert info.value.exit_code == 3
        named = Path(f"{dst.resolve()}.json")  # `build_mezz` names the resolved path
        assert info.value.message_es == f"cierra el archivo {named} en el reproductor y repite"
        assert 99 <= len(clock.sleeps) <= 101  # about 100 turns of 0.1 s
        assert 10.0 - 1e-6 <= clock.now - 1000.0 < 10.2  # and not past the 10 s
        assert sidecar.read_text(encoding="utf-8") == before  # theirs, as it was
        assert _files(mezz_project) == [dst.name, sidecar.name]  # the temporary is gone
