"""The blend of the graphics over the picture (spec S1.6b row 1): `alpha_blend` is straight alpha
in integers, `out = (base * (255 - a) + rgb * a + 127) // 255`, exact for alpha 0, 128 and 255, and
`OverlaySource` puts the PNG of a frame over it, or nothing if the frame has none.
"""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.errors import ProjectError
from kcut.gfx.capture_index import index_document, png_name
from kcut.gfx.overlay import OverlaySource, alpha_blend

W, H = 6, 4


def _png(path: Path, bgra: NDArray[np.uint8]) -> None:
    done, data = cv2.imencode(".png", bgra)
    assert done
    path.write_bytes(data.tobytes())


def _index(folder: Path, frames: list[int]) -> Path:
    path = folder / "index.json"
    path.write_text(json.dumps(index_document(30, frames, "ab" * 32)), encoding="utf-8")
    return path


def _expected(base: int, color: int, alpha: int) -> int:
    """The formula, one value at a time, with Python integers."""
    return (base * (255 - alpha) + color * alpha + 127) // 255


def test_overlay_blend_alpha_0_gives_the_base_and_alpha_255_gives_the_color() -> None:
    base = np.full((H, W, 3), (10, 120, 250), np.uint8)
    over = np.zeros((H, W, 4), np.uint8)
    over[:, :, :3] = (200, 30, 90)
    assert np.array_equal(alpha_blend(base, over), base)  # alpha 0 everywhere
    over[:, :, 3] = 255
    assert np.array_equal(alpha_blend(base, over)[:, :, :], over[:, :, :3])  # alpha 255


def test_overlay_blend_alpha_128_is_the_exact_integer_mix() -> None:
    base = np.full((H, W, 3), (10, 120, 250), np.uint8)
    over = np.zeros((H, W, 4), np.uint8)
    over[:, :, :3] = (200, 30, 90)
    over[:, :, 3] = 128
    out = alpha_blend(base, over)
    want = tuple(_expected(b, c, 128) for b, c in zip((10, 120, 250), (200, 30, 90), strict=True))
    # by hand: (10 * 127 + 200 * 128 + 127) // 255 = 26997 // 255 = 105, and 75 and 170 the same way
    assert want == (105, 75, 170)
    assert {tuple(int(v) for v in px) for row in out for px in row} == {want}


def test_overlay_blend_every_alpha_and_every_pair_of_values_follow_the_formula() -> None:
    """All 256 alphas against the corners and the middle of the range of the base and the color."""
    values = (0, 1, 127, 128, 254, 255)
    for alpha in range(256):
        for base in values:
            for color in values:
                b = np.full((1, 1, 3), base, np.uint8)
                o = np.empty((1, 1, 4), np.uint8)
                o[0, 0] = (color, color, color, alpha)
                assert int(alpha_blend(b, o)[0, 0, 0]) == _expected(base, color, alpha)


def test_overlay_blend_is_per_pixel_and_per_channel_and_leaves_the_inputs_alone() -> None:
    base = np.arange(H * W * 3, dtype=np.uint8).reshape(H, W, 3)
    over = np.zeros((H, W, 4), np.uint8)
    over[1, 2] = (255, 0, 0, 255)  # one opaque blue pixel (BGRA)
    over[2, 3] = (0, 255, 0, 128)  # one half transparent green pixel
    before = base.copy(), over.copy()
    out = alpha_blend(base, over)
    assert tuple(out[1, 2]) == (255, 0, 0) and out.dtype == np.uint8
    green = base[2, 3].astype(int)
    assert tuple(out[2, 3]) == tuple(
        _expected(int(green[i]), (0, 255, 0)[i], 128) for i in range(3)
    )
    untouched = np.ones((H, W), bool)
    untouched[1, 2] = untouched[2, 3] = False
    assert np.array_equal(out[untouched], base[untouched])
    assert np.array_equal(base, before[0]) and np.array_equal(over, before[1])


def test_overlay_source_blends_the_png_of_a_frame_and_gives_the_base_for_the_others(
    tmp_path: Path,
) -> None:
    over = np.zeros((H, W, 4), np.uint8)
    over[:, :, :3], over[:, :, 3] = (0, 0, 255), 255  # opaque red
    _png(tmp_path / png_name(7), over)
    source = OverlaySource(_index(tmp_path, [7]), W, H)
    base = np.full((H, W, 3), 50, np.uint8)
    assert np.array_equal(source.blend(base, 7), np.full((H, W, 3), (0, 0, 255), np.uint8))
    assert source.blend(base, 8) is base  # no PNG for frame 8: the base, as it is


@pytest.mark.parametrize(
    "damage", ["missing", "garbage", "wrong-size", "no-alpha", "empty", "huge-header"]
)
def test_overlay_source_a_png_that_cannot_be_used_is_exit_3_that_says_how_to_make_it_again(
    tmp_path: Path, damage: str
) -> None:
    path = tmp_path / png_name(3)
    good = np.zeros((H, W, 4), np.uint8)
    if damage == "garbage":
        path.write_bytes(b"this is not a png")
    elif damage == "wrong-size":
        _png(path, np.zeros((H + 1, W, 4), np.uint8))
    elif damage == "no-alpha":
        _png(path, np.zeros((H, W, 3), np.uint8))
    elif damage == "empty":
        path.write_bytes(b"")
    elif damage == "huge-header":  # a header that says 60000 x 60000: it is not decoded
        _png(path, good)
        raw = bytearray(path.read_bytes())
        raw[16:24] = (60000).to_bytes(4, "big") * 2
        path.write_bytes(bytes(raw))
    source = OverlaySource(_index(tmp_path, [3]), W, H)
    with pytest.raises(ProjectError) as info:
        source.blend(np.zeros((H, W, 3), np.uint8), 3)
    assert info.value.exit_code == 3
    assert info.value.message_es == (
        "el gráfico 3 de la caché está dañado; corre kcut graphics capture --force"
    )


@pytest.mark.parametrize("text", ["{no es json", "[]", '{"fps": 30}', ""])
def test_overlay_source_an_index_that_is_not_one_is_exit_3(tmp_path: Path, text: str) -> None:
    path = tmp_path / "index.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ProjectError, match="graphics capture --force"):
        OverlaySource(path, W, H)
    with pytest.raises(ProjectError, match="graphics capture --force"):
        OverlaySource(tmp_path / "no-hay.json", W, H)
