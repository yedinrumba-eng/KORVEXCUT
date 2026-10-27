"""The picture of one frame (spec S1.5b row 10, `render/frame_fx.py` and `render/screen_card.py`).

The output is 108x192 (9:16) so each case runs in milliseconds. The cases are numbers: how big a
white square gets when the zoom or the push says so, what a fade does to a white frame, which
pixels of a screen insert are the background.
"""

import cv2
import numpy as np
import pytest

from kcut.config.model import BrandSection
from kcut.edl.model import ColorSpan, Span
from kcut.render.frame_fx import look_for, span_frame
from kcut.render.looks import look_chain
from kcut.render.screen_card import bgr_of
from tests.unit.card_aspect_cases import *  # noqa: F403  (001.25: 300-line rule)
from tests.unit.edl_fakes import edit, parsed
from tests.unit.frame_fx_fakes import (
    BRAND,
    H,
    W,
    _broll,
    _cam,
    _color,
    _ctx,
    _screen,
    _square_source,
    _white,
)
from tests.unit.frame_fx_screen_cases import *  # noqa: F403  (300-line rule)


class TestLookFor:
    def test_frame_fx_a_color_span_has_no_look_even_if_it_says_one(self) -> None:
        edl = parsed(edit(lambda d: d.update(look="calido")))
        assert look_for(edl, _color(look="frio"), BRAND) == ""
        assert look_for(edl, _color(), BRAND) == ""

    def test_frame_fx_the_look_of_the_span_wins_over_the_one_of_the_edl(self) -> None:
        edl = parsed(edit(lambda d: d.update(look="calido")))
        assert look_for(edl, _cam(look="frio"), BRAND) == look_chain("frio", BRAND)
        assert look_for(edl, _broll(look="contraste"), BRAND) == look_chain("contraste", BRAND)

    def test_frame_fx_without_a_look_the_span_takes_the_global_one(self) -> None:
        edl = parsed(edit(lambda d: d.update(look="calido")))
        assert look_for(edl, _cam(), BRAND) == look_chain("calido", BRAND) != ""
        assert look_for(parsed(), _cam(), BRAND) == ""  # the example is `neutro`

    def test_frame_fx_a_screen_insert_gives_its_look_to_the_source_of_the_card(self) -> None:
        edl = parsed()
        assert look_for(edl, _screen(look="cinematico"), BRAND) == look_chain("cinematico", BRAND)

    def test_frame_fx_the_accent_look_takes_the_color_of_the_brand(self) -> None:
        chain = look_for(parsed(), _cam(look="bn-acento"), BRAND)
        assert "color=0xE5FF1F" in chain and "RRGGBB" not in chain
        other = BrandSection("#ff0000", "#2FA8FF", "#0B0B0E", "#FFFFFF")
        assert "color=0xFF0000" in look_for(parsed(), _cam(look="bn-acento"), other)


class TestShapes:
    @pytest.mark.parametrize(
        "span", [_cam(), _broll(), _color(), _screen()], ids=["cam", "broll", "color", "screen"]
    )
    def test_frame_fx_every_kind_gives_a_frame_of_the_output_size(self, span: Span) -> None:
        src = None if isinstance(span, ColorSpan) else _square_source()
        frame = span_frame(src, span, 0, _ctx())
        assert frame.shape == (H, W, 3) and frame.dtype == np.uint8

    def test_frame_fx_a_source_that_is_needed_and_is_not_given_is_a_bug_of_the_caller(self) -> None:
        with pytest.raises(ValueError, match="needs its frame"):
            span_frame(None, _cam(), 0, _ctx())

    def test_frame_fx_the_source_may_have_any_size(self) -> None:
        for size in ((108, 192), (216, 384), (432, 768), (500, 500), (1000, 300)):
            src = np.full((size[1], size[0], 3), 90, np.uint8)
            assert span_frame(src, _cam(zoom=1.5), 3, _ctx()).shape == (H, W, 3)


