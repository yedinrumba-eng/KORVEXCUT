"""`kcut render` with the graphics layer (spec S1.6b rows 4 and 12).

Row 4: the example EDL rendered with the fixture graphics has the same number of frames as the
render with `--no-graphics`, and at frame 60 the box of the title is another picture. Row 12
(001.15, point 40): without `edit/graphics.json` the subtitles of the transcript are drawn by
default. The page that `capture` gets (the render) has the phone number raw, because it goes into
the MP4 (001.13, point 6); the page that `capture_stills` gets in `graphics still` has it masked,
because Claude reads what a still shows. With the subtitles off, `kcut render` exits 0 without
starting Chromium and without writing `.kcut/build/v1/gfx/index.json`, and `--no-graphics` does the
same even if there is an `edit/graphics.json`.

The renders run in this process (`kcut_json`) so that a double can watch what Chromium is given.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import playwright.sync_api as sync_api
import pytest
from numpy.typing import NDArray

from kcut.ff.reader import grab
from kcut.gfx import capture as gfx_capture
from kcut.project import open_project
from tests.conftest import run_kcut
from tests.fixtures.av_probe import stream_tags
from tests.fixtures.synth_graphics import write_graphics_v1
from tests.integration.graphics_helpers import plant_words
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.chromium, pytest.mark.slow]
__all__ = ["small", "small_base"]
BUILD = ".kcut/build/v1"
W, H, FPS = 1080, 1920, 30
Rendered = tuple[Path, dict[str, Any]]
# What a1 says in the 2 s of the small EDL (source frames 60 to 119: 2000 ms to 4000 ms of its own
# clock), with a phone number said in digits
SMALL_WORDS = [
    ("Llama", 2100, 2400),
    ("972", 2500, 2800),
    ("808", 2900, 3200),
    ("3211", 3300, 3700),
]


def _frame(video: Path, f: int) -> NDArray[np.uint8]:
    return grab(video, f, FPS, (W, H), log=None)


def _mean_diff(a: NDArray[np.uint8], b: NDArray[np.uint8], rows: tuple[int, int]) -> float:
    """Mean absolute difference of the full-width rows `[rows[0], rows[1])` of two frames."""
    part = slice(*rows)
    return float(np.abs(a[part].astype(np.int16) - b[part].astype(np.int16)).mean())


def _strip(y: float) -> tuple[int, int]:
    return round((y - 0.1) * H), round((y + 0.1) * H)


def _toml(root: Path, old: str, new: str) -> None:
    path = root / "kcut.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


class _Spy:
    """Records the page that `capture` and `capture_stills` are given, and lets them run."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.captured: list[str] = []
        self.stills: list[str] = []
        real_capture, real_stills = gfx_capture.capture, gfx_capture.capture_stills

        def capture(page_html: str, *args: Any, **kwargs: Any) -> list[int]:
            self.captured.append(page_html)
            return real_capture(page_html, *args, **kwargs)

        def stills(page_html: str, *args: Any, **kwargs: Any) -> dict[int, Path]:
            self.stills.append(page_html)
            return real_stills(page_html, *args, **kwargs)

        monkeypatch.setattr(gfx_capture, "capture", capture)
        monkeypatch.setattr(gfx_capture, "capture_stills", stills)


@pytest.fixture(scope="module")
def with_graphics(tmp_path_factory: pytest.TempPathFactory, rendered_example: Rendered) -> Rendered:
    """A copy of the example project, rendered once with the fixture graphics and the transcript
    planted: `(project root, the JSON that render printed)`. The render takes half a minute."""
    root = tmp_path_factory.mktemp("gfxrender") / "proyecto ñandú"
    shutil.copytree(rendered_example[0], root)
    plant_words(root)
    write_graphics_v1(root, False)
    done = run_kcut("render", "--project", str(root), "--json")
    assert done.returncode == 0, done.stderr
    return root, json.loads(done.stdout)


