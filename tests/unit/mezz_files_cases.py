"""The files of the mezzanines (spec S1.5b rows 32, 40 and 49; 001.25 points 1 and 9, 001.26 point
1): where a run of frames is found and which file is fresh. How one is made is in
`mezz_build_cases.py`.

Collected from `test_mezz_plan.py`.
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

from kcut.config.template import render_template
from kcut.errors import InternalError
from kcut.ff.color import CHAIN_VERSION
from kcut.ingest.inventory import Clip
from kcut.project import Project, open_project
from kcut.render.mezz import MezzJob
from kcut.render.mezz_files import (
    MezzEntry,
    MezzIndex,
    find_fresh,
    list_mezz,
    params_of,
)
from tests.unit.edl_fakes import inventory

__all__ = ["TestFresh", "TestLocateRun", "TestRealFrames", "mezz_project"]
FPS = 30


def _job(
    start: int = 45,
    end: int = 135,
    clip: str = "a1",
    w: int = 1440,
    h: int = 2560,
    need: int | None = None,
) -> MezzJob:
    """The job of the range `[start, end)`; `need` is its `need_end_f` (by default all of it)."""
    name = f"{clip}_{start}-{end}_{w}x{h}_{CHAIN_VERSION}.mp4"
    path = f".kcut/mezz/{name}"
    return MezzJob(clip, start, end, w, h, "chain", path, end if need is None else need)


@pytest.fixture
def mezz_project(tmp_path: Path) -> Project:
    root = tmp_path / "proyecto ñandú"
    (root / ".kcut" / "mezz").mkdir(parents=True)
    (root / "crudo").mkdir()
    (root / "crudo" / "a1.mp4").write_bytes(b"the footage")
    text = render_template("prueba", "9:16", FPS, "es", "2026-10-26")
    (root / "kcut.toml").write_text(text, encoding="utf-8")
    return open_project(str(root))


def _folder(project: Project) -> Path:
    return (project.root / ".kcut" / "mezz").resolve()


def _a1() -> Clip:
    clip = inventory().by_id("a1")
    assert clip is not None
    return clip


def _plant(project: Project, job: MezzJob, *, size: int = 10, **changes: Any) -> Path:
    """The file of `job` and the sidecar a build would have left, with `changes` on it."""
    path = project.root / job.path
    path.write_bytes(b"x" * size)
    sidecar = {
        "qhash": _a1().qhash,
        "params": params_of(job, job.start_f, job.end_f, FPS),
        "size_bytes": size,
        "frames": job.end_f - job.start_f,
    }
    sidecar.update(changes)
    Path(f"{path}.json").write_text(json.dumps(sidecar), encoding="utf-8")
    return path


class TestLocateRun:
    """Row 32 (001.25 point 1): a read run goes to the file that holds all of it."""

    INDEX = MezzIndex(
        entries={
            "a1": [
                MezzEntry(Path("big.mp4"), 45, 135, 1440, 2560),
                MezzEntry(Path("next.mp4"), 115, 195, 1440, 2560),
            ]
        }
    )

    def test_mezz_reuse_overlap_the_run_that_starts_in_the_first_but_ends_in_the_second(
        self,
    ) -> None:
        path, first, size = self.INDEX.locate_run("a1", 130, 179)
        assert (path, first, size) == (Path("next.mp4"), 15, (1440, 2560))

    def test_mezz_reuse_overlap_a_run_inside_both_takes_the_first_one(self) -> None:
        assert self.INDEX.locate_run("a1", 120, 130)[0] == Path("big.mp4")

    def test_mezz_reuse_overlap_the_index_of_the_first_frame_is_inside_that_file(self) -> None:
        assert self.INDEX.locate_run("a1", 60, 69)[1:] == (15, (1440, 2560))

    @pytest.mark.parametrize(("first", "last"), [(44, 50), (100, 195), (190, 199), (300, 301)])
    def test_mezz_reuse_overlap_a_run_that_no_file_holds_whole_is_an_internal_error(
        self, first: int, last: int
    ) -> None:
        with pytest.raises(InternalError, match=f"{first} a {last} de a1"):
            self.INDEX.locate_run("a1", first, last)

    def test_mezz_reuse_overlap_the_last_frame_of_a_file_is_end_minus_one(self) -> None:
        assert self.INDEX.locate_run("a1", 134, 134)[0] == Path("big.mp4")
        assert self.INDEX.locate_run("a1", 194, 194)[0] == Path("next.mp4")

    def test_mezz_reuse_overlap_a_clip_with_no_files_is_an_internal_error(self) -> None:
        with pytest.raises(InternalError):
            self.INDEX.locate_run("a2", 0, 0)


class TestFresh:
    """Rows 40 and 41 (001.25 points 9 and 10): the sidecar says the bytes and the frames."""

    def test_mezz_sidecar_size_a_sidecar_that_says_what_the_file_is_is_fresh(
        self, mezz_project: Project
    ) -> None:
        job = _job()
        path = _plant(mezz_project, job)
        found, corrupt = find_fresh(
            _folder(mezz_project), job, _a1(), FPS, list_mezz(path.parent)["a1"]
        )
        assert found == MezzEntry(path.resolve(), 45, 135, 1440, 2560) and not corrupt

    @pytest.mark.parametrize(
        "change",
        [
            {"size_bytes": 11},
            {"size_bytes": True},
            {"size_bytes": "10"},
            {"frames": 89},  # 001.26: now it is stale only because the job needs all 90
            {"frames": 90.0},
            {"frames": True},
            {"qhash": "sha256:other"},
        ],
    )
    def test_mezz_sidecar_size_anything_that_does_not_match_the_file_makes_it_stale(
        self, mezz_project: Project, change: dict[str, Any]
    ) -> None:
        job = _job()
        path = _plant(mezz_project, job, **change)
        found, corrupt = find_fresh(
            _folder(mezz_project), job, _a1(), FPS, list_mezz(path.parent)["a1"]
        )
        assert found is None and not corrupt

    def test_mezz_sidecar_size_a_file_with_another_size_than_the_sidecar_is_not_reused(
        self, mezz_project: Project
    ) -> None:
        """A red mp4 planted over the file, with the sidecar the real one had."""
        job = _job()
        path = _plant(mezz_project, job, size=10)
        path.write_bytes(b"red" * 7)
        assert (
            find_fresh(_folder(mezz_project), job, _a1(), FPS, list_mezz(path.parent)["a1"])[0]
            is None
        )

    @pytest.mark.parametrize("drop", ["size_bytes", "frames"])
    def test_mezz_sidecar_size_a_sidecar_from_before_these_keys_is_stale(
        self, mezz_project: Project, drop: str
    ) -> None:
        job = _job()
        path = _plant(mezz_project, job)
        sidecar = Path(f"{path}.json")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        del data[drop]
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        assert (
            find_fresh(_folder(mezz_project), job, _a1(), FPS, list_mezz(path.parent)["a1"])[0]
            is None
        )

    def test_mezz_sidecar_size_a_sidecar_that_is_not_json_is_corrupt(
        self, mezz_project: Project
    ) -> None:
        job = _job()
        path = _plant(mezz_project, job)
        Path(f"{path}.json").write_text("{no es json", encoding="utf-8")
        found, corrupt = find_fresh(
            _folder(mezz_project), job, _a1(), FPS, list_mezz(path.parent)["a1"]
        )
        assert found is None and corrupt

    def test_mezz_sidecar_size_a_bigger_file_that_holds_the_range_is_found(
        self, mezz_project: Project
    ) -> None:
        big = _plant(mezz_project, _job(45, 135))
        listed = list_mezz(big.parent)["a1"]
        found, _ = find_fresh(_folder(mezz_project), _job(60, 90), _a1(), FPS, listed)
        assert found is not None and (found.start_f, found.end_f) == (45, 135)
        assert find_fresh(_folder(mezz_project), _job(100, 140), _a1(), FPS, listed)[0] is None

    def test_mezz_sidecar_size_another_size_or_chain_is_not_a_candidate(
        self, mezz_project: Project
    ) -> None:
        listed = list_mezz(_plant(mezz_project, _job(45, 135)).parent)["a1"]
        assert (
            find_fresh(_folder(mezz_project), _job(60, 90, w=720, h=1280), _a1(), FPS, listed)[0]
            is None
        )

    def test_mezz_candidates_once_the_folder_lists_names_by_clip_and_skips_the_rest(
        self, mezz_project: Project
    ) -> None:
        folder = mezz_project.root / ".kcut" / "mezz"
        _plant(mezz_project, _job(45, 135))
        (folder / f"a1_45-135_1440x2560_{CHAIN_VERSION}.{os.getpid()}.partial.mp4").write_bytes(
            b"p"
        )
        (folder / "notes.txt").write_bytes(b"n")
        listed = list_mezz(folder)
        assert [i.name for i in listed["a1"]] == [f"a1_45-135_1440x2560_{CHAIN_VERSION}.mp4"]
        assert list(listed) == ["a1"]
        assert list_mezz(folder / "nothing") == {}


class TestRealFrames:
    """Row 49 (001.26 point 1): the frames of the sidecar are those the file really has, from 1 to
    the length of its name, and the file is reused only if its video reaches what the job reads."""

    def _find(self, project: Project, job: MezzJob, path: Path) -> MezzEntry | None:
        folder = _folder(project)
        return find_fresh(folder, job, _a1(), FPS, list_mezz(path.parent)["a1"])[0]

    def test_mezz_real_frames_a_file_that_is_shorter_than_its_name_but_reaches_the_need_is_fresh(
        self, mezz_project: Project
    ) -> None:
        job = _job(need=120)
        path = _plant(mezz_project, job, frames=80)
        entry = self._find(mezz_project, job, path)
        assert entry == MezzEntry(path.resolve(), 45, 125, 1440, 2560)  # [45, 45 + 80)

    def test_mezz_real_frames_one_that_stops_before_the_need_is_made_again(
        self, mezz_project: Project
    ) -> None:
        job = _job(need=120)
        path = _plant(mezz_project, job, frames=74)  # 45 + 74 = 119 < 120
        assert self._find(mezz_project, job, path) is None
        _plant(mezz_project, job, frames=75)  # 45 + 75 = 120: just enough
        assert self._find(mezz_project, job, path) is not None

    @pytest.mark.parametrize("frames", [0, -1, True, False, 90.0, "90", None, 91, 1000])
    def test_mezz_real_frames_a_frames_that_is_not_a_whole_number_in_range_is_stale(
        self, mezz_project: Project, frames: Any
    ) -> None:
        job = _job(need=46)  # the need is no obstacle: it is the sidecar that is not believed
        path = _plant(mezz_project, job, frames=frames)
        assert self._find(mezz_project, job, path) is None
        _, corrupt = find_fresh(
            _folder(mezz_project), job, _a1(), FPS, list_mezz(path.parent)["a1"]
        )
        assert not corrupt

    @pytest.mark.parametrize("frames", [1, 45, 90])
    def test_mezz_real_frames_the_whole_range_of_whole_numbers_is_fresh(
        self, mezz_project: Project, frames: int
    ) -> None:
        job = _job(need=46)
        path = _plant(mezz_project, job, frames=frames)
        entry = self._find(mezz_project, job, path)
        assert entry is not None and entry.end_f == 45 + frames

    def test_mezz_real_frames_a_bigger_file_is_reused_only_if_its_video_reaches_the_need(
        self, mezz_project: Project
    ) -> None:
        big = _plant(mezz_project, _job(45, 135), frames=70)  # its video ends at 115
        listed = list_mezz(big.parent)["a1"]
        folder = _folder(mezz_project)
        found, _ = find_fresh(folder, _job(60, 90, need=100), _a1(), FPS, listed)
        assert found is not None and (found.start_f, found.end_f) == (45, 115)
        assert find_fresh(folder, _job(60, 90, need=116), _a1(), FPS, listed)[0] is None