class TestCamera:
    def test_frame_fx_zoom_1_shows_the_whole_picture(self) -> None:
        frame = span_frame(_square_source(), _cam(zoom=1.0), 0, _ctx())
        assert _white(frame) == pytest.approx(27 * 27, rel=0.05)  # 54 px at half the size

    def test_frame_fx_zoom_2_makes_the_square_four_times_bigger(self) -> None:
        frame = span_frame(_square_source(), _cam(zoom=2.0), 0, _ctx())
        assert _white(frame) == pytest.approx(54 * 54, rel=0.05)

    def test_frame_fx_the_push_zooms_from_zoom_to_zoom_times_one_plus_push_over_the_span(
        self,
    ) -> None:
        span, ctx, src = _cam(n=11, zoom=2.0, push=0.5), _ctx(), _square_source()
        first = _white(span_frame(src, span, 0, ctx))
        last = _white(span_frame(src, span, 10, ctx))
        assert first == pytest.approx(54 * 54, rel=0.05)  # zoom 2.0
        assert last == pytest.approx(81 * 81, rel=0.05)  # zoom 3.0 at the end: 1.5 times a side
        middle = _white(span_frame(src, span, 5, ctx))  # zoom 2.5
        assert middle == pytest.approx(67.5 * 67.5, rel=0.06)

    def test_frame_fx_a_span_of_one_frame_does_not_divide_by_zero(self) -> None:
        frame = span_frame(_square_source(), _cam(n=1, zoom=2.0, push=0.5), 0, _ctx())
        assert _white(frame) == pytest.approx(54 * 54, rel=0.05)

    def test_frame_fx_cx_slides_the_cut_sideways_and_stays_inside_the_picture(self) -> None:
        corner = _square_source(side=30, at=(0, 177))  # the white square sits at the left edge
        left = span_frame(corner, _cam(zoom=2.0, cx=0.0), 0, _ctx())
        right = span_frame(corner, _cam(zoom=2.0, cx=1.0), 0, _ctx())
        assert _white(left) > 0 and _white(right) == 0
        centered = span_frame(corner, _cam(zoom=2.0, cx=0.5), 0, _ctx())
        assert _white(centered) == 0  # at 0.5 the cut starts at x = 54: the square is out

    def test_frame_fx_the_anchor_top_keeps_the_head_and_bottom_keeps_the_feet(self) -> None:
        head = _square_source(side=30, at=(93, 0))  # at the top of the picture
        feet = _square_source(side=30, at=(93, 354))
        top = _cam(zoom=2.0, anchor="top")
        bottom = _cam(zoom=2.0, anchor="bottom")
        assert _white(span_frame(head, top, 0, _ctx())) > 0
        assert _white(span_frame(head, bottom, 0, _ctx())) == 0
        assert _white(span_frame(feet, bottom, 0, _ctx())) > 0
        assert _white(span_frame(feet, top, 0, _ctx())) == 0

    def test_frame_fx_the_same_framing_from_the_proxy_or_from_the_mezzanine(self) -> None:
        """A smooth picture at two sizes: the frame is the same one (mean difference under 3)."""
        yy, xx = np.mgrid[0:768, 0:432].astype(np.float32)
        big = (
            np.stack(
                [90 + 80 * np.sin(xx / 70), 110 + 90 * np.cos(yy / 90), 60 + 0.1 * (xx + yy)],
                axis=-1,
            )
            .clip(0, 255)
            .astype(np.uint8)
        )
        small = cv2.resize(big, (216, 384), interpolation=cv2.INTER_AREA)
        span = _cam(zoom=1.6, cx=0.4, push=0.2)
        for i in (0, 5, 10):
            a = span_frame(big, span, i, _ctx()).astype(np.float32)
            b = span_frame(small, span, i, _ctx()).astype(np.float32)
            assert float(np.abs(a - b).mean()) < 3.0, i


