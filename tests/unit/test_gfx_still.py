"""`gfx/still.py` (spec S1.6b, 001.40): the steps of a still, shared by `kcut graphics still` and
the contact sheet of `kcut qa`. A layer is accepted only if it is a PNG with alpha of the size of
the video; the blend is `alpha_blend`; the PNGs are encoded in memory.
"""

import cv2
import numpy as np
import pytest

from kcut.errors import ToolError
from kcut.gfx.overlay import alpha_blend
from kcut.gfx.still import compose, decode_layer, png_bytes, transparent_png

SIZE = (40, 24)  # (W, H)


def _png(pixels: np.ndarray) -> bytes:
    done, data = cv2.imencode(".png", pixels)
    assert done
    return bytes(data.tobytes())


def _layer(alpha: int = 255) -> np.ndarray:
    pixels = np.zeros((SIZE[1], SIZE[0], 4), dtype=np.uint8)
    pixels[:, :] = (10, 200, 30, alpha)
    return pixels


def test_gfx_still_a_png_with_alpha_of_the_size_of_the_video_is_decoded_as_it_was_made() -> None:
    layer = _layer(128)
    assert np.array_equal(decode_layer(_png(layer), SIZE), layer)


@pytest.mark.parametrize(
    "shot",
    [
        b"",
        b"not a png",
        _png(np.zeros((24, 40, 3), dtype=np.uint8)),  # no alpha
        _png(np.zeros((25, 40, 4), dtype=np.uint8)),  # a row too many
        _png(np.zeros((24, 41, 4), dtype=np.uint8)),  # a column too many
        _png(np.zeros((24, 40, 4), dtype=np.uint16)),  # not 8 bits
    ],
)
def test_gfx_still_anything_else_than_that_png_is_a_tool_error(shot: bytes) -> None:
    with pytest.raises(ToolError, match="no entregó un PNG con alfa del tamaño del video"):
        decode_layer(shot, SIZE)


def test_gfx_still_compose_is_the_alpha_blend_of_the_layer_over_the_base() -> None:
    base = np.full((SIZE[1], SIZE[0], 3), 90, dtype=np.uint8)
    for alpha in (0, 77, 255):
        layer = _layer(alpha)
        assert np.array_equal(compose(base, layer), alpha_blend(base, layer))
    assert np.array_equal(compose(base, _layer(0)), base)  # nothing drawn: the base as it is
    assert compose(base, _layer(255))[0, 0].tolist() == [10, 200, 30]  # all drawn: the layer


def test_gfx_still_a_picture_goes_to_png_and_back_without_a_loss() -> None:
    picture = np.arange(24 * 40 * 3, dtype=np.uint8).reshape(24, 40, 3)
    again = cv2.imdecode(np.frombuffer(png_bytes(picture), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    assert np.array_equal(again, picture)


def test_gfx_still_graphics_still_and_the_qa_sheet_use_it_and_keep_no_copy() -> None:
    from kcut.commands import graphics_capture
    from kcut.gfx import still
    from kcut.qa import contact_gfx

    for name in ("compose", "decode_layer", "png_bytes", "transparent_png"):
        assert getattr(graphics_capture, name) is getattr(still, name), name
    assert contact_gfx.compose is still.compose and contact_gfx.decode_layer is still.decode_layer
    assert graphics_capture.STILLS_WORK is still.STILLS_WORK is contact_gfx.STILLS_WORK
    assert not hasattr(graphics_capture, "_png") and not hasattr(graphics_capture, "_transparent")


def test_gfx_still_the_transparent_png_has_alpha_0_everywhere_and_the_size_of_the_video() -> None:
    again = decode_layer(transparent_png(SIZE), SIZE)
    assert again.shape == (24, 40, 4) and int(again[:, :, 3].max()) == 0
