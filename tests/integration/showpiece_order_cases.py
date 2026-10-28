"""The picture of a component frame does not depend on which frames were shown before (spec S1.7
row 4, 001.34; S1.8a row 14, 001.35): `seek(t)` is pure. Collected by `test_components_showpiece.py`
(300-line rule); it uses the fixtures `root` and `showpiece_cue` of that module (the resolved
graphics of one of its showpiece cues).

Each component, and the subtitles, is shot at six frames in two orders, going up and going down,
each order in its own Chromium: a frame has to be the same pixels in both. The check of the middle
frame twice (`test_showpiece_deterministic`) did not see that `steps` and the first `sticker`
depended on this (24 000 and 28 000 pixels apart, by frame): the soft shadows of a node that
Chromium keeps from one seek to the next are drawn from an earlier seek. 001.35 point 7: the base
components (`title`, `label`, `kinetic`, `endcard`) and the subtitles did the same, from 2 416 to
18 461 pixels apart, so the test covers all of them: the four showpieces, the four base components
(the cues of `graphics_v1_document`) and the subtitles (a transcript planted, no cues).
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut.edl.check import check_edl_file
from kcut.gfx.capture import Shooter
from kcut.gfx.layer import page_for
from kcut.gfx.resolve import ResolvedGraphics, resolve
from kcut.project import load_inventory, open_project
from tests.fixtures.synth_graphics import graphics_v1_document
from tests.integration.capture_helpers import decode_png
from tests.integration.graphics_helpers import plant_words

SHOWPIECE_NAMES = ["pasos", "mascota", "holo", "mundo"]
BASE_CUES = {c["id"]: c for c in graphics_v1_document()["cues"]}  # gancho, titulo, pill, cierre
SUBTITLES = "subtitulos"


def _frames(start: int, end: int) -> list[int]:
    return [start + 1 + round(i * (end - start - 3) / 5) for i in range(6)]


def _shots_in_two_orders(
    resolved: ResolvedGraphics, frames: list[int], folder: Path
) -> dict[str, dict[int, Any]]:
    page = page_for(resolved, masked=False)
    shots: dict[str, dict[int, Any]] = {}
    for label, order in (("up", frames), ("down", frames[::-1])):
        with Shooter(page, folder / label, resolved.fps, (resolved.w, resolved.h)) as shooter:
            shots[label] = {f: decode_png(shooter.shoot(f)) for f in order}
    return shots


def _base_resolved(root: Path, name: str) -> ResolvedGraphics:
    """The graphics with only the base cue `name` and the subtitles off, or (`SUBTITLES`) with no
    cues and the subtitles on, from the transcript of a1 planted in `root`."""
    path = root / "edit" / "graphics.json"
    if name == SUBTITLES:
        plant_words(root)
        path.unlink(missing_ok=True)
    else:
        document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}}
        document["cues"] = [BASE_CUES[name]]
        path.write_text(json.dumps(document), encoding="utf-8", newline="\n")
    project = open_project(str(root))
    inventory = load_inventory(project)
    checked = check_edl_file(project, inventory, None)
    assert checked.edl is not None and not [i for i in checked.issues if i.level == "error"]
    resolved = resolve(project, checked.edl, checked.version, inventory=inventory)
    assert [i for i in resolved.issues if i.level == "error"] == [], resolved.issues
    return resolved


def _subtitle_frames(resolved: ResolvedGraphics) -> list[int]:
    """The frames of the subtitles that the order matters in: the first five of each chunk (the
    block pops in from scale 0.86 and from opacity 0 in them) and its middle and its end. Six
    frames spread over the chunks did not see the old code differ (measured: 0 of 6, and from 1 to
    35 000 pixels in 87 of the 104 frames of the three chunks of the planted transcript)."""
    found = {
        f
        for c in resolved.chunks
        for f in (*range(c.s_f, min(c.s_f + 5, c.e_f)), (c.s_f + c.e_f) // 2, c.e_f - 2)
    }
    assert found, "no hay subtitulos"
    return sorted(found)


@pytest.mark.parametrize("name", [*SHOWPIECE_NAMES, *BASE_CUES, SUBTITLES])  # 001.35: was 4 names
def test_showpiece_order_independent(
    tmp_path: Path, name: str, root: Path, showpiece_cue: Callable[[str], ResolvedGraphics]
) -> None:
    resolved = showpiece_cue(name) if name in SHOWPIECE_NAMES else _base_resolved(root, name)
    if name == SUBTITLES:
        assert resolved.cues == () and resolved.chunks
        frames = _subtitle_frames(resolved)
    else:
        (cue,) = resolved.cues
        frames = _frames(cue.start_f, cue.end_f)
    shots = _shots_in_two_orders(resolved, frames, tmp_path)
    assert any(int(shots["up"][f][:, :, 3].max()) > 0 for f in frames), f"{name}: nada dibujado"
    for f in frames:
        assert np.array_equal(shots["up"][f], shots["down"][f]), f"{name}: el frame {f} cambia"
