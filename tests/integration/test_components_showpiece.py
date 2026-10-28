"""The four showpiece components, captured alone (spec S1.7 rows 2, 3 and 4).

A `graphics.json` with only that cue and `captions.enabled = false` is resolved against the example
EDL, and the page is captured at the middle frame of the cue, `start + (end - start) // 2`, as raw
alpha (what `capture_stills` gives). `steps` leaves at least 1000 pixels with alpha in the strip of
full width `(y +- 0.05) * H`; `sticker` at least 1000 inside the square of side `2 * w_px` centered
on `(x * W, y * H)`; `holo_board` at least 5000 inside the rectangle `w_px x h_px` centered on its
`center` (and, at `start + type_at_f + 2`, pixels of the accent color +-10 inside it); `globe` at
least 2000 inside the circle of radius `1.5 * r_px` around its center and less than 1 % of its
pixels outside it. The same frame twice is the same pixels, in one Chromium and in two. A sticker
whose image nobody approved is a G10, exit 5.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.edl.check import check_edl_file
from kcut.gfx.capture import Shooter, capture_stills
from kcut.gfx.layer import page_for
from kcut.gfx.resolve import ResolvedGraphics, resolve
from kcut.project import load_inventory, open_project
from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import LOGO, write_logo
from tests.integration.capture_helpers import decode_png
from tests.integration.showpiece_gate_cases import *  # noqa: F403  (row 3: 300-line rule)
from tests.integration.showpiece_order_cases import *  # noqa: F403  (row 4: 300-line rule)

pytestmark = [pytest.mark.ffmpeg, pytest.mark.chromium, pytest.mark.slow]
CUES: dict[str, dict[str, Any]] = {
    "pasos": {
        "id": "pasos",
        "component": "steps",
        "start": 210,
        "end": 270,
        "params": {
            "items": [
                {"at_f": 0, "label": "PASO 1", "text": "Abre la app"},
                {"at_f": 20, "label": "PASO 2", "text": "Pega el link"},
                {"at_f": 40, "label": "PASO 3", "text": "Dale a publicar"},
            ]
        },
    },
    "mascota": {
        "id": "mascota",
        "component": "sticker",
        "start": 180,
        "end": 210,
        "params": {"image": LOGO, "exit": "fly_to", "fly_to": {"x": 0.3, "y": 0.4, "at_f": 20}},
    },
    "holo": {
        "id": "holo",
        "component": "holo_board",
        "start": 270,
        "end": 315,
        "params": {"text": "HOLA", "type_at_f": 30},
    },
    "mundo": {"id": "mundo", "component": "globe", "start": 280, "end": 315, "params": {}},
}
MIN_STEPS, MIN_STICKER, MIN_HOLO, MIN_GLOBE, MAX_OUTSIDE = 1000, 1000, 5000, 2000, 0.01
ACCENT_TOLERANCE = 10


@pytest.fixture(scope="module")
def root(view_shared: Path) -> Path:
    write_edl_v1(view_shared)
    write_logo(view_shared)  # recursos/logo.png, approved in the manifest
    return view_shared


@pytest.fixture
def showpiece_cue(root: Path) -> Callable[[str], ResolvedGraphics]:
    """The resolved graphics with only the cue `name` of `CUES` (for `showpiece_order_cases`)."""
    return lambda name: _resolve(root, CUES[name])


def _resolve(root: Path, cue: dict[str, Any]) -> ResolvedGraphics:
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")
    project = open_project(str(root))
    inventory = load_inventory(project)
    checked = check_edl_file(project, inventory, None)
    assert checked.edl is not None and not [i for i in checked.issues if i.level == "error"]
    resolved = resolve(project, checked.edl, checked.version, inventory=inventory)
    assert [i for i in resolved.issues if i.level == "error"] == [], resolved.issues
    return resolved


def _shot(resolved: ResolvedGraphics, frame: int, folder: Path) -> NDArray[np.uint8]:
    page = page_for(resolved, masked=False)
    size = (resolved.w, resolved.h)
    found = capture_stills(page, folder, [frame], resolved.fps, size, folder / "out", None)
    return decode_png(found[frame])


def _middle(resolved: ResolvedGraphics) -> int:
    (cue,) = resolved.cues
    return cue.start_f + (cue.end_f - cue.start_f) // 2


def test_components_showpiece_steps_fill_the_strip_of_their_y(root: Path, tmp_path: Path) -> None:
    resolved = _resolve(root, CUES["pasos"])
    (cue,) = resolved.cues
    y = cue.params["y"]
    assert isinstance(y, float)
    drawn = _shot(resolved, _middle(resolved), tmp_path)[:, :, 3] > 0
    height = drawn.shape[0]
    low, high = round((y - 0.05) * height), round((y + 0.05) * height)
    inside = int(drawn[low:high].sum())
    assert inside >= MIN_STEPS, f"steps: {inside} pixeles con alfa en la franja"
    outside = int(drawn.sum()) - inside
    assert outside < MAX_OUTSIDE * (inside + outside), f"steps: {outside} fuera de la franja"


def test_components_showpiece_steps_show_one_step_at_a_time_in_its_own_frames(
    root: Path, tmp_path: Path
) -> None:
    resolved = _resolve(root, CUES["pasos"])
    first, second, third = (_shot(resolved, f, tmp_path) for f in (222, 242, 262))
    before, after = _shot(resolved, 200, tmp_path), _shot(resolved, 270, tmp_path)
    assert (
        int(before[:, :, 3].max()) == 0 and int(after[:, :, 3].max()) == 0
    )  # the cue is [210, 270)
    for a, b in ((first, second), (second, third), (first, third)):
        assert not np.array_equal(a, b)  # a different step, a different picture
    assert all(int(p[:, :, 3].max()) > 0 for p in (first, second, third))


def test_components_showpiece_globe_fills_its_circle_and_not_much_else(
    root: Path, tmp_path: Path
) -> None:
    resolved = _resolve(root, CUES["mundo"])
    (cue,) = resolved.cues
    x, y, r = cue.params["x"], cue.params["y"], cue.params["r_px"]
    assert isinstance(x, float) and isinstance(y, float) and isinstance(r, int)
    drawn = _shot(resolved, _middle(resolved), tmp_path)[:, :, 3] > 0
    rows, cols = np.indices(drawn.shape)
    near = (cols - x * resolved.w) ** 2 + (rows - y * resolved.h) ** 2 <= (1.5 * r) ** 2
    inside = int((drawn & near).sum())
    outside = int(drawn.sum()) - inside
    assert inside >= MIN_GLOBE, f"globe: {inside} pixeles con alfa en el circulo"
    assert outside < MAX_OUTSIDE * (inside + outside), f"globe: {outside} fuera del circulo"


def test_components_showpiece_globe_spins_with_the_time(root: Path, tmp_path: Path) -> None:
    resolved = _resolve(root, CUES["mundo"])
    a, b = _shot(resolved, 295, tmp_path), _shot(resolved, 300, tmp_path)
    assert not np.array_equal(a, b)  # `spin` is 1.4 rad/s: 5 frames are 0.23 rad


def _alpha_in(drawn: NDArray[np.bool_], inside: NDArray[np.bool_]) -> int:
    return int((drawn & inside).sum())


def test_components_showpiece_sticker_fills_the_square_of_twice_its_width(
    root: Path, tmp_path: Path
) -> None:
    resolved = _resolve(root, CUES["mascota"])
    (cue,) = resolved.cues
    x, y, w = cue.params["x"], cue.params["y"], cue.params["w_px"]
    assert isinstance(x, float) and isinstance(y, float) and isinstance(w, int)
    drawn = _shot(resolved, _middle(resolved), tmp_path)[:, :, 3] > 0
    rows, cols = np.indices(drawn.shape)
    square = (abs(cols - x * resolved.w) <= w) & (abs(rows - y * resolved.h) <= w)  # side 2 * w_px
    inside = _alpha_in(drawn, square)
    assert inside >= MIN_STICKER, f"sticker: {inside} pixeles con alfa en el cuadrado"


def _centroid_x(shot: NDArray[np.uint8]) -> float:
    cols = np.nonzero(shot[:, :, 3] > 0)[1]
    assert cols.size > 0
    return float(cols.mean())


def test_components_showpiece_sticker_flies_to_its_point(root: Path, tmp_path: Path) -> None:
    resolved = _resolve(root, CUES["mascota"])  # exit fly_to to x = 0.3, from x = 0.5
    standing = _centroid_x(_shot(resolved, 180 + 10, tmp_path))
    flying = _centroid_x(_shot(resolved, 180 + 24, tmp_path))
    assert abs(standing - 0.5 * resolved.w) < 40, standing
    assert flying < standing - 100, (standing, flying)  # it went left, toward 0.3 * W


def test_components_showpiece_sticker_follows_its_path(root: Path, tmp_path: Path) -> None:
    path = [{"at_f": 0, "x": 0.25, "y": 0.5}, {"at_f": 20, "x": 0.75, "y": 0.5}]
    params = {"image": LOGO, "enter": "pop", "idle": "none", "exit": "none", "glow": False}
    cue = {"id": "m", "component": "sticker", "start": 180, "end": 210} | {
        "params": params | {"sparkles": False, "path": path}
    }
    resolved = _resolve(root, cue)
    xs = [_centroid_x(_shot(resolved, 180 + f, tmp_path)) for f in (5, 10, 25)]
    # the feet are at 0.375, 0.5 and 0.75 of the width (held after the last point of the path)
    for got, want in zip(xs, (0.375, 0.5, 0.75), strict=True):
        assert abs(got - want * resolved.w) < 30, (xs, want)


def _accent_pixels(shot: NDArray[np.uint8], accent: str, inside: NDArray[np.bool_]) -> int:
    """How many pixels of `shot` (BGRA) inside `inside` are the color `accent` (+-10) and opaque."""
    want = [int(accent[i : i + 2], 16) for i in (5, 3, 1)]  # B, G, R
    close = np.ones(shot.shape[:2], dtype=bool)
    for channel, value in enumerate(want):
        close &= abs(shot[:, :, channel].astype(int) - value) <= ACCENT_TOLERANCE
    return _alpha_in(close & (shot[:, :, 3] > 0), inside)


def _board_box(resolved: ResolvedGraphics) -> NDArray[np.bool_]:
    (cue,) = resolved.cues
    center, w, h = cue.params["center"], cue.params["w_px"], cue.params["h_px"]
    assert isinstance(center, dict) and isinstance(w, int) and isinstance(h, int)
    rows, cols = np.indices((resolved.h, resolved.w))
    in_cols = abs(cols - center["x"] * resolved.w) <= w / 2
    return in_cols & (abs(rows - center["y"] * resolved.h) <= h / 2)


def test_components_showpiece_holo_board_fills_its_rectangle(root: Path, tmp_path: Path) -> None:
    resolved = _resolve(root, CUES["holo"])
    (cue,) = resolved.cues
    middle = _middle(resolved)
    assert middle < cue.start_f + int(cue.params["type_at_f"])  # type: ignore[call-overload]
    drawn = _shot(resolved, middle, tmp_path)[:, :, 3] > 0  # the last letter has not fallen yet
    inside = _alpha_in(drawn, _board_box(resolved))
    assert inside >= MIN_HOLO, f"holo: {inside} pixeles con alfa en el rectangulo"


def test_components_showpiece_holo_board_has_the_accent_when_the_last_letter_falls(
    root: Path, tmp_path: Path
) -> None:
    resolved = _resolve(root, CUES["holo"])
    shot = _shot(resolved, 270 + 30 + 2, tmp_path)  # start + type_at_f + 2
    found = _accent_pixels(shot, resolved.brand["accent"], _board_box(resolved))
    assert found > 0, "holo: ningun pixel del color accent en el tablero"


def test_components_showpiece_holo_board_accent_index_null_leaves_no_letter_in_accent(
    root: Path, tmp_path: Path
) -> None:
    """Not given, the last letter has the accent; `null`, none: the difference is a whole letter."""
    frame = 270 + 30 + 10
    counts = []
    for extra in ({}, {"accent_index": None}):
        cue = CUES["holo"] | {"params": {"text": "HOLA", "type_at_f": 30, **extra}}
        resolved = _resolve(root, cue)
        shot = _shot(resolved, frame, tmp_path)
        counts.append(_accent_pixels(shot, resolved.brand["accent"], _board_box(resolved)))
    assert counts[0] > counts[1] + 1000, counts


def test_components_showpiece_holo_board_a_12_letter_word_fits_in_the_board(
    root: Path, tmp_path: Path
) -> None:
    """The widest letter, twelve times, with no accent letter (it is not white): the white of the
    letters stays inside the board with room to spare at both sides."""
    params = {"text": "MMMMMMMMMMMM", "type_at_f": 20, "type_step_f": 1, "accent_index": None}
    resolved = _resolve(root, CUES["holo"] | {"params": params})
    shot = _shot(resolved, 270 + 25, tmp_path)
    solid = (shot[:, :, 3] > 200) & (shot[:, :, :3].min(axis=2) > 200)  # the letters: near white
    cols = np.nonzero((solid & _board_box(resolved)).any(axis=0))[0]
    assert cols.size > 0, "holo: no hay letras blancas en el tablero"
    half = 860 / 2  # `w_px` of the board, by default
    left, right = 0.5 * resolved.w - half, 0.5 * resolved.w + half
    assert left + 30 < cols.min() and cols.max() < right - 30, (cols.min(), cols.max())


@pytest.mark.parametrize("name", ["pasos", "mascota", "holo", "mundo"])
def test_showpiece_deterministic(root: Path, tmp_path: Path, name: str) -> None:
    resolved = _resolve(root, CUES[name])
    frame = _middle(resolved)
    page = page_for(resolved, masked=False)
    size = (resolved.w, resolved.h)
    with Shooter(page, tmp_path / "a", resolved.fps, size) as shooter:
        first = decode_png(shooter.shoot(frame))
        decode_png(shooter.shoot(frame - 7))  # another frame in between
        again = decode_png(shooter.shoot(frame))
    with Shooter(page, tmp_path / "b", resolved.fps, size) as other:
        second = decode_png(other.shoot(frame))
    assert int(first[:, :, 3].max()) > 0
    assert np.array_equal(first, again) and np.array_equal(first, second)
