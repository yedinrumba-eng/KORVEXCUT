"""`render.preview.base_frame` (spec S1.6b, 001.15): the frame of the output without graphics, made
from the proxy. It has to be the frame that the render makes, only from the small file: every kind
of span of the example EDL (color, synchronized camera, camera with a look, screen insert with a
remap, fades) is compared with the same frame of the render of the example, on a picture reduced to
68 x 120 so that the size of the source does not count, only the crop, the zoom and the look.
"""

from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.edl.check import check_edl_file
from kcut.errors import ProjectError
from kcut.ff.reader import grab
from kcut.project import load_inventory, open_project
from kcut.render.frame_fx import fx_context  # 001.31: it moved from `render.preview`
from kcut.render.preview import base_frame
from tests.fixtures.synth_edl import write_edl_v1
from tests.integration.view_frames_helpers import remove

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
BUILD = ".kcut/build/v1"
W, H, FPS = 1080, 1920, 30
# mean difference, on the reduced picture, between the preview and the render: measured at about
# 2 (the codec, the colors of the limited range) for every kind of span, and at 129 for a frame
# 15 frames away, so 5 tells a crop or a zoom that is wrong and does not fail for the codec
MAX_DIFF = 5.0
# the kinds of span of the example EDL, one frame in the middle of each
FRAMES = {
    "color": 10,
    "cam a1 zoom 1.3 top": 60,
    "cam a2 hlg with push": 130,
    "cam a1 look calido": 190,
    "screen with remap": 240,
    "cam a1 look cinematico": 290,
    "color with fade out": 340,
}


def _small(picture: NDArray[Any]) -> NDArray[np.float32]:
    return np.asarray(cv2.resize(picture, (68, 120), interpolation=cv2.INTER_AREA), np.float32)


@pytest.fixture(scope="module")
def parts(rendered_example: tuple[Path, dict[str, Any]]) -> tuple[Any, Any, Any, Any]:
    root = rendered_example[0]
    project = open_project(str(root))
    inventory = load_inventory(project)
    checked = check_edl_file(project, inventory, None)
    assert checked.edl is not None
    return project, inventory, checked.edl, fx_context(project, checked.edl)


@pytest.mark.parametrize("name", list(FRAMES), ids=list(FRAMES))
def test_preview_base_frame_is_the_frame_that_the_render_makes(
    rendered_example: tuple[Path, dict[str, Any]], parts: tuple[Any, Any, Any, Any], name: str
) -> None:
    project, inventory, edl, ctx = parts
    f = FRAMES[name]
    preview = base_frame(project, edl, inventory, f, ctx, log=None)
    assert preview.shape == (H, W, 3) and preview.dtype == np.uint8
    rendered = grab(rendered_example[0] / BUILD / "video.mp4", f, FPS, (W, H), log=None)
    diff = float(np.abs(_small(preview) - _small(rendered)).mean())
    assert diff < MAX_DIFF, f"{name}: el preview difiere {diff:.1f} del render (maximo {MAX_DIFF})"


def test_preview_base_frame_the_frames_of_different_spans_are_different_pictures(
    parts: tuple[Any, Any, Any, Any],
) -> None:
    """The comparison above would pass for a preview that gave one picture for every frame only if
    the render were that picture too: the frames of the example are not."""
    project, inventory, edl, ctx = parts
    pictures = [
        _small(base_frame(project, edl, inventory, FRAMES[name], ctx, log=None))
        for name in ("cam a1 zoom 1.3 top", "screen with remap")
    ]
    assert float(np.abs(pictures[0] - pictures[1]).mean()) > 20


def test_preview_base_frame_a_color_span_reads_no_proxy(
    parts: tuple[Any, Any, Any, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from kcut.render import preview

    project, inventory, edl, ctx = parts

    def never(*_a: object, **_k: object) -> None:
        raise AssertionError("un tramo color no lee nada")

    monkeypatch.setattr(preview, "grab", never)
    monkeypatch.setattr(preview, "proxy_of", never)
    frame = base_frame(project, edl, inventory, 10, ctx, log=None)
    assert tuple(frame[100, 100]) == (14, 11, 11)  # #0B0B0E in BGR


def test_preview_base_frame_a_frame_with_no_span_is_a_project_error(
    parts: tuple[Any, Any, Any, Any],
) -> None:
    project, inventory, edl, ctx = parts
    with pytest.raises(ProjectError, match="no cae en ningún tramo"):
        base_frame(project, edl, inventory, edl.frames, ctx, log=None)


def test_preview_base_frame_a_proxy_that_is_missing_says_ingest(view_fresh: Path) -> None:
    write_edl_v1(view_fresh)
    remove(view_fresh, "a1", "proxy")
    project = open_project(str(view_fresh))
    inventory = load_inventory(project)
    checked = check_edl_file(project, inventory, None)
    assert checked.edl is not None
    ctx = fx_context(project, checked.edl)
    with pytest.raises(ProjectError, match="falta el proxy de a1; corre kcut ingest"):
        base_frame(project, checked.edl, inventory, 60, ctx, log=None)
