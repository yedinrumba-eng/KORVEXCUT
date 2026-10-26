"""Row 36 of S1.4 (001.21 point 2): the size of the real stream of a proxy is checked.

The inventory says `540 x 960`; a proxy file that is really bigger (a swapped file, a hostile one)
must be refused with the same `ProjectError` as a wrong inventory, before ffmpeg decodes a frame.
ffprobe gives the size and the frame count in one call. Collected from `test_view_frames_synth.py`.
"""

from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.errors import ProjectError
from kcut.ff import reader as reader_module
from kcut.ff.reader import proxy_frame_count
from kcut.ingest.inventory import load_inventory as read_inventory
from kcut.paths import resolve_in_project
from tests.fixtures.synth_media import _ffmpeg
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["TestProxyStreamMismatch"]
MESSAGE = "el proxy no coincide con el inventario; corre kcut ingest"
HUGE = 8192


def _proxy_path(root: Path) -> Path:
    clip = read_inventory(root / ".kcut" / "inventory.json").by_id("a1")
    assert clip is not None and clip.work is not None and clip.work.proxy is not None
    return resolve_in_project(root, clip.work.proxy)


def _swap_proxy(root: Path, side: int) -> None:
    """Put a black mp4 of `side` x `side` where the proxy of a1 is."""
    graph = f"color=c=black:s={side}x{side}:r=30:d=0.1,format=yuv420p"
    _ffmpeg(
        [
            *("-f", "lavfi", "-i", graph),
            *("-c:v", "libx264", "-preset", "ultrafast"),
            str(_proxy_path(root)),
        ]
    )


def _no_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Make any start of a long-running child (the frame reader) fail the test."""
    started: list[list[str]] = []

    def popen(args: list[str], **kwargs: Any) -> None:
        started.append(args)
        raise AssertionError("ffmpeg was started on a proxy that is not the inventory's size")

    monkeypatch.setattr(reader_module.proc, "popen", popen)
    return started


class TestProxyStreamMismatch:
    def test_proxy_stream_mismatch_frames_refuses_an_8192_square_before_decoding(
        self, view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _swap_proxy(view_fresh, HUGE)
        started = _no_ffmpeg(monkeypatch)
        code, doc, _ = kcut_json("frames", "a1", "30", *project_args(view_fresh))
        assert code == 3 and doc["error"]["kind"] == "ProjectError"
        assert doc["error"]["message"] == MESSAGE and started == []
        assert not list((view_fresh / ".kcut" / "frames").glob("*.png"))

    def test_proxy_stream_mismatch_view_filmstrip_refuses_it_too(
        self, view_fresh: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _swap_proxy(view_fresh, HUGE)
        started = _no_ffmpeg(monkeypatch)
        code, doc, _ = kcut_json(
            "view", "a1", "0", "3s", "--filmstrip", "3", *project_args(view_fresh)
        )
        assert code == 3 and doc["error"]["message"] == MESSAGE and started == []

    def test_proxy_stream_mismatch_a_smaller_proxy_than_the_inventory_is_refused_as_well(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        _swap_proxy(view_fresh, 64)
        code, doc, _ = kcut_json("frames", "a1", "30", *project_args(view_fresh))
        assert code == 3 and doc["error"]["message"] == MESSAGE

    def test_proxy_stream_mismatch_the_count_asks_the_size_in_the_same_ffprobe_call(
        self, view_shared: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[list[str]] = []
        real = proc.run

        def spy(args: list[str], **kwargs: Any) -> Any:
            calls.append(args)
            return real(args, **kwargs)

        monkeypatch.setattr(reader_module.proc, "run", spy)
        count = proxy_frame_count(_proxy_path(view_shared), (540, 960), None)
        assert count > 0 and len(calls) == 1
        assert "stream=width,height,nb_frames" in calls[0]
        with pytest.raises(ProjectError, match="el proxy no coincide con el inventario"):
            proxy_frame_count(_proxy_path(view_shared), (540, 961), None)

    def test_proxy_stream_mismatch_a_proxy_of_the_inventory_size_still_works(
        self, view_shared: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("frames", "a1", "30", *project_args(view_shared))
        assert code == 0, err
        assert doc["frames"][0]["f"] == 30
