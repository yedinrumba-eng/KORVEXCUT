"""The sweep of orphan partial files reaches `.kcut/build/v*/` (spec S1.8b round 1, 001.37 point
11; row 34). A `kcut mix` or a `kcut render` killed by force left `<name>.<pid>.partial` (up to 4
bytes for each sample) in `.kcut/build/vN/`, and the sweep did not look there. The rules are the
ones of `mezz`, `wav16`, `wav48` and `proxy` (`test_partials_sweep.py`): a regular file with one
link, a partial name with a pid, more than 24 h old; a link or a folder is never followed. The
folders are the `vN` of `.kcut/build/` (`build_dir`), one level, and not `gfx/` inside them.
"""

import os
from pathlib import Path

import pytest

from kcut.config.load import parse_config
from kcut.ingest.partials import sweep_orphan_partials
from kcut.paths import Layout
from kcut.project import Project
from tests.fixtures.links import make_dir_link, make_hard_link, remove_dir_link

NOW = 1_800_000_000.0
HOUR = 3600.0


@pytest.fixture
def project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto ñandú"
    for folder in ("mezz", "wav16", "wav48", "proxy", "build/v1", "build/v2"):
        (root / ".kcut" / folder).mkdir(parents=True)
    (root / "crudo").mkdir()
    return Project(root, parse_config("", default_name="x"), Layout(root))


def _plant(path: Path, hours: float, content: bytes = b"half a file") -> Path:
    path.write_bytes(content)
    when = NOW - hours * HOUR
    os.utime(path, (when, when))
    return path


def _names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_sweep_build_partials_old_partials_of_every_build_folder_go(project: Project) -> None:
    v1, v2 = project.layout.build_dir(1), project.layout.build_dir(2)
    _plant(v1 / "voice.f32.4242.partial", 30)  # a mix killed by force: no extension
    _plant(v1 / "mix.wav.4242.partial", 30)
    _plant(v2 / "mix_pre.f32.77.partial", 30)
    _plant(v2 / "music.f32.12345.partial.f32", 30)  # the `<name>.<pid>.partial<ext>` form
    assert sweep_orphan_partials(project, now=NOW) == 4
    assert _names(v1) == [] and _names(v2) == []


def test_sweep_build_partials_a_recent_one_is_a_process_that_is_alive_and_stays(
    project: Project,
) -> None:
    v1 = project.layout.build_dir(1)
    _plant(v1 / "voice.f32.4242.partial", 1)
    _plant(v1 / "sfx.f32.4243.partial", 24)  # exactly a day: not over it yet
    assert sweep_orphan_partials(project, now=NOW) == 0
    assert _names(v1) == ["sfx.f32.4243.partial", "voice.f32.4242.partial"]
    assert sweep_orphan_partials(project, now=NOW + 1) == 1  # a second more and it is a day old
    assert _names(v1) == ["voice.f32.4242.partial"]


def test_sweep_build_partials_what_is_not_a_partial_stays_even_if_old(project: Project) -> None:
    v1 = project.layout.build_dir(1)
    for name in (
        "voice.f32", "mix.wav", "video.mp4", "render.mp4",
        "video.partial.mp4",  # the fixed names of the render: no pid, the render deletes them
        "voice.f32.partial", "voice.f32.abc.partial", "voice.f32.4242.partial.wav.bak",
    ):  # fmt: skip
        _plant(v1 / name, 100)
    assert sweep_orphan_partials(project, now=NOW) == 0
    assert len(_names(v1)) == 8


def test_sweep_build_partials_only_the_files_of_the_folder_no_subfolder_like_gfx(
    project: Project,
) -> None:
    v1 = project.layout.build_dir(1)
    (v1 / "gfx").mkdir()
    inner = _plant(v1 / "gfx" / "f00001.4242.partial.png", 100)
    folder = v1 / "a.4242.partial"
    folder.mkdir()  # a folder with a partial name
    os.utime(folder, (NOW - 100 * HOUR, NOW - 100 * HOUR))
    assert sweep_orphan_partials(project, now=NOW) == 0
    assert inner.is_file() and folder.is_dir()


def test_sweep_build_partials_a_folder_that_is_not_a_version_is_not_swept(
    project: Project,
) -> None:
    other = project.layout.build / "otra"
    other.mkdir()
    keep = _plant(other / "voice.f32.4242.partial", 100)
    assert sweep_orphan_partials(project, now=NOW) == 0
    assert keep.is_file()


def test_sweep_build_partials_a_build_folder_that_is_a_junction_is_not_followed(
    project: Project, tmp_path: Path
) -> None:
    outside = tmp_path / "fuera"
    outside.mkdir()
    victim = _plant(outside / "voice.f32.4242.partial", 100)
    v2 = project.layout.build_dir(2)
    v2.rmdir()
    make_dir_link(v2, outside)
    try:
        assert sweep_orphan_partials(project, now=NOW) == 0
        assert victim.is_file()
    finally:
        remove_dir_link(v2)


def test_sweep_build_partials_a_hard_link_stays_and_so_does_its_twin(
    project: Project, tmp_path: Path
) -> None:
    outside = _plant(tmp_path / "ajeno.f32", 100, b"SOMEONE-ELSE")
    link = project.layout.build_dir(1) / "voice.f32.4242.partial"
    make_hard_link(link, outside)
    assert sweep_orphan_partials(project, now=NOW) == 0
    assert link.read_bytes() == outside.read_bytes() == b"SOMEONE-ELSE"


def test_sweep_build_partials_a_build_folder_of_the_cache_that_leads_outside_is_not_swept(
    project: Project, tmp_path: Path
) -> None:
    outside = tmp_path / "fuera"
    (outside / "v1").mkdir(parents=True)
    victim = _plant(outside / "v1" / "voice.f32.4242.partial", 100)
    for entry in project.layout.build.iterdir():
        entry.rmdir()
    project.layout.build.rmdir()
    make_dir_link(project.layout.build, outside)  # `.kcut/build` leads out of `.kcut/`
    try:
        assert sweep_orphan_partials(project, now=NOW) == 0
        assert victim.is_file()
    finally:
        remove_dir_link(project.layout.build)


def test_sweep_build_partials_without_a_build_folder_there_is_nothing_to_sweep(
    tmp_path: Path,
) -> None:
    root = tmp_path / "proyecto"
    (root / ".kcut" / "mezz").mkdir(parents=True)
    project = Project(root, parse_config("", default_name="x"), Layout(root))
    assert sweep_orphan_partials(project, now=NOW) == 0
