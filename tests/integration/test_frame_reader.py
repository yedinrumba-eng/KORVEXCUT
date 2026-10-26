"""`FrameReader`, `grab` and `reader_args` against real ffmpeg (spec S1.4, 001.15).

A 2 s clip of black 64 x 48 frames at 30 fps with one white frame, number 10, in a folder with a
space and an accent: what comes out must be exact frames in BGR, not close ones.
"""

import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut import proc
from kcut.errors import ToolError
from kcut.ff import reader as reader_module
from kcut.ff.reader import FrameReader, grab, reader_args
from tests.fixtures.synth_media import _ffmpeg

pytestmark = pytest.mark.ffmpeg

FPS = 30
SIZE = (64, 48)  # (w, h)
FLASH = 10
_FLASH = "drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='eq(n,{n})'"


@pytest.fixture(scope="module")
def clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("lector") / "proyecto ñandú" / "negro.mp4"
    path.parent.mkdir()
    graph = f"color=c=black:s=64x48:r=30:d=2,{_FLASH.format(n=FLASH)},format=yuv420p"
    _ffmpeg(
        [
            *("-f", "lavfi", "-i", graph),
            *("-c:v", "libx264", "-preset", "ultrafast", "-crf", "10", "-g", "5"),
            *("-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"),
            str(path),
        ]
    )
    return path


def _mean(frame: np.ndarray) -> float:
    return float(frame.mean())


class TestFrameReader:
    def test_frame_reader_gives_exactly_count_bgr_frames_that_can_be_written_to(
        self, clip: Path
    ) -> None:
        with FrameReader(clip, 0, 5, FPS, SIZE, log=None) as reader:
            frames = list(reader)
        assert len(frames) == 5
        assert all(f.shape == (48, 64, 3) and f.dtype == np.uint8 for f in frames)
        frames[0][0, 0] = (1, 2, 3)  # writable: the next stage may draw on it

    def test_frame_reader_starts_exactly_at_the_frame_asked(self, clip: Path) -> None:
        # the quarter of a frame before it lands on frame `start_f`: not one before, not one after
        with FrameReader(clip, FLASH - 1, 3, FPS, SIZE, log=None) as reader:
            dark_before, flash, dark_after = [_mean(f) for f in reader]
        assert dark_before < 20 and flash > 235 and dark_after < 20

    def test_frame_reader_grab_is_one_frame(self, clip: Path) -> None:
        assert _mean(grab(clip, FLASH, FPS, SIZE, log=None)) > 235
        assert _mean(grab(clip, FLASH + 5, FPS, SIZE, log=None)) < 20

    def test_frame_reader_a_white_frame_is_white_in_all_three_channels(self, clip: Path) -> None:
        frame = grab(clip, FLASH, FPS, SIZE, log=None)
        assert frame.min() >= 232  # bt709 tv range read as full: white, not light gray
        assert abs(int(frame[..., 0].mean()) - int(frame[..., 2].mean())) <= 2

    def test_frame_reader_the_rgb_filters_run_between_the_two_conversions(self, clip: Path) -> None:
        negated = grab(clip, FLASH, FPS, SIZE, rgb_filters="negate", log=None)
        assert _mean(negated) < 20  # the flash became black
        assert _mean(grab(clip, 0, FPS, SIZE, rgb_filters="negate", log=None)) > 235

    def test_frame_reader_pre_filters_change_the_time_not_the_colors(self, clip: Path) -> None:
        with FrameReader(clip, 0, 2, FPS, SIZE, pre_filters="fps=1", log=None) as reader:
            frames = list(reader)
        assert len(frames) == 2 and all(_mean(f) < 20 for f in frames)  # frames 0 and 30

    def test_frame_reader_fewer_frames_than_asked_is_a_tool_error_that_says_how_many(
        self, clip: Path
    ) -> None:
        with (
            pytest.raises(ToolError, match=r"entregó 10 de 20 frames"),  # 60 frames in all
            FrameReader(clip, 50, 20, FPS, SIZE, log=None) as reader,
        ):
            list(reader)

    def test_frame_reader_a_file_that_is_not_there_is_a_tool_error_with_the_reason(
        self, tmp_path: Path
    ) -> None:
        with pytest.raises(ToolError, match=r"entregó 0 de 1 frames"):
            grab(tmp_path / "no existe.mp4", 0, FPS, SIZE, log=None)

    def test_frame_reader_leaves_no_process_behind(self, clip: Path) -> None:
        with FrameReader(clip, 0, 3, FPS, SIZE, log=None) as reader:
            frames = list(reader)
            assert len(frames) == 3
        # the process was waited for on leaving the `with`: nothing to kill, no error
        assert reader._child._popen.poll() is not None

    def test_frame_reader_the_child_writes_to_the_log_when_it_is_given_one(
        self, clip: Path, tmp_path: Path
    ) -> None:
        log = tmp_path / "lector.log"
        grab(clip, 0, FPS, SIZE, log=log)
        text = log.read_text(encoding="utf-8")
        assert text.startswith("$ ") and "rawvideo" in text and "[exit 0 en " in text


