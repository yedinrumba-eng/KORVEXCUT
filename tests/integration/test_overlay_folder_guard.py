"""The folder of the layer is looked at while the render reads it (spec S1.7 step 0, 001.33
point 5; row 13). The `lstat` of S1.6b row 39 looks at the PNG but follows a junction in the
folder, and the window lasts the whole render. `OverlaySource` now gets the guard of the folders of
S1.6b row 20 (the one of `build/vN` and `gfx/`) and calls it before the `lstat` of each PNG.

The test changes `gfx/` for a junction to a folder that has red PNGs of the size of the video, right
after the `OverlaySource` is made: with the guard the render stops with exit 3 and no `video.mp4`;
without it the red pixels got into the video.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from kcut.gfx.capture_index import png_name
from kcut.gfx.overlay import OverlaySource
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.integration.fake_shooter import install_fake_shooter
from tests.integration.graphics_helpers import tree_hash
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
__all__ = ["small", "small_base"]
BUILD = ".kcut/build/v1"
GFX = f"{BUILD}/gfx"


def _label_doc() -> dict[str, Any]:
    cue = {"id": "x", "component": "label", "start": 3, "end": 9, "params": {"text": "x"}}
    return {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}


def _captured(root: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Capture the layer once with the fake shooter and give back the frames of its index."""
    (root / "edit" / "graphics.json").write_text(json.dumps(_label_doc()), encoding="utf-8")
    install_fake_shooter(monkeypatch)
    code, doc, err = kcut_json("graphics", "capture", *project_args(root))
    assert code == 0 and doc["captured"] is True, (doc, err)
    index = json.loads((root / GFX / "index.json").read_text(encoding="utf-8"))
    assert len(index["frames"]) >= 3
    return list(index["frames"])


def _red_png(w: int, h: int) -> bytes:
    pixels = np.zeros((h, w, 4), np.uint8)
    pixels[:, :] = (0, 0, 255, 255)  # opaque red: visible in the video if the render reads it
    done, data = cv2.imencode(".png", pixels)
    assert done
    return bytes(data.tobytes())


def _swap(gfx: Path, outside: Path) -> Callable[[], None]:
    def swap() -> None:
        gfx.rename(gfx.with_name("gfx-real"))
        make_dir_link(gfx, outside)

    return swap


def test_overlay_folder_guard_gfx_changed_for_a_junction_after_the_source_is_made_is_exit_3(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frames = _captured(small, kcut_json, monkeypatch)
    build, gfx = small / BUILD, small / GFX
    for name in ("video.mp4", "render.mp4"):  # the render of the base project left them
        (build / name).unlink(missing_ok=True)
    outside = tmp_path / "ajeno"
    outside.mkdir()
    for f in frames:  # PNGs of the size of the video, with the names the index lists
        (outside / png_name(f)).write_bytes(_red_png(1080, 1920))
    before = tree_hash(outside)
    swap = _swap(gfx, outside)
    real_init: Callable[..., None] = OverlaySource.__init__
    state = {"swapped": 0}

    def init(self: OverlaySource, *args: Any, **kwargs: Any) -> None:
        real_init(self, *args, **kwargs)  # the index is read and valid; the blend has not begun
        state["swapped"] += 1
        swap()

    monkeypatch.setattr(OverlaySource, "__init__", init)
    try:
        code, doc, err = kcut_json("render", *project_args(small))
    finally:
        monkeypatch.undo()
        remove_dir_link(gfx)
        if gfx.with_name("gfx-real").exists() and not gfx.exists():
            gfx.with_name("gfx-real").rename(gfx)
    assert state["swapped"] == 1  # the junction went in where the test meant
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert "queda fuera de .kcut/" in doc["error"]["message"] or "enlace" in doc["error"]["message"]
    assert not (build / "video.mp4").exists() and not (build / "render.mp4").exists()
    assert not list(build.glob("*.partial*"))
    assert tree_hash(outside) == before  # no pixel of the folder outside was read into the video


def test_overlay_folder_guard_the_render_gives_the_source_the_guard_of_its_folders() -> None:
    """`OverlaySource` takes a `guard` and `commands/render.py` builds it with `folder_guard`."""
    import inspect

    from kcut.commands import render

    assert "guard" in inspect.signature(OverlaySource.__init__).parameters
    source = inspect.getsource(render)
    assert "folder_guard(" in source and "OverlaySource(" in source


def test_overlay_folder_guard_build_changed_for_a_junction_after_the_source_is_made_is_exit_3(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """001.35, row 13: `build/vN` swapped for a junction right after the `OverlaySource` is made,
    as `gfx/` is in the test above (S1.7-13): exit 3, no `video.mp4`, and nothing written through
    the junction nor read from it. The render cannot be cut in its middle with a rename: ffmpeg has
    `video.partial.mp4` open in `build/v1`, and Windows refuses to rename a folder with an open
    file in it (`PermissionError`, measured). The identity check in the middle of a blend is in
    `tests/unit/test_overlay_folder_guard_identity.py`, for each of the four folders."""
    frames = _captured(small, kcut_json, monkeypatch)
    build = small / BUILD
    for name in ("video.mp4", "render.mp4"):
        (build / name).unlink(missing_ok=True)
    outside = tmp_path / "ajeno"
    (outside / "gfx").mkdir(parents=True)
    for f in frames:  # the layer that the junction leads to, with PNGs of the size of the video
        (outside / "gfx" / png_name(f)).write_bytes(_red_png(1080, 1920))
    before = tree_hash(outside)
    swap = _swap(build, outside)
    real_init: Callable[..., None] = OverlaySource.__init__
    state = {"swapped": 0}

    def init(self: OverlaySource, *args: Any, **kwargs: Any) -> None:
        real_init(self, *args, **kwargs)  # the index is read and valid; the blend has not begun
        state["swapped"] += 1
        swap()

    monkeypatch.setattr(OverlaySource, "__init__", init)
    try:
        code, doc, err = kcut_json("render", *project_args(small))
    finally:
        monkeypatch.undo()
        remove_dir_link(build)
        if build.with_name("v1-real").exists() and not build.exists():
            build.with_name("v1-real").rename(build)
    assert state["swapped"] == 1  # the junction went in where the test meant
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    message = doc["error"]["message"]
    assert "queda fuera de .kcut/" in message or "enlace" in message or "cambió" in message
    assert tree_hash(outside) == before  # nothing was written through the junction, nor read
    assert not (build / "video.mp4").exists() and not list(build.glob("*.partial*"))