class TestBroll:
    def test_frame_fx_broll_zooms_from_1_to_1_plus_push(self) -> None:
        span, ctx, src = _broll(n=11, push=0.5), _ctx(), _square_source()
        first = _white(span_frame(src, span, 0, ctx))
        last = _white(span_frame(src, span, 10, ctx))
        assert first == pytest.approx(27 * 27, rel=0.05)
        assert last == pytest.approx(27 * 27 * 1.5**2, rel=0.06)

    def test_frame_fx_dim_multiplies_the_picture(self) -> None:
        src = np.full((384, 216, 3), 200, np.uint8)
        frame = span_frame(src, _broll(push=0.0, dim=0.5), 0, _ctx())
        assert np.unique(frame).tolist() == [100]
        assert np.unique(span_frame(src, _broll(push=0.0, dim=1.5), 0, _ctx())).tolist() == [255]

    def test_frame_fx_without_dim_or_sharpen_the_picture_is_not_touched(self) -> None:
        src = np.full((384, 216, 3), 77, np.uint8)
        assert np.unique(span_frame(src, _broll(push=0.0), 0, _ctx())).tolist() == [77]

    def test_frame_fx_sharpen_adds_overshoot_next_to_an_edge_and_leaves_a_flat_area_alone(
        self,
    ) -> None:
        src = np.zeros((384, 216, 3), np.uint8)
        src[:, :108] = 80
        src[:, 108:] = 160
        plain = span_frame(src, _broll(push=0.0), 0, _ctx())
        sharp = span_frame(src, _broll(push=0.0, sharpen=0.5), 0, _ctx())
        row = sharp[96, :, 0].astype(int)
        assert row[0] == 80 and row[-1] == 160  # far from the edge: as it was
        assert row[W // 2 - 4 : W // 2].min() < 80 and row[W // 2 : W // 2 + 4].max() > 160
        assert np.array_equal(plain[96, :3], sharp[96, :3])

    def test_frame_fx_sharpen_then_dim_and_the_result_stays_between_0_and_255(self) -> None:
        src = np.zeros((384, 216, 3), np.uint8)
        src[:, 108:] = 250
        frame = span_frame(src, _broll(push=0.0, sharpen=1.0, dim=1.5), 0, _ctx())
        assert frame.min() == 0 and frame.max() == 255


class TestColorAndFades:
    def test_frame_fx_a_color_span_is_one_color_in_bgr(self) -> None:
        frame = span_frame(None, _color(color="#0B0B0E"), 3, _ctx())
        assert frame.shape == (H, W, 3) and np.unique(frame.reshape(-1, 3), axis=0).tolist() == [
            [14, 11, 11]
        ]
        assert bgr_of("#112233") == (0x33, 0x22, 0x11)

    @pytest.mark.parametrize("i", [0, 1, 2, 3, 4, 5])
    def test_frame_fx_fade_in_is_i_plus_1_over_fade_in_f_plus_1(self, i: int) -> None:
        frame = span_frame(None, _color(color="#FFFFFF", fade_in_f=4), i, _ctx())
        want = round(255 * (i + 1) / 5) if i < 4 else 255
        assert np.unique(frame).tolist() == [want]

    @pytest.mark.parametrize("i", [19, 20, 24, 28, 29])
    def test_frame_fx_fade_out_is_n_minus_i_over_fade_out_f_plus_1(self, i: int) -> None:
        frame = span_frame(None, _color(color="#FFFFFF", fade_out_f=10), i, _ctx())
        want = round(255 * (30 - i) / 11) if i >= 20 else 255
        assert np.unique(frame).tolist() == [want]

    def test_frame_fx_the_example_fade_out_of_the_last_span(self) -> None:
        last = _color(color="#0B0B0E", fade_out_f=10)
        assert span_frame(None, last, 29, _ctx())[0, 0].tolist() == [1, 1, 1]
        assert span_frame(None, last, 19, _ctx())[0, 0].tolist() == [14, 11, 11]

    def test_frame_fx_a_fade_goes_over_every_kind_of_span(self) -> None:
        src = np.full((384, 216, 3), 200, np.uint8)
        frame = span_frame(src, _cam(n=10, fade_in_f=1), 0, _ctx())
        assert np.unique(frame).tolist() == [100]  # (0 + 1) / (1 + 1)
        frame = span_frame(src, _broll(n=10, push=0.0, fade_out_f=1), 9, _ctx())
        assert np.unique(frame).tolist() == [100]  # (10 - 9) / (1 + 1)

    def test_frame_fx_both_fades_can_touch_the_same_frame_of_a_short_span(self) -> None:
        frame = span_frame(None, _color(n=2, color="#FFFFFF", fade_in_f=1, fade_out_f=1), 0, _ctx())
        assert np.unique(frame).tolist() == [round(255 * (1 / 2) * (2 / 2))]