class TestRenderOfTheExampleWithGraphics:
    """Row 4: the example EDL, with the four cues of the fixture and the subtitles."""

    def test_render_graphics_the_title_box_differs_and_the_frame_count_is_the_same(
        self, rendered_example: Rendered, with_graphics: Rendered
    ) -> None:
        baseline = rendered_example[0] / BUILD / "video.mp4"  # `--no-graphics`, made once
        root, doc = with_graphics
        assert doc["ok"] is True and doc["frames"] == 345
        assert set(doc) == {"ok", "video", "render", "frames", "mezz_built", "mezz_reused",
                            "elapsed_s"}  # fmt: skip
        video = root / BUILD / "video.mp4"
        count = stream_tags(video, "nb_frames")["nb_frames"]
        assert count == stream_tags(baseline, "nb_frames")["nb_frames"] == "345"
        with_gfx, without = _frame(video, 60), _frame(baseline, 60)
        low, high = _strip(0.6)
        box = (slice(low, high), slice(round(0.2 * W), round(0.8 * W)))
        diff = float(np.abs(with_gfx[box].astype(np.int16) - without[box].astype(np.int16)).mean())
        assert diff > 2, f"la caja del titulo difiere {diff:.2f} (hace falta mas de 2)"
        top = (0, round(0.1 * H))  # far from every cue at frame 60: the picture is the same
        assert _mean_diff(with_gfx, without, top) < 1.0

    def test_render_graphics_the_index_lists_the_frames_that_have_graphics(
        self, with_graphics: Rendered
    ) -> None:
        root, _ = with_graphics
        index = json.loads((root / BUILD / "gfx" / "index.json").read_text(encoding="utf-8"))
        assert index["fps"] == 30 and len(index["hash"]) == 64
        frames = index["frames"]
        assert 10 in frames and 60 in frames and 120 in frames and 330 in frames  # inside a cue
        assert 250 not in frames and 300 not in frames  # nothing is on at these frames
        assert 0 not in frames  # a frame with alpha 0 everywhere is not kept: no line is in yet
        assert all((root / BUILD / "gfx" / f"{f:06d}.png").is_file() for f in frames)


class TestDefaultCaptions:
    """Row 12 (001.15, point 40): no `edit/graphics.json`, and the subtitles are the layer."""

    @staticmethod
    def _chunk_frame(root: Path, kcut_json: Run) -> int:
        doc = kcut_json("graphics", "check", *project_args(root))[1]
        chunk = doc["chunks"][0]
        return (chunk["s_f"] + chunk["e_f"]) // 2

    def test_default_captions_the_strip_of_captions_y_differs_and_the_pages_are_as_they_say(
        self, small: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        baseline = tmp_path / "sin-graficos.mp4"
        shutil.copy2(small / BUILD / "video.mp4", baseline)  # the `--no-graphics` render
        plant_words(small, SMALL_WORDS)
        assert not (small / "edit" / "graphics.json").exists()
        spy = _Spy(monkeypatch)
        code, doc, err = kcut_json("render", *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert "G11" in err  # the subtitles are the default: a warning says so
        frame = self._chunk_frame(small, kcut_json)
        y = open_project(str(small)).config.captions.y  # the strip is centered on `captions.y`
        with_gfx, without = _frame(small / BUILD / "video.mp4", frame), _frame(baseline, frame)
        diff = _mean_diff(with_gfx, without, _strip(y))
        assert diff > 2, f"la franja de los subtitulos difiere {diff:.2f} (hace falta mas de 2)"
        # the MP4 gets the text as it was said: the phone number raw
        assert len(spy.captured) == 1 and not spy.stills
        assert '"text":"3211"' in spy.captured[0] and '"text":"972"' in spy.captured[0]
        # `graphics still` gets it masked: Claude reads what it makes
        code, doc, err = kcut_json("graphics", "still", str(frame), *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert len(spy.stills) == 1
        for word in ("972", "808", "3211"):
            assert f'"text":"{word}"' not in spy.stills[0]
        assert '"text":"**11"' in spy.stills[0]

    def test_default_captions_off_renders_without_chromium_and_without_an_index(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _toml(small, "[captions]\nenabled = true", "[captions]\nenabled = false")
        spy = _Spy(monkeypatch)

        def never() -> Any:
            raise AssertionError("se lanzó Chromium")

        monkeypatch.setattr(sync_api, "sync_playwright", never)
        code, doc, err = kcut_json("render", *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert "G12" in err and spy.captured == [] and spy.stills == []
        assert not (small / BUILD / "gfx" / "index.json").exists()
        assert not (small / BUILD / "gfx").exists()

    def test_default_captions_no_graphics_flag_renders_with_none_and_makes_no_index(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plant_words(small, SMALL_WORDS)
        write_graphics_v1(small, False)
        spy = _Spy(monkeypatch)
        code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert spy.captured == [] and not (small / BUILD / "gfx").exists()
