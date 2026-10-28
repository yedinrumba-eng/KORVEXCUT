"""`loudnorm.normalize` with the real ffmpeg (spec S1.8b, 001.15): two passes to a level. A quiet
sine goes to the target LUFS with its true peak under the ceiling; silence is copied as it is and a
`loudnorm_silence` notice says so; the result goes through a partial file, so none is left. The
files are raw float32 mono at 48 kHz in `.kcut/build/v1/`, as the mixer makes them.
"""

from pathlib import Path

import numpy as np
import pytest

from kcut.audio.loudnorm import normalize
from kcut.errors import ProjectError
from kcut.ingest.inventory import Notice
from kcut.project import Project
from tests.integration.mix_helpers import measure
from tests.unit.gfx_resolve_fakes import make_project

pytestmark = pytest.mark.ffmpeg


@pytest.fixture
def project(tmp_path: Path) -> Project:
    project = make_project(tmp_path)
    (project.root / ".kcut" / "build" / "v1").mkdir(parents=True)
    return project


def _folder(project: Project) -> Path:
    return project.root / ".kcut" / "build" / "v1"


def _tone(path: Path, amplitude: float, seconds: int = 5) -> None:
    t = np.arange(48000 * seconds) / 48000
    (amplitude * np.sin(2 * np.pi * 440.0 * t)).astype("<f4").tofile(path)


@pytest.mark.parametrize(("amplitude", "target"), [(0.02, -16.0), (0.5, -23.0)])
def test_loudnorm_normalize_brings_a_tone_to_the_target_and_under_the_ceiling(
    project: Project, amplitude: float, target: float
) -> None:
    src, dst = _folder(project) / "entra.f32", _folder(project) / "sale.f32"
    _tone(src, amplitude)
    notices: list[Notice] = []
    normalize(project, src, dst, target, -2.0, notices=notices, label="la voz")
    found = measure(dst, raw=True)
    assert found.I is not None and pytest.approx(target, abs=0.5) == found.I, found
    assert found.TP is not None and found.TP <= -1.9, found
    assert notices == [] and dst.stat().st_size == src.stat().st_size  # same length
    assert not list(_folder(project).glob("*.partial*"))


def test_loudnorm_normalize_silence_is_copied_and_a_notice_says_so(project: Project) -> None:
    src, dst = _folder(project) / "entra.f32", _folder(project) / "sale.f32"
    np.zeros(48000 * 2, dtype="<f4").tofile(src)
    notices: list[Notice] = []
    normalize(project, src, dst, -16.0, -2.0, notices=notices, label="la mezcla")
    assert dst.read_bytes() == src.read_bytes()
    assert [(n.code, n.detail) for n in notices] == [
        ("loudnorm_silence", "la mezcla está en silencio: no se normaliza")
    ]
    assert not list(_folder(project).glob("*.partial*"))


def test_loudnorm_normalize_runs_over_a_destination_that_is_already_there(project: Project) -> None:
    src, dst = _folder(project) / "entra.f32", _folder(project) / "sale.f32"
    _tone(src, 0.05)
    dst.write_bytes(b"old and useless")
    normalize(project, src, dst, -16.0, -2.0)
    assert dst.stat().st_size == src.stat().st_size


def test_loudnorm_normalize_does_not_write_outside_the_cache(
    project: Project, tmp_path: Path
) -> None:
    src = _folder(project) / "entra.f32"
    _tone(src, 0.05)
    outside = tmp_path / "fuera.f32"
    with pytest.raises(ProjectError, match=r"fuera de \.kcut"):
        normalize(project, src, outside, -16.0, -2.0)
    assert not outside.exists() and not list(tmp_path.glob("*.partial*"))
