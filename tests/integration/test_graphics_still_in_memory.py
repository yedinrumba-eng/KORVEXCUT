"""`graphics still` keeps what Chromium makes in memory (spec S1.7 step 0, 001.33 point 2; row 10).

`capture_stills` used to write the raw PNG of each frame to `gfx/stills_work/` and `graphics still`
read them back without looking at the folder first (and with `--alpha` copied them as they were).
Now `capture_stills` gives the bytes of each still, and `stills_work/` holds only the page that was
drawn (masked). The pixels of the stills are the ones they were: the one with the graphics over the
frame is `alpha_blend` of the `--alpha` one over the base frame.
"""

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.edl.check import check_edl_file
from kcut.gfx.capture import capture_stills
from kcut.gfx.overlay import alpha_blend
from kcut.project import load_inventory, open_project
from kcut.render.frame_fx import fx_context
from kcut.render.preview import base_frame
from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import write_graphics_v1
from tests.integration.capture_helpers import FPS, H, W, decode_png, sample_page
from tests.integration.graphics_helpers import plant_words
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.chromium, pytest.mark.slow]
STILLS = ".kcut/build/v1/gfx/stills"
WORK = ".kcut/build/v1/gfx/stills_work"
FRAMES = (20, 60, 150)  # the hook (kinetic), the title, a subtitle


@pytest.fixture(scope="module")
def shared(view_shared: Path) -> Path:
    """The synthetic project with the example EDL, a transcript planted and the fixture graphics."""
    write_edl_v1(view_shared)
    plant_words(view_shared)
    write_graphics_v1(view_shared, False)
    return view_shared


def _base(root: Path, f: int) -> NDArray[np.uint8]:
    project = open_project(str(root))
    inventory = load_inventory(project)
    checked = check_edl_file(project, inventory, None)
    assert checked.edl is not None
    ctx = fx_context(project, checked.edl)
    return base_frame(project, checked.edl, inventory, f, ctx, log=None)


def _sha(picture: NDArray[Any]) -> str:
    """The hash of the decoded pixels: two PNG files with the same pixels have the same one."""
    return hashlib.sha256(picture.tobytes()).hexdigest()


def test_stills_in_memory_no_png_is_written_under_stills_work_and_the_page_is(
    shared: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    written: list[Path] = []
    real_open, real_replace = Path.open, os.replace

    def spy_open(self: Path, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if any(letter in mode for letter in "wxa+"):
            written.append(self)
        return real_open(self, mode, *args, **kwargs)

    def spy_replace(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
        written.append(Path(dst))
        real_replace(src, dst, *args, **kwargs)

    monkeypatch.setattr(Path, "open", spy_open)
    monkeypatch.setattr(os, "replace", spy_replace)
    code, doc, err = kcut_json("graphics", "still", *map(str, FRAMES), *project_args(shared))
    monkeypatch.undo()
    assert code == 0 and [s["f"] for s in doc["stills"]] == list(FRAMES), (doc, err)
    inside = [p.name for p in written if "/stills_work/" in p.as_posix().lower()]
    assert "page.html" in inside  # the spy does see what is written there
    assert [name for name in inside if ".png" in name.lower()] == []
    assert sorted(os.listdir(shared / WORK)) == ["page.html"]  # only the masked page is left
    for f in FRAMES:  # and the stills themselves are where they always were
        assert (shared / STILLS / f"still_{f:06d}.png").is_file()


def test_stills_in_memory_the_still_is_the_alpha_one_blended_over_the_base_frame(
    shared: Path, kcut_json: Run
) -> None:
    args = tuple(map(str, FRAMES))
    code, _, err = kcut_json("graphics", "still", *args, "--alpha", *project_args(shared))
    assert code == 0, err
    alpha = {f: decode_png(shared / STILLS / f"still_{f:06d}.png") for f in FRAMES}
    assert all(a.shape == (H, W, 4) and int(a[:, :, 3].max()) > 0 for a in alpha.values())
    code, _, err = kcut_json("graphics", "still", *args, *project_args(shared))
    assert code == 0, err
    for f in FRAMES:
        got = decode_png(shared / STILLS / f"still_{f:06d}.png")
        want = alpha_blend(_base(shared, f), alpha[f])
        assert got.shape == (H, W, 3) and _sha(got) == _sha(want), f


def test_stills_in_memory_capture_stills_gives_the_bytes_of_every_frame_and_writes_no_png(
    tmp_path: Path,
) -> None:
    found = capture_stills(sample_page(), tmp_path, [330, 50], FPS, (W, H), tmp_path / "out", None)
    assert sorted(found) == [50, 330]
    assert all(isinstance(data, bytes) for data in found.values())
    assert int(decode_png(found[50])[:, :, 3].max()) > 0  # a cue is drawn at frame 50
    assert int(decode_png(found[330])[:, :, 3].max()) == 0  # and none at 330: kept all the same
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == ["page.html"]
