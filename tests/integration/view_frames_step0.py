"""Rows 15 and 22 of S1.5a (step 0 of 001.22, points 1 and 8) for `kcut frames`.

Row 15: times that fall on the same frame are one frame. Row 22: a proxy whose size changes half
way (an MPEG-TS that starts at 540x960 and goes on at 1080x1920, with an inventory that says
540x960) is cut by `-max_pixels` and ends in a `ToolError`, never in a frame of the wrong size.
Collected from `test_view_frames_synth.py`.
"""

import time
from pathlib import Path
from typing import Any

import pytest

from kcut.commands import frames as frames_cmd
from kcut.ingest.inventory import load_inventory as read_inventory
from kcut.paths import resolve_in_project
from tests.fixtures.synth_media import _ffmpeg
from tests.integration.view_frames_helpers import Run, gray, project_args

__all__ = ["TestFramesDuplicateTimes", "TestMaxPixels"]

SIZES = ((540, 960), (1080, 1920))  # the proxy of the inventory is the first one
FIRST_STRETCH_FRAME = 10  # of the 30 frames of the first stretch
SECOND_STRETCH_FRAME = 45  # of the 30 frames of the second one


def _resizing_ts(dst: Path) -> None:
    """A transport stream of 1 s at 540x960 followed by 1 s at 1080x1920, timestamps continuous."""
    parts: list[Path] = []
    for n, (width, height) in enumerate(SIZES):
        part = dst.with_name(f"tramo{n}.ts")
        _ffmpeg(
            [
                *("-f", "lavfi", "-i", f"testsrc2=s={width}x{height}:r=30:d=1,format=yuv420p"),
                *("-c:v", "libx264", "-preset", "ultrafast", "-g", "15"),
                *("-muxdelay", "0", "-muxpreload", "0", "-output_ts_offset", str(n)),
                *("-f", "mpegts", str(part)),
            ]
        )
        parts.append(part)
    dst.write_bytes(b"".join(part.read_bytes() for part in parts))


def _proxy_path(root: Path) -> Path:
    clip = read_inventory(root / ".kcut" / "inventory.json").by_id("a1")
    assert clip is not None and clip.work is not None and clip.work.proxy is not None
    return resolve_in_project(root, clip.work.proxy)


class TestFramesDuplicateTimes:
    """Row 15 (001.22 point 1): `90 3s` at 30 fps is frame 90 twice; it is one frame."""

    def test_frames_duplicate_times_90_and_3s_leave_one_png_and_no_sheet(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        (view_fresh / "qa" / "vacia").mkdir(parents=True)
        code, doc, err = kcut_json(
            "frames", "a1", "90", "3s", "--out", "qa/vacia", *project_args(view_fresh)
        )
        assert code == 0, err
        assert doc["frames"] == [{"f": 90, "png": "qa/vacia/a1_f90.png"}]
        assert doc["sheet"] is None and doc["cell_width"] is None
        assert [p.name for p in (view_fresh / "qa" / "vacia").iterdir()] == ["a1_f90.png"]
        assert gray(view_fresh / "qa" / "vacia" / "a1_f90.png") >= 200  # the flash

    def test_frames_duplicate_times_keep_the_order_of_the_first_appearance(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "frames", "a1", "90", "30", "3s", "1s", "91", *project_args(view_fresh)
        )
        assert code == 0, err
        assert [item["f"] for item in doc["frames"]] == [90, 30, 91]
        assert doc["sheet"] == ".kcut/frames/a1_sheet_90-91.png"  # first and last of the list

    def test_frames_duplicate_times_two_times_in_one_frame_by_rounding_are_one(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "frames", "a1", "91", "3.0167s", "3.02s", *project_args(view_fresh)
        )
        assert code == 0, err
        assert [item["f"] for item in doc["frames"]] == [91] and doc["sheet"] is None

    def test_frames_duplicate_times_a_time_past_the_end_still_fails_whatever_the_duplicates(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        code, doc, _ = kcut_json("frames", "a1", "3s", "90", "360", *project_args(view_fresh))
        assert code == 2 and doc["error"]["kind"] == "UsageError"  # 360 is past the end

    def test_frames_duplicate_times_ask_for_the_frame_once(
        self, view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        reads: list[int] = []
        real = frames_cmd.grab

        def spy(path: Path, f: int, *args: Any, **kwargs: Any) -> Any:
            reads.append(f)
            return real(path, f, *args, **kwargs)

        monkeypatch.setattr(frames_cmd, "grab", spy)
        code, _, err = kcut_json("frames", "a1", "90", "3s", "0:03", *project_args(view_fresh))
        assert code == 0, err
        assert reads == [90]


class TestMaxPixels:
    """Row 22 (001.22 point 8)."""

    @pytest.fixture
    def resizing(self, view_fresh: Path) -> Path:
        _resizing_ts(_proxy_path(view_fresh))
        return view_fresh

    def test_max_pixels_a_frame_of_the_first_stretch_works(
        self, resizing: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json(
            "frames", "a1", str(FIRST_STRETCH_FRAME), *project_args(resizing)
        )
        assert code == 0, err
        assert (resizing / doc["frames"][0]["png"]).is_file()

    def test_max_pixels_a_frame_after_the_size_change_is_a_tool_error_and_no_png(
        self, resizing: Path, kcut_json: Run
    ) -> None:
        started = time.monotonic()
        code, doc, err = kcut_json(
            "frames", "a1", str(SECOND_STRETCH_FRAME), *project_args(resizing)
        )
        assert code == 4 and doc["error"]["kind"] == "ToolError"
        assert doc["error"]["exit_code"] == 4 and "Traceback" not in err
        assert time.monotonic() - started < 60
        assert "ffmpeg entregó 0 de 1 frames" in doc["error"]["message"]
        assert not list((resizing / ".kcut" / "frames").glob("*.png"))

    def test_max_pixels_the_stretch_before_the_change_still_works_after_a_failure(
        self, resizing: Path, kcut_json: Run
    ) -> None:
        second = kcut_json("frames", "a1", str(SECOND_STRETCH_FRAME), *project_args(resizing))
        first = kcut_json("frames", "a1", str(FIRST_STRETCH_FRAME), *project_args(resizing))
        assert (second[0], first[0]) == (4, 0)

    def test_max_pixels_the_view_filmstrip_reads_with_the_same_cap(
        self, resizing: Path, kcut_json: Run
    ) -> None:
        code, doc, _ = kcut_json(
            "view", "a1", "40", "50", "--filmstrip", "1", *project_args(resizing)
        )
        assert code == 4 and doc["error"]["kind"] == "ToolError"
        assert "ffmpeg entregó 0 de 1 frames" in doc["error"]["message"]
