"""`kcut render` and the mezzanines, round 2 of S1.5b (spec 001.25, points 1, 7, 8 and 9; rows 32,
38, 39 and 40): a bigger file that was reused next to one made for the rest, a video that is shorter
than the range, two renders that make the same file, and a file that is not what its sidecar says.

Collected from `test_render_synth.py`, which is at the 300-line limit. `small` is the fixture of
`render_small_cases.py` (a copy of the project with the 2 s EDL, whose mezzanine `a1_45-135` is
already made).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.ingest.inventory import load_inventory
from tests.conftest import run_kcut
from tests.fixtures.av_probe import stream_tags
from tests.fixtures.synth_late_video import make_short_video
from tests.fixtures.synth_media import _ffmpeg
from tests.integration.render_small_cases import approve, mezz_files, render_json

__all__ = ["TestMezzConcurrent", "TestMezzReuseOverlap", "TestMezzShort", "TestMezzSidecarSize"]
EDL = "edit/edl-v1.json"
MEZZ = ".kcut/mezz"


def _edit(root: Path, name: str = "edl-v1.json", **changes: Any) -> None:
    path = root / "edit" / name
    document = json.loads((root / EDL).read_text(encoding="utf-8"))
    document.update(changes)
    path.write_text(json.dumps(document), encoding="utf-8")


def _first_render(root: Path) -> None:
    """The first render of the story: the EDL of 2 s with the zoom of the spec (1.5), so the
    mezzanine is `a1_45-135_1440x2560_tm2.mp4`, and nothing else in the cache."""
    shutil.rmtree(root / MEZZ)
    _edit(root, spans=[{"kind": "cam", "at_f": 0, "dur_f": 60, "src": "a1", "zoom": 1.5}])
    code, doc, err = render_json(root)
    assert code == 0 and doc["mezz_built"] == 1, err
    assert [p.name for p in mezz_files(root)] == ["a1_45-135_1440x2560_tm2.mp4"]


def _overlap_edl(root: Path) -> None:
    """The EDL of row 32, edited after that render: source frames 60-69 and 130-179 of a1."""
    _edit(
        root,
        frames=60,
        clips=[
            {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 60, "out_f": 70, "why": "x"},
            {"kind": "voice", "at_f": 10, "src": "a1", "in_f": 130, "out_f": 180, "why": "y"},
        ],
        spans=[{"kind": "cam", "at_f": 0, "dur_f": 60, "src": "a1", "zoom": 1.5}],
    )


def _frame_md5s(video: Path) -> list[str]:
    """The md5 of each decoded frame of `video`, from ffmpeg's `framemd5`."""
    args = [str(proc.tool_path("ffmpeg")), "-v", "error", "-i", str(video), "-f", "framemd5", "-"]
    text = proc.run(args, timeout_s=120).stdout.decode("ascii", "replace")
    return [
        line.rsplit(",", 1)[1].strip() for line in text.splitlines() if line[:1] != "#" and line
    ]


def _nb_frames(video: Path) -> int:
    return int(stream_tags(video, "nb_frames")["nb_frames"])


class TestMezzReuseOverlap:
    """Row 32: the first render, notes, the EDL edited, the second render."""

    def test_mezz_reuse_overlap_a_second_edl_renders_with_the_old_file_and_a_new_one(
        self, small: Path
    ) -> None:
        _first_render(small)
        _overlap_edl(small)
        code, doc, err = render_json(small)
        assert code == 0, err
        assert (doc["mezz_built"], doc["mezz_reused"], doc["frames"]) == (1, 1, 60)
        names = [p.name for p in mezz_files(small)]
        assert names == ["a1_115-195_1440x2560_tm2.mp4", "a1_45-135_1440x2560_tm2.mp4"]

    def test_mezz_reuse_overlap_the_frames_are_those_of_a_render_with_an_empty_cache(
        self, small: Path
    ) -> None:
        _first_render(small)
        _overlap_edl(small)
        cold = small.parent / "frio" / "proyecto ñandú"
        shutil.copytree(small, cold)
        shutil.rmtree(cold / MEZZ)
        shutil.rmtree(cold / ".kcut" / "build")
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 1), err
        code, doc, err = render_json(cold)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (2, 0), err
        warm = _frame_md5s(small / ".kcut/build/v1/video.mp4")
        assert len(warm) == 60 and warm == _frame_md5s(cold / ".kcut/build/v1/video.mp4")

    def test_mezz_reuse_overlap_a_third_render_reuses_both_files(self, small: Path) -> None:
        _first_render(small)
        _overlap_edl(small)
        assert render_json(small)[0] == 0
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (0, 2), err


