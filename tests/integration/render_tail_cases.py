"""`kcut render` and a video that ends a little before its container (spec S1.5b rows 48, 49 and
50; 001.26 points 1 and 2): the check is against the last frame the EDL reads and not against the
range with its margin, the sidecar says the frames the file really has, and a fresh file that
another process reads is not replaced.

Collected from `test_render_synth.py`, which is at the 300-line limit. `small` is the fixture of
`render_small_cases.py` (a copy of the project with the 2 s EDL, already rendered once).
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.errors import ProjectError
from kcut.ingest import sidecar as sidecar_module
from kcut.ingest.inventory import load_inventory
from kcut.project import open_project
from kcut.render.mezz import plan_mezz
from kcut.render.mezz_files import build_mezz
from tests.conftest import run_kcut
from tests.fixtures.av_probe import stream_tags
from tests.fixtures.synth_late_video import make_short_video
from tests.integration.render_small_cases import approve, mezz_files, render_json

__all__ = ["TestMezzReaderOpen", "TestMezzRealFrames", "TestMezzShortTail"]
EDL = "edit/edl-v1.json"


def _nb_frames(video: Path) -> int:
    return int(stream_tags(video, "nb_frames")["nb_frames"])


def _clip_project(tmp_path: Path, video_s: float, audio_s: float) -> tuple[Path, int, str]:
    """A project with one clip whose video is `video_s` s and whose audio is `audio_s` s: the
    root, the frames of its container and its `qhash`."""
    root = tmp_path / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    make_short_video(root / "crudo" / "corto.mov", video_s=video_s, audio_s=audio_s)
    ingested = run_kcut("ingest", "--project", str(root), "--json")
    assert ingested.returncode == 0, ingested.stderr
    clip = load_inventory(root / ".kcut" / "inventory.json", root).by_id("a1")
    assert clip is not None and clip.frames is not None
    return root, clip.frames, clip.qhash


def _write_edl(root: Path, qhash: str, reads: int) -> None:
    """A voice clip and a camera of `a1` that read its source frames `0` to `reads - 1`."""
    document: dict[str, Any] = {
        "schema": "kcut.edl/1",
        "version": 1,
        "fps": 30,
        "output": {"w": 1080, "h": 1920},
        "frames": reads,
        "look": "neutro",
        "sources": {"a1": {"qhash": qhash}},
        "clips": [{"kind": "voice", "at_f": 0, "src": "a1", "in_f": 0, "out_f": reads, "why": "x"}],
        "spans": [{"kind": "cam", "at_f": 0, "dur_f": reads, "src": "a1"}],
    }
    (root / "edit").mkdir(exist_ok=True)
    (root / EDL).write_text(json.dumps(document), encoding="utf-8")
    approve(root)


class TestMezzShortTail:
    """Row 48: the video of a phone clip ends some milliseconds before its audio."""

    def test_mezz_short_tail_50_ms_of_video_less_than_the_audio_renders_and_is_reused(
        self, tmp_path: Path
    ) -> None:
        root, container, qhash = _clip_project(tmp_path, 4.00, 4.05)
        assert container == 121  # the container has one frame that the video does not
        _write_edl(root, qhash, 120)  # the EDL reads the frames 0-119: all the video has
        code, doc, err = render_json(root)
        assert code == 0 and doc["frames"] == 120 and doc["mezz_built"] == 1, (doc, err)
        (mezz,) = mezz_files(root)
        assert mezz.name == "a1_0-121_320x568_tm2.mp4"  # the name is the one of the plan
        assert _nb_frames(mezz) == 120
        sidecar = json.loads(Path(f"{mezz}.json").read_text(encoding="utf-8"))
        assert sidecar["frames"] == 120 and sidecar["params"]["end_f"] == 121
        code, doc, err = render_json(root)  # the same EDL finds the same file
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (0, 1), (doc, err)

    def test_mezz_short_tail_4_s_of_video_5_s_of_audio_and_an_edl_that_stops_at_the_109_renders(
        self, tmp_path: Path
    ) -> None:
        root, container, qhash = _clip_project(tmp_path, 4, 5)
        assert container == 150
        _write_edl(root, qhash, 110)  # frames 0-109; the range is [0, 125) and the video has 120
        code, doc, err = render_json(root)
        assert code == 0 and doc["mezz_built"] == 1, (doc, err)
        (mezz,) = mezz_files(root)
        assert mezz.name == "a1_0-125_320x568_tm2.mp4" and _nb_frames(mezz) == 120
        assert json.loads(Path(f"{mezz}.json").read_text(encoding="utf-8"))["frames"] == 120

    def test_mezz_short_tail_a_span_that_reads_the_frame_the_video_does_not_have_is_exit_1(
        self, tmp_path: Path
    ) -> None:
        root, _, qhash = _clip_project(tmp_path, 4.00, 4.05)
        _write_edl(root, qhash, 121)  # it reads the frame 120, which is only in the container
        code, doc, err = render_json(root)
        assert code == 1 and doc["error"]["kind"] == "CheckFailed", (doc, err)
        assert (
            doc["error"]["message"]
            == "el video de a1 termina en el frame 120; el EDL pide hasta 121"
        )
        assert list((root / ".kcut" / "mezz").iterdir()) == []  # no file, no sidecar, no partial

    def test_mezz_short_tail_an_edl_that_needs_more_than_the_file_has_makes_it_again(
        self, tmp_path: Path
    ) -> None:
        """The file of the first render is fresh and has the name that the second one asks for,
        but its video ends before what the second one reads: it is made again, fails with the
        right message and leaves the first one as it was."""
        root, _, qhash = _clip_project(tmp_path, 4.00, 4.05)
        _write_edl(root, qhash, 120)
        assert render_json(root)[0] == 0
        (mezz,) = mezz_files(root)
        before = (mezz.read_bytes(), Path(f"{mezz}.json").read_bytes())
        _write_edl(root, qhash, 121)
        code, doc, err = render_json(root)
        assert code == 1, (doc, err)
        assert (
            doc["error"]["message"]
            == "el video de a1 termina en el frame 120; el EDL pide hasta 121"
        )
        assert (mezz.read_bytes(), Path(f"{mezz}.json").read_bytes()) == before
        assert [p.name for p in (root / ".kcut" / "mezz").iterdir()] == [
            mezz.name,
            f"{mezz.name}.json",
        ]


class TestMezzRealFrames:
    """Row 49: the frames of the sidecar are those of the file; the render reads up to the 119."""

    @pytest.mark.parametrize("frames", [89, 75])
    def test_mezz_real_frames_a_file_with_fewer_frames_that_reaches_what_is_read_is_reused(
        self, small: Path, frames: int
    ) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["frames"] = frames  # 45 + 75 = 120 is the frame after the last one that is read
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (0, 1), (doc, err)

    @pytest.mark.parametrize("frames", [74, 60])
    def test_mezz_real_frames_one_that_stops_before_what_is_read_is_made_again(
        self, small: Path, frames: int
    ) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["frames"] = frames
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), (doc, err)
        assert json.loads(sidecar.read_text(encoding="utf-8"))["frames"] == 90

    @pytest.mark.parametrize("frames", [0, True, 90.0, 91, -1, "90"])
    def test_mezz_real_frames_a_frames_that_is_not_believed_makes_it_again(
        self, small: Path, frames: Any
    ) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["frames"] = frames
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), (doc, err)
        again = json.loads(sidecar.read_text(encoding="utf-8"))["frames"]
        assert again == 90 and type(again) is int


class TestMezzReaderOpen:
    """Row 50: another process has the mezzanine open (as ffmpeg does while it decodes it) when
    this one has its own copy of the same range ready to move over it."""

    @staticmethod
    def _the_job(root: Path) -> Any:
        project = open_project(str(root))
        inventory = load_inventory(project.layout.inventory, project.root)
        rel, _ = find_edl(project, None)
        edl = check_edl_file(project, inventory, rel).edl
        assert edl is not None
        (job,) = plan_mezz(edl, inventory, project.config)
        clip = inventory.by_id("a1")
        assert clip is not None
        return project, job, clip

    def test_mezz_concurrent_reader_a_fresh_file_that_is_open_is_used_and_the_partial_goes(
        self, small: Path
    ) -> None:
        project, job, clip = self._the_job(small)
        (mezz,) = mezz_files(small)
        before = (mezz.read_bytes(), mezz.stat().st_mtime_ns)
        with mezz.open("rb"):  # on Windows this does not share the delete, as ffmpeg does not
            entry = build_mezz(project, job, clip, 30, None)
        assert entry.path == mezz.resolve() and (entry.start_f, entry.end_f) == (45, 135)
        assert (mezz.read_bytes(), mezz.stat().st_mtime_ns) == before
        assert [p.name for p in mezz.parent.iterdir()] == [mezz.name, f"{mezz.name}.json"]

    @pytest.mark.skipif(sys.platform != "win32", reason="only Windows refuses to replace it")
    def test_mezz_concurrent_reader_a_file_that_is_open_and_not_fresh_is_exit_3(
        self, small: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sidecar_module, "LAND_WAIT_S", 0.0)  # 001.29: no real wait
        project, job, clip = self._the_job(small)
        (mezz,) = mezz_files(small)
        Path(f"{mezz}.json").unlink()  # nobody vouches for it
        before = mezz.read_bytes()
        with mezz.open("rb"), pytest.raises(ProjectError) as info:
            build_mezz(project, job, clip, 30, None)
        message = info.value.message_es
        assert info.value.exit_code == 3 and "otro proceso tiene abierto" in message
        assert message.endswith("espera a que termine y repite") and "reproductor" not in message
        assert mezz.read_bytes() == before
        assert [p.name for p in mezz.parent.iterdir()] == [mezz.name]  # not even its partial