class TestReaderArgsRun:
    def test_reader_args_with_a_lavfi_input_runs_and_gives_count_raw_frames(self) -> None:
        graph = "color=c=white:s=32x16:r=30:d=1"
        args = reader_args(proc.tool_path("ffmpeg"), ["-f", "lavfi", "-i", graph], 3)
        done = proc.run(args)
        assert len(done.stdout) == 3 * 32 * 16 * 3
        assert np.frombuffer(done.stdout, dtype=np.uint8).min() >= 232


PY = str(getattr(sys, "_base_executable", None) or sys.executable)


def _child_that(monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    """Make the reader start a Python child with `code` instead of ffmpeg."""
    real = proc.popen

    def start(args: list[str], **kwargs: Any) -> Any:
        return real([PY, "-c", code], **kwargs)

    monkeypatch.setattr(reader_module.proc, "popen", start)


class TestFrameDeadline:
    """001.20 point 7: 60 s a frame (a parameter); if ffmpeg does not deliver, it is killed."""

    def test_frame_deadline_is_60_seconds_by_default(self) -> None:
        import inspect

        assert inspect.signature(FrameReader).parameters["deadline_s"].default == 60.0

    def test_frame_deadline_a_child_that_delivers_nothing_is_killed_and_reported(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _child_that(monkeypatch, "import time; time.sleep(120)")
        started = time.monotonic()
        reader = FrameReader(tmp_path / "x.mp4", 0, 1, FPS, (4, 4), deadline_s=1.0, log=None)
        with pytest.raises(ToolError, match="no entregó el frame 1 en 1 s"), reader:
            next(reader)
        assert time.monotonic() - started < 20  # it did not wait the 120 s of the child
        assert reader._child._popen.poll() is not None  # and the child is dead

    def test_frame_deadline_a_child_that_stalls_in_the_middle_of_a_frame_is_killed_too(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code = (
            "import sys, time; sys.stdout.buffer.write(b'12'); sys.stdout.flush(); time.sleep(120)"
        )
        _child_that(monkeypatch, code)
        reader = FrameReader(tmp_path / "x.mp4", 0, 1, FPS, (4, 4), deadline_s=1.0, log=None)
        with pytest.raises(ToolError, match="no entregó el frame 1"), reader:
            next(reader)
        assert reader._child._popen.poll() is not None

    def test_frame_deadline_a_child_in_time_is_not_touched(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        code = "import sys, time; time.sleep(0.3); sys.stdout.buffer.write(bytes(48))"
        _child_that(monkeypatch, code)
        with FrameReader(tmp_path / "x.mp4", 0, 1, FPS, (4, 4), deadline_s=30, log=None) as r:
            frame = next(r)
        assert frame.shape == (4, 4, 3) and int(frame.sum()) == 0

    @pytest.mark.slow
    def test_frame_deadline_counts_each_frame_on_its_own(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # two frames 0.9 s apart: 1.8 s in all, over a 1.5 s deadline, each one in time
        code = (
            "import sys, time\n"
            "for _ in range(2):\n"
            "    time.sleep(0.9); sys.stdout.buffer.write(bytes(48)); sys.stdout.flush()\n"
        )
        _child_that(monkeypatch, code)
        with FrameReader(tmp_path / "x.mp4", 0, 2, FPS, (4, 4), deadline_s=1.5, log=None) as r:
            assert len(list(r)) == 2


class TestCloseWaitDeadline:
    """001.21 point 7: every wait for ffmpeg has a deadline, `CLOSE_WAIT_S`; then it is killed."""

    def test_close_wait_deadline_is_10_seconds(self) -> None:
        assert reader_module.CLOSE_WAIT_S == 10.0

    def test_close_wait_deadline_a_child_that_closes_its_output_and_hangs_is_killed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _child_that(monkeypatch, "import os, time; os.close(1); time.sleep(120)")
        monkeypatch.setattr(reader_module, "CLOSE_WAIT_S", 1.0)
        reader = FrameReader(tmp_path / "x.mp4", 0, 1, FPS, (4, 4), deadline_s=60, log=None)
        started = time.monotonic()
        with pytest.raises(ToolError, match="se paso del tiempo"), reader:
            next(reader)
        assert time.monotonic() - started < 20  # it did not wait the 120 s of the child
        assert reader._child._popen.poll() is not None  # and the child is dead

    def test_close_wait_deadline_leaving_the_with_waits_that_long_and_kills(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _child_that(monkeypatch, "import time; time.sleep(120)")
        monkeypatch.setattr(reader_module, "CLOSE_WAIT_S", 1.0)
        reader = FrameReader(tmp_path / "x.mp4", 0, 1, FPS, (4, 4), log=None)
        started = time.monotonic()
        with pytest.raises(ToolError, match="no se espero"), reader:
            assert reader._child.pid > 0
        assert 1.0 <= time.monotonic() - started < 20
        assert reader._child._popen.poll() is not None