class TestMezzSidecarSize:
    """Row 40: the sidecar says how many bytes and frames the file has, and the file must have
    them."""

    def test_mezz_sidecar_size_a_render_leaves_the_bytes_and_the_frames_of_the_file(
        self, small: Path
    ) -> None:
        (mezz,) = mezz_files(small)
        data = json.loads(Path(f"{mezz}.json").read_text(encoding="utf-8"))
        assert data["size_bytes"] == mezz.stat().st_size
        assert data["frames"] == 90 == _nb_frames(mezz)
        assert set(data) == {"qhash", "params", "size_bytes", "frames"}

    def test_mezz_sidecar_size_a_red_file_over_it_with_the_old_sidecar_is_made_again(
        self, small: Path
    ) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        before = json.loads(sidecar.read_text(encoding="utf-8"))
        red = small.parent / "rojo.mp4"
        _ffmpeg(
            [
                *("-f", "lavfi", "-i", "color=c=red:s=1440x2560:r=30:d=3,format=yuv420p"),
                *("-c:v", "libx264", "-preset", "ultrafast", str(red)),
            ]
        )
        assert red.stat().st_size != before["size_bytes"]
        shutil.copyfile(red, mezz)  # the sidecar is the one of the real file, which is bigger
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), err
        assert mezz.stat().st_size == before["size_bytes"] != red.stat().st_size
        assert json.loads(sidecar.read_text(encoding="utf-8"))["size_bytes"] == mezz.stat().st_size

    def test_mezz_sidecar_size_a_file_one_byte_shorter_is_made_again(self, small: Path) -> None:
        (mezz,) = mezz_files(small)
        mezz.write_bytes(mezz.read_bytes()[:-1])
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), err
        assert _nb_frames(mezz) == 90

    def test_mezz_sidecar_size_a_sidecar_with_the_wrong_frames_is_made_again(
        self, small: Path
    ) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["frames"] = 91  # 001.26: it was 89, which is now a file that is a frame shorter
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), err
        assert json.loads(sidecar.read_text(encoding="utf-8"))["frames"] == 90


class TestMezzConcurrent:
    """Row 39: two renders (two versions of the EDL, so two locks) make the same file."""

    def test_mezz_concurrent_two_renders_on_a_cold_cache_both_finish_and_the_file_is_whole(
        self, small: Path
    ) -> None:
        _edit(small, "edl-v2.json", version=2)
        shutil.rmtree(small / MEZZ)
        base = [sys.executable, "-I", "-X", "utf8", "-m", "kcut", "render", "--no-graphics"]
        base += ["--json", "--project", str(small)]
        children = [
            subprocess.Popen(
                [*base, *extra],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
            )
            for extra in (["--edl", "edit/edl-v1.json"], ["--edl", "edit/edl-v2.json"])
        ]
        done = [(*child.communicate(timeout=300), child.returncode) for child in children]
        assert [code for _, _, code in done] == [0, 0], done
        names = sorted(p.name for p in (small / MEZZ).iterdir())
        assert names == ["a1_45-135_1296x2304_tm2.mp4", "a1_45-135_1296x2304_tm2.mp4.json"]
        (mezz,) = mezz_files(small)
        assert _nb_frames(mezz) == 90
        data = json.loads(Path(f"{mezz}.json").read_text(encoding="utf-8"))
        assert data["size_bytes"] == mezz.stat().st_size
        code, doc, err = render_json(small)  # the file that is there is a fresh one
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (0, 1), err


class TestMezzShort:
    """Row 38: a clip whose video ends 1 s before its audio, and a span until the end."""

    @pytest.fixture
    def short(self, tmp_path: Path) -> Path:
        root = tmp_path / "proyecto ñandú"
        assert run_kcut("new", str(root)).returncode == 0
        make_short_video(root / "crudo" / "corto.mov", video_s=4)
        ingested = run_kcut("ingest", "--project", str(root), "--json")
        assert ingested.returncode == 0, ingested.stderr
        clip = load_inventory(root / ".kcut" / "inventory.json", root).by_id("a1")
        assert clip is not None and clip.frames == 150  # the container: 5 s
        document = {
            "schema": "kcut.edl/1",
            "version": 1,
            "fps": 30,
            "output": {"w": 1080, "h": 1920},
            "frames": 150,
            "look": "neutro",
            "sources": {"a1": {"qhash": clip.qhash}},
            "clips": [
                {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 0, "out_f": 150, "why": "x"}
            ],
            "spans": [{"kind": "cam", "at_f": 0, "dur_f": 150, "src": "a1"}],
        }
        (root / "edit").mkdir(exist_ok=True)
        (root / EDL).write_text(json.dumps(document), encoding="utf-8")
        approve(root)
        return root

    def test_mezz_short_the_render_is_exit_1_and_no_sidecar_is_left(self, short: Path) -> None:
        code, doc, err = render_json(short)
        assert code == 1 and doc["error"]["kind"] == "CheckFailed", (doc, err)
        assert doc["error"]["message"] == (
            "el video de a1 termina en el frame 120; el EDL pide hasta 150"
        )
        assert list((short / MEZZ).iterdir()) == []  # no file, no sidecar, no partial

    def test_mezz_short_a_span_that_stops_before_the_end_of_the_video_renders(
        self, short: Path
    ) -> None:
        _edit(
            short,
            frames=60,
            clips=[{"kind": "voice", "at_f": 0, "src": "a1", "in_f": 0, "out_f": 60, "why": "x"}],
            spans=[{"kind": "cam", "at_f": 0, "dur_f": 60, "src": "a1"}],
        )
        code, doc, err = render_json(short)
        assert code == 0 and doc["mezz_built"] == 1, err
        assert [p.name for p in mezz_files(short)] == ["a1_0-75_320x568_tm2.mp4"]
