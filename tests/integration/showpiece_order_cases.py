"""The picture of a showpiece frame does not depend on which frames were shown before (spec S1.7 row
4, 001.34): `seek(t)` is pure. Collected by `test_components_showpiece.py` (300-line rule); it uses
the fixture `showpiece_cue` of that module, which gives the resolved graphics of one of its cues.

Each component is shot at six frames of its cue in two orders, going up and going down, each order
in its own Chromium: a frame has to be the same pixels in both. The check of the middle frame twice
(`test_showpiece_deterministic`) did not see that `steps` and the first `sticker` depended on this
(24 000 and 28 000 pixels apart, by frame): the soft shadows of a node that Chromium keeps from one
seek to the next are drawn from an earlier seek.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut.gfx.capture import Shooter
from kcut.gfx.layer import page_for
from kcut.gfx.resolve import ResolvedGraphics
from tests.integration.capture_helpers import decode_png


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


@pytest.mark.parametrize("name", ["pasos", "mascota", "holo", "mundo"])
def test_showpiece_order_independent(
    tmp_path: Path, name: str, showpiece_cue: Callable[[str], ResolvedGraphics]
) -> None:
    resolved = showpiece_cue(name)
    (cue,) = resolved.cues
    frames = _frames(cue.start_f, cue.end_f)
    shots = _shots_in_two_orders(resolved, frames, tmp_path)
    for f in frames:
        assert np.array_equal(shots["up"][f], shots["down"][f]), f"{name}: el frame {f} cambia"
