"""The screen insert in `span_frame` (spec S1.5b row 10): the background, the card and its look.

Collected from `test_frame_fx.py`, which is at the 300-line limit.
"""

import numpy as np

from kcut.edl.model import ScreenKey, ScreenSpan
from kcut.render.frame_fx import span_frame
from kcut.render.screen_card import bgr_of
from tests.unit.frame_fx_fakes import H, W, _ctx, _screen, _square_source

__all__ = ["TestScreen"]


class TestScreen:
    def test_frame_fx_the_first_frame_is_the_background_and_nothing_else(self) -> None:
        ctx = _ctx()
        frame = span_frame(_square_source(), _screen(), 0, ctx)
        assert np.array_equal(frame, ctx.bg)  # alpha 0: no card, no border, no shadow

    def test_frame_fx_the_pixels_of_the_background_are_exactly_the_background(self) -> None:
        """Far from the card and its shadow (a small card in a big frame) nothing is touched; near
        it, the shadow does darken the background."""
        ctx = _ctx(216, 384)
        keys = (ScreenKey(0, (0.5, 0.5, 1.0), (40, 40)),)
        span = ScreenSpan(at_f=0, dur_f=60, src="b1", src_f=0, keys=keys)
        src = np.full((384, 216, 3), 220, np.uint8)
        for i in (5, 10, 20, 40, 59):
            frame = span_frame(src, span, i, ctx)
            for y, x in ((0, 0), (0, 215), (383, 0), (383, 215), (2, 100), (381, 100)):
                assert frame[y, x].tolist() == ctx.bg[y, x].tolist(), (i, y, x)
        near = span_frame(src, span, 40, ctx)
        assert near[210, 108].tolist() != ctx.bg[210, 108].tolist()  # under the shadow

    def test_frame_fx_a_card_that_has_come_in_shows_the_source_in_the_middle(self) -> None:
        src = np.full((384, 216, 3), (30, 140, 220), np.uint8)
        frame = span_frame(src, _screen(), 15, _ctx())
        assert frame[int(H * 0.47), W // 2].tolist() == [30, 140, 220]
        assert not np.array_equal(frame, _ctx().bg)

    def test_frame_fx_the_card_has_an_accent_border_just_outside_the_picture(self) -> None:
        src = np.full((384, 216, 3), 0, np.uint8)
        frame = span_frame(src, _screen(), 40, _ctx())  # the second key: a 60x80 card
        card = int(H * 0.47)
        row = frame[card, :, :].astype(int)
        accent = np.array(bgr_of("#E5FF1F"))
        borders = np.flatnonzero(np.all(np.abs(row - accent) <= 2, axis=1))
        assert borders.size >= 2 and borders.min() < W // 2 < borders.max()

    def test_frame_fx_the_card_follows_card_y(self) -> None:
        src = np.full((384, 216, 3), 255, np.uint8)
        low = span_frame(src, _screen(card_y=0.8), 40, _ctx())
        high = span_frame(src, _screen(card_y=0.2), 40, _ctx())
        assert low[int(H * 0.8), W // 2].tolist() == [255, 255, 255]
        assert high[int(H * 0.2), W // 2].tolist() == [255, 255, 255]
        assert low[int(H * 0.2), W // 2].tolist() != [255, 255, 255]

    def test_frame_fx_the_source_is_what_the_look_made_of_it_and_the_background_is_not(
        self,
    ) -> None:
        """The look goes in the reader, so the card shows the source as it came. The background
        of the frame is the same with or without a look on the span."""
        ctx = _ctx()
        src = np.full((384, 216, 3), 150, np.uint8)
        with_look = span_frame(src, _screen(look="calido"), 0, ctx)
        without = span_frame(src, _screen(), 0, ctx)
        assert np.array_equal(with_look, without) and np.array_equal(without, ctx.bg)

    def test_frame_fx_a_crop_that_leaves_the_picture_is_filled_with_the_dark_color(self) -> None:
        wide = np.full((100, 400, 3), 255, np.uint8)  # a wide recording; the card is tall
        keys = (ScreenKey(0, (0.5, 0.5, 0.3), (60, 120)),)
        span = ScreenSpan(at_f=0, dur_f=60, src="b1", src_f=0, keys=keys)
        frame = span_frame(wide, span, 30, _ctx())
        card_x, top, bottom = W // 2, int(H * 0.47) - 55, int(H * 0.47) + 55
        assert frame[int(H * 0.47), card_x].tolist() == [255, 255, 255]  # inside the picture
        assert frame[top, card_x].tolist() == [14, 11, 11]  # above it: `dark`
        assert frame[bottom, card_x].tolist() == [14, 11, 11]

    def test_frame_fx_a_card_that_is_bigger_than_the_frame_is_cut_and_does_not_crash(self) -> None:
        keys = (ScreenKey(0, (0.5, 0.5, 1.0), (W + 40, H + 40)),)
        span = ScreenSpan(at_f=0, dur_f=60, src="b1", src_f=0, keys=keys)
        src = np.full((384, 216, 3), 99, np.uint8)
        for i in (1, 5, 20, 59):
            assert span_frame(src, span, i, _ctx()).shape == (H, W, 3)
