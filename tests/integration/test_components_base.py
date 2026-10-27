"""Each base component, captured alone (spec S1.6b row 3; S1.6-6 made exact in 001.15).

A `graphics.json` with only that cue of the fixture and `captions.enabled = false` is resolved
against the example EDL, and the page is captured at the middle frame of the cue,
`start + (end - start) // 2`. The component has to leave at least 1000 pixels with alpha above 0
inside the strip of full width between `(y - 0.1) * H` and `(y + 0.1) * H` (its own `y`), and less
than 1 % of its pixels with alpha outside the strip. The subtitles are the same test alone: no cues,
a transcript planted with `save_transcript`, and `captions.y` as the center of the strip.
"""

import copy
import os
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.edl.check import check_edl_file
from kcut.gfx.capture import capture_stills
from kcut.gfx.layer import page_for
from kcut.gfx.resolve import ResolvedGraphics, resolve
from kcut.project import load_inventory, open_project
from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import graphics_v1_document
from tests.integration.capture_helpers import decode_png
from tests.integration.graphics_helpers import plant_words

pytestmark = [pytest.mark.ffmpeg, pytest.mark.chromium, pytest.mark.slow]
MIN_INSIDE = 1000  # pixels with alpha in the strip
MAX_OUTSIDE = 0.01  # of the pixels with alpha, outside it


@pytest.fixture(scope="module")
def root(view_shared: Path) -> Path:
    """The synthetic project with the example EDL and the transcript of a1 planted."""
    write_edl_v1(view_shared)
    plant_words(view_shared)
    return view_shared


def _resolve(root: Path, document: dict[str, Any] | None) -> ResolvedGraphics:
    """Write `document` as `edit/graphics.json` (none: remove it) and resolve it."""
    path = root / "edit" / "graphics.json"
    if document is None:
        path.unlink(missing_ok=True)
    else:
        import json

        path.write_text(json.dumps(document), encoding="utf-8", newline="\n")
    project = open_project(str(root))
    inventory = load_inventory(project)
    checked = check_edl_file(project, inventory, None)
    assert checked.edl is not None and not [i for i in checked.issues if i.level == "error"]
    resolved = resolve(project, checked.edl, checked.version, inventory=inventory)
    assert [i for i in resolved.issues if i.level == "error"] == [], resolved.issues
    return resolved


def _alone(cue_id: str) -> dict[str, Any]:
    """The fixture with only the cue `cue_id` and the subtitles off."""
    document = copy.deepcopy(graphics_v1_document())
    document["cues"] = [c for c in document["cues"] if c["id"] == cue_id]
    document["captions"] = {"enabled": False}
    assert len(document["cues"]) == 1
    return document


def _shot(resolved: ResolvedGraphics, frame: int, folder: Path) -> NDArray[np.uint8]:
    page = page_for(resolved, masked=False)
    size = (resolved.w, resolved.h)
    found = capture_stills(page, folder, [frame], resolved.fps, size, folder / "out", None)
    return decode_png(found[frame])


def _strip(picture: NDArray[np.uint8], y: float) -> tuple[int, int]:
    """`(pixels with alpha inside the strip, pixels with alpha outside it)`."""
    height = picture.shape[0]
    drawn = picture[:, :, 3] > 0
    low, high = round((y - 0.1) * height), round((y + 0.1) * height)
    inside = int(drawn[low:high].sum())
    return inside, int(drawn.sum()) - inside


@pytest.mark.parametrize(
    "cue_id", ["gancho", "titulo", "pill", "cierre"], ids=["kinetic", "title", "label", "endcard"]
)
def test_components_base_each_component_alone_fills_its_strip_and_not_much_else(
    root: Path, tmp_path: Path, cue_id: str
) -> None:
    resolved = _resolve(root, _alone(cue_id))
    (cue,) = resolved.cues
    assert resolved.chunks == [] and resolved.captions is False
    y = cue.params["y"]
    assert isinstance(y, float)
    frame = cue.start_f + (cue.end_f - cue.start_f) // 2
    inside, outside = _strip(_shot(resolved, frame, tmp_path), y)
    assert inside >= MIN_INSIDE, f"{cue.component}: {inside} pixeles con alfa en la franja"
    assert outside < MAX_OUTSIDE * (inside + outside), (
        f"{cue.component}: {outside} de {inside + outside} pixeles con alfa fuera de la franja"
    )


def test_components_base_the_subtitles_alone_fill_the_strip_of_captions_y(
    root: Path, tmp_path: Path
) -> None:
    resolved = _resolve(root, None)  # no graphics.json: the subtitles are the whole layer
    assert resolved.cues == () and resolved.captions is True and resolved.chunks
    y = resolved.captions_cfg.y
    chunk = resolved.chunks[0]
    frame = chunk.s_f + (chunk.e_f - chunk.s_f) // 2
    inside, outside = _strip(_shot(resolved, frame, tmp_path), y)
    assert inside >= MIN_INSIDE, f"subtitulos: {inside} pixeles con alfa en la franja"
    assert outside < MAX_OUTSIDE * (inside + outside), (
        f"subtitulos: {outside} de {inside + outside} pixeles con alfa fuera de la franja"
    )


def test_components_base_the_frames_between_cues_have_nothing_drawn(
    root: Path, tmp_path: Path
) -> None:
    """The strip test means something only if a frame with no cue and no subtitle is empty."""
    resolved = _resolve(root, _alone("titulo"))  # the title is on from frame 40 to 80
    assert int(_shot(resolved, 20, tmp_path)[:, :, 3].max()) == 0
    assert int(_shot(resolved, 60, tmp_path)[:, :, 3].max()) > 0
    assert os.path.isfile(tmp_path / "page.html")
