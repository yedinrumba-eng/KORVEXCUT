"""A thin card (spec S1.5b row 37, 001.25 point 6): its aspect ratio is at most 8 (E13), and what
`_crop_card` makes for it never grows past the output frame, whatever the card is.

Collected from `test_frame_fx.py`, which is at the 300-line limit.
"""

import tracemalloc

import cv2
import numpy as np
import pytest

from kcut.edl.fields import check_fields
from kcut.edl.model import ScreenKey, ScreenSpan
from kcut.render import screen_card
from kcut.render.frame_fx import span_frame
from kcut.render.screen_card import _crop_card
from tests.unit.frame_fx_fakes import Frame, _ctx

__all__ = ["TestCardAspect"]
FILL = (11, 11, 14)


def _span(card: tuple[int, int], crop: tuple[float, float, float] = (0.5, 0.5, 1.0)) -> ScreenSpan:
    keys = (ScreenKey(0, crop, card),)
    return ScreenSpan(at_f=0, dur_f=60, src="b1", src_f=0, keys=keys)


def _e13(card: tuple[int, int], out: tuple[int, int] = (1080, 1920)) -> list[str]:
    issues = check_fields(_span(card), "spans[0]", *out)
    return [i.path for i in issues if i.code == "E13"]


def _old_crop_card(
    src: Frame, cx: float, cy: float, cw: float, kw: int, kh: int, fill: tuple[int, ...]
) -> Frame:
    """`_crop_card` as it was before the limit on the fill: the reference where nothing is cut."""
    sh, sw = src.shape[:2]
    cw_px = cw * sw
    ch_px = cw_px * kh / kw
    x0 = min(max(cx * sw - cw_px / 2, 0), sw - cw_px)
    y0 = cy * sh - ch_px / 2
    pad = int(max(0, -y0, y0 + ch_px - sh)) + 2
    padded = cv2.copyMakeBorder(src, pad, pad, 0, 0, cv2.BORDER_CONSTANT, value=fill)
    left, top = int(x0), int(y0 + pad)
    crop = padded[top : max(top + 1, int(y0 + pad + ch_px)), left : max(left + 1, int(x0 + cw_px))]
    mode = cv2.INTER_AREA if cw_px > kw else cv2.INTER_CUBIC
    return np.asarray(cv2.resize(crop, (kw, kh), interpolation=mode))


def _picture(w: int = 1894, h: int = 866) -> Frame:
    """A source with a vertical gradient, so that a row of the card says which row of it it is."""
    rows = np.linspace(40, 215, h).astype(np.uint8)
    return np.repeat(rows[:, None, None], w, axis=1).repeat(3, axis=2)


class TestCardAspect:
    @pytest.mark.parametrize(
        "card", [(1064, 133), (133, 1064), (225, 1800), (800, 100), (500, 500)]
    )
    def test_card_aspect_up_to_8_to_1_passes_either_way_up(self, card: tuple[int, int]) -> None:
        assert _e13(card) == []

    @pytest.mark.parametrize("card", [(1064, 132), (132, 1064), (224, 1800), (800, 99), (2, 1000)])
    def test_card_aspect_more_than_8_to_1_is_e13_on_the_card_of_the_key(
        self, card: tuple[int, int]
    ) -> None:
        assert _e13(card) == ["spans[0].keys[0].card"]

    def test_card_aspect_the_message_says_the_size_and_the_limit(self) -> None:
        (issue,) = check_fields(_span((224, 1800)), "spans[0]", 1080, 1920)
        assert "224x1800" in issue.message_es and "8 veces" in issue.message_es

    def test_card_aspect_a_card_that_does_not_fit_is_one_finding_not_two(self) -> None:
        assert _e13((2000, 100)) == ["spans[0].keys[0].card"]

    def test_card_aspect_a_card_with_no_size_is_still_the_old_finding(self) -> None:
        issues = check_fields(_span((0, 100)), "spans[0]", 1080, 1920)
        assert [i.message_es for i in issues if i.code == "E13"] == [
            "la tarjeta tiene que medir 1 px o más"
        ]

    def test_card_aspect_the_fill_is_never_more_than_the_height_of_the_frame(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pads: list[int] = []
        real = cv2.copyMakeBorder

        def spy(src: Frame, top: int, bottom: int, *args: object, **kwargs: object) -> Frame:
            pads.append(top)
            return real(src, top, bottom, *args, **kwargs)  # type: ignore[no-any-return]

        monkeypatch.setattr(screen_card.cv2, "copyMakeBorder", spy)
        for kw, kh in ((225, 1800), (50, 1800), (2, 1800), (1064, 1800), (1064, 133)):
            card = _crop_card(_picture(), 0.5, 0.5, 1.0, kw, kh, FILL, 1920)
            assert card.shape == (kh, kw, 3)
        assert pads and max(pads) <= 1920

    def test_card_aspect_a_cut_fill_leaves_the_picture_in_its_place_and_fill_around_it(
        self,
    ) -> None:
        """225x1800: the card is 8 times as tall as the source is wide, so the picture is a band in
        the middle of it and the rest is the fill color."""
        card = _crop_card(_picture(), 0.5, 0.5, 1.0, 225, 1800, FILL, 1920)
        assert card[0, 100].tolist() == list(FILL) and card[1799, 100].tolist() == list(FILL)
        band = np.flatnonzero(np.any(card[:, 100] != np.array(FILL, np.uint8), axis=1))
        assert band.size and band.min() > 600 and band.max() < 1200  # 866 of 15152 rows
        assert abs((band.min() + band.max()) / 2 - 900) < 6
        assert (
            card[band.min() + 4, 100, 0] < card[band.max() - 4, 100, 0]
        )  # the gradient is upright

    @pytest.mark.parametrize(
        ("kw", "kh", "cw", "cy"),
        [(400, 600, 1.0, 0.5), (300, 900, 0.5, 0.3), (1000, 400, 0.6, 0.8), (120, 240, 0.2, 0.0)],
    )
    def test_card_aspect_where_nothing_is_cut_the_card_is_as_it_always_was(
        self, kw: int, kh: int, cw: float, cy: float
    ) -> None:
        src = _picture()
        now = _crop_card(src, 0.5, cy, cw, kw, kh, FILL, 1920)
        assert np.array_equal(now, _old_crop_card(src, 0.5, cy, cw, kw, kh, FILL))

    @pytest.mark.parametrize("card", [(1064, 1800), (225, 1800), (1064, 133)])
    def test_card_aspect_the_biggest_card_allowed_over_a_1894x866_mezzanine_stays_under_200_mb(
        self, card: tuple[int, int]
    ) -> None:
        ctx = _ctx(1080, 1920)
        span, src = _span(card), _picture()
        tracemalloc.start()
        try:
            frame = span_frame(src, span, 30, ctx)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert frame.shape == (1920, 1080, 3)
        assert peak < 200 * 1024 * 1024, f"pico de {peak / 2**20:.0f} MB"
