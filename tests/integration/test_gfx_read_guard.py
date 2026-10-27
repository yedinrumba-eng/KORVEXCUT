"""Reads and deletes in the layer of the graphics are looked at right before they happen (spec S1.6b
round 2, 001.32 point 8; row 39), as the writes already were (row 20). Chromium is replaced by the
`Shooter` of `fake_shooter.py`; the folders are changed on purpose, in process, at the moment that
matters, and what is outside has to stay as it was.

- (a) `gfx/layer._clear` calls the guard before each `unlink`, not once before the list: with `gfx/`
  turned into a junction before the last one, the `index.json` of the folder outside is not
  deleted through the link.
- (b) `gfx/overlay` looks at each PNG with `lone_file_reason(os.lstat(path))` right before reading
  it: a PNG that was valid when the index was validated and is a hard link to a file outside when
  the render reads it is exit 3, and nothing of it gets into the video.
"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from kcut.gfx import capture as gfx_capture
from kcut.gfx.capture_index import png_name
from kcut.gfx.overlay import OverlaySource
from tests.fixtures.links import make_dir_link, make_hard_link, remove_dir_link
from tests.integration.fake_shooter import install_fake_shooter
from tests.integration.graphics_helpers import tree_hash
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
__all__ = ["small", "small_base"]
BUILD = ".kcut/build/v1"
GFX = f"{BUILD}/gfx"
CHANGED = (
    "el PNG del frame {f} de la capa de gráficos cambió durante el render; "
    "corre kcut graphics capture --force"
)


def _label_doc() -> dict[str, Any]:
    cue = {"id": "x", "component": "label", "start": 3, "end": 9, "params": {"text": "x"}}
    return {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}


def _captured(root: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Capture the layer of `root` once, with the fake shooter, and give back its frames."""
    (root / "edit" / "graphics.json").write_text(json.dumps(_label_doc()), encoding="utf-8")
    install_fake_shooter(monkeypatch)
    code, doc, err = kcut_json("graphics", "capture", *project_args(root))
    assert code == 0 and doc["captured"] is True, (doc, err)
    index = json.loads((root / GFX / "index.json").read_text(encoding="utf-8"))
    assert len(index["frames"]) >= 3
    return list(index["frames"])


def _red_png(w: int, h: int) -> bytes:
    """A PNG of `w` x `h`, opaque red: what a render would blend visibly if it read it."""
    pixels = np.zeros((h, w, 4), np.uint8)
    pixels[:, :] = (0, 0, 255, 255)
    done, data = cv2.imencode(".png", pixels)
    assert done
    return bytes(data.tobytes())


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gfx_read_guard_a_junction_before_the_last_unlink_is_exit_3_and_the_outside_stays(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frames = _captured(small, kcut_json, monkeypatch)
    gfx = small / GFX
    stale = [png_name(f) for f in frames] + ["index.json"]
    outside = tmp_path / "ajeno"
    outside.mkdir()
    for name in stale:  # the folder outside has a file with each name that `_clear` deletes
        (outside / name).write_bytes(b"NOT OF KCUT " + name.encode("ascii"))
    before = tree_hash(outside)

    state = {"armed": True, "done": 0}
    real_unlink = Path.unlink
    real_capture = gfx_capture.capture

    def swap() -> None:
        gfx.rename(gfx.with_name("gfx-real"))
        make_dir_link(gfx, outside)

    def unlink(self: Path, *args: Any, **kwargs: Any) -> None:
        real_unlink(self, *args, **kwargs)
        if state["armed"] and self.name in stale:
            state["done"] += 1
            if state["done"] == len(stale) - 1:  # all but the last are gone: now it is the last
                swap()

    def capture(*args: Any, **kwargs: Any) -> list[int]:
        state["armed"] = False  # `_clear` is over by now
        return real_capture(*args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(gfx_capture, "capture", capture)
    try:
        code, doc, _ = kcut_json("graphics", "capture", "--force", *project_args(small))
    finally:
        monkeypatch.undo()
        remove_dir_link(gfx)
        if gfx.with_name("gfx-real").exists() and not gfx.exists():
            gfx.with_name("gfx-real").rename(gfx)
    assert state["done"] == len(stale) - 1, state  # the junction went in where the test meant
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert tree_hash(outside) == before  # not the `index.json` and not one of the PNGs


def test_gfx_read_guard_a_png_that_became_a_hard_link_before_the_blend_is_exit_3_and_no_video(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frames = _captured(small, kcut_json, monkeypatch)
    build = small / BUILD
    for name in ("video.mp4", "render.mp4"):  # the render of the base project left them
        (build / name).unlink(missing_ok=True)
    outside = tmp_path / "ajeno.png"
    outside.write_bytes(_red_png(1080, 1920))  # a good picture of the size of the video
    before = _sha(outside)
    first = frames[0]
    real_init: Callable[..., None] = OverlaySource.__init__

    def init(self: OverlaySource, *args: Any, **kwargs: Any) -> None:
        real_init(self, *args, **kwargs)  # the index is validated; the blend has not begun
        png = small / GFX / png_name(first)
        png.unlink()
        make_hard_link(png, outside)

    monkeypatch.setattr(OverlaySource, "__init__", init)
    code, doc, err = kcut_json("render", *project_args(small))
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert doc["error"]["message"] == CHANGED.format(f=first)
    assert not (build / "video.mp4").exists() and not (build / "render.mp4").exists()
    assert not list(build.glob("*.partial*"))
    assert _sha(outside) == before
