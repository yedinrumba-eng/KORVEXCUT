"""The length of every file of the mix is exact (spec S1.8b, step 6 of `mixer.mix`, 001.15): after
each `ffmpeg` the raw float32 file is made exactly `frames * spf` samples, with zeros at the end if
it is short and cut if it is long; a difference of more than one frame is an InternalError. No
ffmpeg here: the files are made by the test.
"""

from pathlib import Path

import numpy as np
import pytest

from kcut.audio import mixer
from kcut.audio.mixer import _fit, _through_partial
from kcut.errors import InternalError, ProjectError, ToolError
from kcut.project import Project
from tests.unit.gfx_resolve_fakes import make_project

SPF, TOTAL = 1600, 16000


@pytest.fixture
def project(tmp_path: Path) -> Project:
    project = make_project(tmp_path)
    (project.root / ".kcut" / "build" / "v1").mkdir(parents=True)
    return project


def _file(project: Project, samples: int, name: str = "paso.f32") -> Path:
    path = project.root / ".kcut" / "build" / "v1" / name
    (np.arange(samples, dtype="<f4") + 1).tofile(path)  # 1, 2, 3...: nothing is silent by chance
    return path


def test_mixer_fit_a_file_of_the_exact_length_is_not_touched(project: Project) -> None:
    path = _file(project, TOTAL)
    before = path.stat()
    _fit(project, path, TOTAL, SPF)
    assert path.stat().st_mtime_ns == before.st_mtime_ns and path.stat().st_size == TOTAL * 4


@pytest.mark.parametrize("short", [1, 100, SPF])
def test_mixer_fit_a_short_file_gets_zeros_at_the_end(project: Project, short: int) -> None:
    path = _file(project, TOTAL - short)
    _fit(project, path, TOTAL, SPF)
    samples = np.fromfile(path, dtype="<f4")
    assert len(samples) == TOTAL
    assert samples[: TOTAL - short].tolist() == list(range(1, TOTAL - short + 1))
    assert not samples[TOTAL - short :].any()


@pytest.mark.parametrize("extra", [1, 100, SPF])
def test_mixer_fit_a_long_file_is_cut(project: Project, extra: int) -> None:
    path = _file(project, TOTAL + extra)
    _fit(project, path, TOTAL, SPF)
    samples = np.fromfile(path, dtype="<f4")
    assert len(samples) == TOTAL and samples.tolist() == list(range(1, TOTAL + 1))


@pytest.mark.parametrize("off", [SPF + 1, -(SPF + 1), 48000, -5000])
def test_mixer_fit_more_than_a_frame_of_difference_is_an_internal_error(
    project: Project, off: int
) -> None:
    path = _file(project, TOTAL + off)
    with pytest.raises(InternalError) as info:
        _fit(project, path, TOTAL, SPF)
    assert info.value.exit_code == 10 and "se esperaban 16000" in info.value.message_es
    assert path.stat().st_size == (TOTAL + off) * 4  # the file is left as it is


def test_mixer_fit_a_file_that_is_not_there_is_a_project_error_without_its_path(
    project: Project,
) -> None:
    with pytest.raises(ProjectError) as info:
        _fit(project, project.root / ".kcut" / "build" / "v1" / "Maria-809.f32", TOTAL, SPF)
    assert info.value.exit_code == 3 and "Maria" not in info.value.message_es


def test_mixer_fit_does_not_write_outside_the_cache(project: Project, tmp_path: Path) -> None:
    outside = tmp_path / "fuera.f32"
    (np.arange(TOTAL - 5, dtype="<f4")).tofile(outside)
    with pytest.raises(ProjectError, match=r"fuera de .kcut"):
        _fit(project, outside, TOTAL, SPF)
    assert outside.stat().st_size == (TOTAL - 5) * 4


def _fake_run(monkeypatch: pytest.MonkeyPatch, *, fails: bool) -> list[Path]:
    """A `proc.run` that writes the partial file it is given (the last argument) and, with `fails`,
    ends in a ToolError after writing half of it, as an ffmpeg that is killed does."""
    made: list[Path] = []

    def run(args: list[str], **_kwargs: object) -> None:
        made.append(Path(args[-1]))
        made[-1].write_bytes(b"half" if fails else b"whole")
        if fails:
            raise ToolError("ffmpeg terminó con error")

    monkeypatch.setattr(mixer.proc, "run", run)
    return made


def test_mixer_through_partial_moves_the_result_over_the_destination(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    dst = project.root / ".kcut" / "build" / "v1" / "salida.f32"
    dst.write_bytes(b"old")
    made = _fake_run(monkeypatch, fails=False)
    _through_partial(project, dst, lambda out: ["ffmpeg", str(out)], None, 10.0)
    assert dst.read_bytes() == b"whole" and len(made) == 1
    assert made[0].parent == dst.parent and made[0].name.endswith(".partial")
    assert not made[0].exists() and not list(dst.parent.glob("*.partial*"))


def test_mixer_through_partial_a_failure_leaves_the_destination_and_no_partial(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    dst = project.root / ".kcut" / "build" / "v1" / "salida.f32"
    dst.write_bytes(b"old")
    _fake_run(monkeypatch, fails=True)
    with pytest.raises(ToolError):
        _through_partial(project, dst, lambda out: ["ffmpeg", str(out)], None, 10.0)
    assert dst.read_bytes() == b"old" and not list(dst.parent.glob("*.partial*"))
