"""Row 14 of S1.4: a clip whose video starts 0.5 s after its audio (spec 0.6, 001.15 T5).

Collected from `test_view_frames_synth.py`.
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from kcut.commands import frames as frames_cmd
from kcut.ingest.inventory import load_inventory as read_inventory
from tests.conftest import run_kcut
from tests.fixtures.synth_late_video import (
    FLASH_CLOCK_FRAME,
    SHORT_VIDEO_FRAMES,
    make_late_video,
    make_short_video,
)
from tests.integration.view_frames_helpers import Run, gray, project_args

__all__ = [
    "TestFilmstripPastVideoEnd",
    "TestFramesPastVideoEnd",
    "TestVideoStartOffset",
    "late",
    "short",
]


@pytest.fixture(scope="module")
def late(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A project with one clip, a1, whose video starts 0.5 s after its audio."""
    root = tmp_path_factory.mktemp("late") / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    make_late_video(root / "crudo" / "tarde.mov")
    ingested = run_kcut("ingest", "--project", str(root), "--json")
    assert ingested.returncode == 0, ingested.stderr
    return root


class TestVideoStartOffset:
    """Row 14: the video's first frame is frame 15 of the source clock (0.5 s at 30 fps), so frame
    `f` of the clock is index `f - 15` of the proxy, and a frame before the video is refused."""

    def test_video_start_offset_the_inventory_knows_where_the_video_starts(
        self, late: Path
    ) -> None:
        clip = read_inventory(late / ".kcut" / "inventory.json").by_id("a1")
        assert clip is not None and clip.video is not None and clip.audio is not None
        assert (clip.video.start_ms, clip.audio.start_ms, clip.frames) == (500, 0, 150)

    def test_video_start_offset_the_flash_is_frame_45_of_the_clock(
        self, late: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("frames", "a1", str(FLASH_CLOCK_FRAME), *project_args(late))
        assert code == 0, err
        assert gray(late / doc["frames"][0]["png"]) >= 200

    @pytest.mark.parametrize("f", [44, 46, 15, 149])
    def test_video_start_offset_the_other_frames_are_not_the_flash(
        self, late: Path, kcut_json: Run, f: int
    ) -> None:
        code, doc, err = kcut_json("frames", "a1", str(f), *project_args(late))
        assert code == 0, err
        assert gray(late / doc["frames"][0]["png"]) <= 180

    @pytest.mark.parametrize("f", ["14", "0", "0.1s"])
    def test_video_start_offset_a_frame_before_the_video_is_exit_2(
        self, late: Path, kcut_json: Run, f: str
    ) -> None:
        code, doc, _ = kcut_json("frames", "a1", f, *project_args(late))
        assert code == 2 and "fuera del video" in doc["error"]["message"]

    def test_video_start_offset_the_filmstrip_leaves_a_gray_hole_before_the_video(
        self, late: Path, kcut_json: Run
    ) -> None:
        # 4 cells over frames 0..60: the first one is frame 7, before the video (frame 15)
        code, doc, err = kcut_json("view", "a1", "0", "2s", "--filmstrip", "4", *project_args(late))
        assert code == 0, err
        pixels = np.asarray(Image.open(late / doc["png"]).convert("RGB"))
        cell = 2400 // 4
        assert tuple(pixels[110, cell // 2]) == (40, 40, 46)  # the hole
        assert tuple(pixels[110, cell + cell // 2]) != (40, 40, 46)  # a real frame

    def test_video_start_offset_the_filmstrip_frame_is_the_one_of_the_clock(
        self, late: Path, kcut_json: Run
    ) -> None:
        # one cell over frames 30..60: its frame is 45, the flash, and it is white in the strip
        code, doc, err = kcut_json(
            "view", "a1", "30", "60", "--filmstrip", "1", *project_args(late)
        )
        assert code == 0, err
        pixels = np.asarray(Image.open(late / doc["png"]).convert("RGB"))
        assert pixels[110, 1200].min() >= 240


@pytest.fixture(scope="module")
def short(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A project with one clip, a1, whose video (3 s) is shorter than its container (5 s)."""
    root = tmp_path_factory.mktemp("short") / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    make_short_video(root / "crudo" / "corto.mov")
    ingested = run_kcut("ingest", "--project", str(root), "--json")
    assert ingested.returncode == 0, ingested.stderr
    return root


def _fake_grab(reads: list[int]) -> Callable[..., NDArray[np.uint8]]:
    def grab(*args: object, **kwargs: object) -> NDArray[np.uint8]:
        reads.append(1)
        return np.zeros((960, 540, 3), dtype=np.uint8)

    return grab


class TestFramesPastVideoEnd:
    """S1.4-23 (001.19 point 3): the last real frame comes from the frames of the proxy, not
    from the duration of the container; and one run takes at most 64 times."""

    def test_past_video_end_the_container_has_more_frames_than_the_video(self, short: Path) -> None:
        clip = read_inventory(short / ".kcut" / "inventory.json").by_id("a1")
        assert clip is not None and clip.frames == 150  # what the container says

    @pytest.mark.parametrize(("f", "frame"), [("90", 90), ("100", 100), ("149", 149), ("4s", 120)])
    def test_past_video_end_is_exit_2_that_names_the_frame_and_the_last_one(
        self, short: Path, kcut_json: Run, f: str, frame: int
    ) -> None:
        code, doc, _ = kcut_json("frames", "a1", f, *project_args(short))
        assert code == 2 and doc["error"]["kind"] == "UsageError"  # never a ToolError (4)
        message = doc["error"]["message"]
        assert str(SHORT_VIDEO_FRAMES - 1) in message and str(frame) in message

    def test_past_video_end_the_last_real_frame_still_works(
        self, short: Path, kcut_json: Run
    ) -> None:
        last = SHORT_VIDEO_FRAMES - 1
        code, doc, err = kcut_json("frames", "a1", str(last), *project_args(short))
        assert code == 0, err
        assert gray(short / doc["frames"][0]["png"]) > 0

    def test_past_video_end_with_a_late_video_the_last_is_vs_f_plus_the_frames_less_one(
        self, late: Path, kcut_json: Run
    ) -> None:
        code, doc, _ = kcut_json("frames", "a1", "150", *project_args(late))
        assert code == 2 and "149" in doc["error"]["message"]  # 15 + 135 - 1

    def test_past_video_end_one_bad_time_among_good_ones_writes_no_picture(
        self, short: Path, kcut_json: Run
    ) -> None:
        out = "qa/ninguno"
        code, _, _ = kcut_json("frames", "a1", "10", "120", "--out", out, *project_args(short))
        assert code == 2 and not (short / out).exists()

    def test_too_many_times_65_is_a_usage_error_before_any_frame_is_read(
        self, short: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads: list[int] = []
        monkeypatch.setattr(frames_cmd, "grab", _fake_grab(reads))
        code, doc, _ = kcut_json("frames", "a1", *(["30"] * 65), *project_args(short))
        assert code == 2 and doc["error"]["kind"] == "UsageError"
        assert "64" in doc["error"]["message"] and reads == []

    def test_too_many_times_64_are_accepted(
        self, short: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads: list[int] = []
        monkeypatch.setattr(frames_cmd, "grab", _fake_grab(reads))
        code, doc, err = kcut_json("frames", "a1", *(["30"] * 64), *project_args(short))
        assert code == 0, err
        assert len(reads) == 64 and len(doc["frames"]) == 64 and doc["sheet"] is not None


class TestFilmstripPastVideoEnd:
    """S1.4-26 (001.20 point 3): `view --filmstrip` takes the frames the proxy really has."""

    def test_filmstrip_past_video_end_leaves_gray_holes_and_exits_0(
        self, short: Path, kcut_json: Run
    ) -> None:
        # 6 cells over frames 0..150: 12, 37, 62 and 87 exist (the video has 90), 112 and 137 no
        code, doc, err = kcut_json(
            "view", "a1", "0", "5s", "--filmstrip", "6", *project_args(short)
        )
        assert code == 0, err
        pixels = np.asarray(Image.open(short / doc["png"]).convert("RGB"))
        cell = 2400 // 6
        centers = [tuple(pixels[110, k * cell + cell // 2]) for k in range(6)]
        assert centers[:4] != [(40, 40, 46)] * 4 and (40, 40, 46) not in centers[:4]
        assert centers[4] == centers[5] == (40, 40, 46)

    def test_filmstrip_past_video_end_a_window_inside_the_video_has_no_hole(
        self, short: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "view", "a1", "0", "3s", "--filmstrip", "6", *project_args(short)
        )
        assert code == 0, err
        pixels = np.asarray(Image.open(short / doc["png"]).convert("RGB"))
        cell = 2400 // 6
        assert all(tuple(pixels[110, k * cell + cell // 2]) != (40, 40, 46) for k in range(6))

    def test_filmstrip_past_video_end_the_count_is_the_one_frames_uses(self, short: Path) -> None:
        from kcut.ff.reader import proxy_frame_count
        from kcut.ingest.inventory import load_inventory

        clip = load_inventory(short / ".kcut" / "inventory.json").by_id("a1")
        work = clip.work if clip is not None else None
        assert work is not None and work.proxy is not None and work.proxy_w and work.proxy_h
        size = (work.proxy_w, work.proxy_h)
        assert proxy_frame_count(short / work.proxy, size, None) == SHORT_VIDEO_FRAMES
