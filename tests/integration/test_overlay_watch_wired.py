"""`kcut render` gives `watch=` to the `OverlaySource` (spec S1.8b step 0, 001.36 point 7; row 18).

S1.8a-13 made the check of the folders cost microseconds: the whole guard runs once and, before each
PNG, four identities are compared. All of that depends on `commands/render.py` passing `watch=`;
without it the source runs the whole guard before each PNG (1.7 ms a frame), and no test failed.
Here a render with 60 frames of graphics counts how many times the whole guard of folders runs: at
most 5. Without `watch=` it is once for the source and once per PNG, 61, and this test fails (it
was seen to fail with `watch=` taken out of the render).
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.commands import render
from kcut.gfx.capture_index import INDEX_NAME
from tests.integration.fake_shooter import install_fake_shooter
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
__all__ = ["small", "small_base"]
MOST_CALLS = 5
GFX_INDEX = f".kcut/build/v1/gfx/{INDEX_NAME}"


def _sixty_frames_of_graphics(root: Path) -> None:
    cue = {"id": "x", "component": "label", "start": 0, "end": 60, "params": {"text": "x"}}
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


def test_overlay_watch_wired_a_render_runs_the_whole_guard_of_folders_a_few_times_at_most(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    _sixty_frames_of_graphics(small)
    install_fake_shooter(monkeypatch)
    calls: list[int] = []
    real_folder_guard = render.folder_guard

    def counting_folder_guard(*args: Any, **kwargs: Any) -> Any:
        """The guard that `render` builds for the `OverlaySource`, counted each time it runs."""
        whole = real_folder_guard(*args, **kwargs)

        def counted() -> None:
            calls.append(1)
            whole()

        return counted

    monkeypatch.setattr(render, "folder_guard", counting_folder_guard)
    code, doc, err = kcut_json("render", *project_args(small))
    assert code == 0 and doc["ok"] is True and doc["frames"] == 60, (doc, err)
    index = json.loads((small / GFX_INDEX).read_text(encoding="utf-8"))
    assert len(index["frames"]) == 60  # every frame of the video has a PNG to blend
    assert 1 <= len(calls) <= MOST_CALLS, f"the whole guard ran {len(calls)} times"
