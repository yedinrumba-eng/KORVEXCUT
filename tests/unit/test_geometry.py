"""Crops, easings, the screen-card interpolation and the upscale factor (spec S1.5a)."""

import math

import pytest

from kcut.edl.model import ScreenKey
from kcut.render.geometry import (
    back_out,
    broll_crop,
    cam_crop,
    cover_box,
    ease_in_out_cubic,
    screen_state,
    upscale_factor,
)

W, H = 1080, 1920


class TestCoverBox:
    def test_geometry_a_source_with_the_aspect_of_the_output_is_the_whole_source(self) -> None:
        assert cover_box(1440, 2560, W, H) == (1440.0, 2560.0)

    def test_geometry_a_wider_source_is_limited_by_its_height(self) -> None:
        width, height = cover_box(1894, 866, W, H)
        assert height == 866.0 and width == pytest.approx(866 * 9 / 16)

    def test_geometry_a_taller_source_is_limited_by_its_width(self) -> None:
        width, height = cover_box(1000, 3000, W, H)
        assert width == 1000.0 and height == pytest.approx(1000 * 16 / 9)

    def test_geometry_the_other_preset(self) -> None:
        assert cover_box(3840, 2160, 1920, 1080) == (3840.0, 2160.0)
        width, height = cover_box(1080, 1920, 1920, 1080)  # a vertical clip for a horizontal video
        assert width == 1080.0 and height == pytest.approx(1080 * 9 / 16)


class TestCamCrop:
    def test_geometry_zoom_one_is_the_whole_cover_box(self) -> None:
        assert cam_crop(1440, 2560, W, H, 1.0, 0.5, 0.5, "center") == (0, 0, 1440, 2560)

    def test_geometry_the_size_is_the_box_over_the_zoom(self) -> None:
        x, y, w, h = cam_crop(1440, 2560, W, H, 2.0, 0.5, 0.5, "center")
        assert (w, h) == (720, 1280) and (x, y) == (360, 640)

    def test_geometry_x_follows_cx_and_stays_inside(self) -> None:
        assert cam_crop(1440, 2560, W, H, 2.0, 0.0, 0.5, "center")[0] == 0
        assert cam_crop(1440, 2560, W, H, 2.0, 1.0, 0.5, "center")[0] == 720  # sw - w
        assert cam_crop(1440, 2560, W, H, 2.0, 0.4, 0.5, "center")[0] == 216  # 576 - 720 / 2

    def test_geometry_the_anchor_sets_y(self) -> None:
        top = cam_crop(1440, 2560, W, H, 2.0, 0.5, 0.9, "top")
        bottom = cam_crop(1440, 2560, W, H, 2.0, 0.5, 0.1, "bottom")
        center = cam_crop(1440, 2560, W, H, 2.0, 0.5, 0.25, "center")
        assert top[1] == 0 and bottom[1] == 2560 - 1280 and center[1] == 0  # 640 - 640 = 0
        assert cam_crop(1440, 2560, W, H, 2.0, 0.5, 1.0, "center")[1] == 1280  # clamped to sh - h

    def test_geometry_a_crop_never_leaves_the_source(self) -> None:
        for zoom in (1.0, 1.37, 2.0, 3.0):
            for cx in (0.0, 0.3, 1.0):
                for anchor in ("top", "center", "bottom"):
                    x, y, w, h = cam_crop(1894, 866, W, H, zoom, cx, 0.5, anchor)
                    assert x >= 0 and x + w <= 1894 and y >= 0 and y + h <= 866

    def test_geometry_the_crop_keeps_the_aspect_of_the_output_up_to_rounding(self) -> None:
        _, _, w, h = cam_crop(1894, 866, W, H, 1.3, 0.5, 0.5, "center")
        assert abs(w / h - W / H) < 0.01

    def test_geometry_a_zoom_below_one_is_held_inside_the_source(self) -> None:
        assert cam_crop(1440, 2560, W, H, 0.5, 0.5, 0.5, "center") == (0, 0, 1440, 2560)


class TestBrollCrop:
    def test_geometry_broll_is_a_centered_cam_crop_with_the_push_as_zoom(self) -> None:
        assert broll_crop(1440, 2560, W, H, 1.2, 0.5, 0.5) == cam_crop(
            1440, 2560, W, H, 1.2, 0.5, 0.5, "center"
        )

    def test_geometry_broll_push_one_is_the_whole_box_and_more_push_is_a_smaller_box(self) -> None:
        assert broll_crop(1894, 866, W, H, 1.0, 0.5, 0.5)[2:] == (487, 866)
        assert broll_crop(1894, 866, W, H, 1.07, 0.5, 0.5)[2] < 487


class TestEasings:
    @pytest.mark.parametrize("ease", [ease_in_out_cubic, back_out])
    def test_geometry_easings_start_at_zero_and_end_at_one(self, ease: object) -> None:
        assert callable(ease)
        assert ease(0.0) == pytest.approx(0.0) and ease(1.0) == pytest.approx(1.0)
        assert ease(-3.0) == pytest.approx(0.0) and ease(7.0) == pytest.approx(
            1.0
        )  # held in [0, 1]

    def test_geometry_ease_in_out_cubic_values(self) -> None:
        assert ease_in_out_cubic(0.25) == pytest.approx(4 * 0.25**3)
        assert ease_in_out_cubic(0.5) == pytest.approx(0.5)
        assert ease_in_out_cubic(0.75) == pytest.approx(1 - 0.125 / 2 * 1)  # 1 - (-2*.75+2)^3 / 2

    def test_geometry_ease_in_out_cubic_is_symmetric_and_rising(self) -> None:
        samples = [ease_in_out_cubic(k / 20) for k in range(21)]
        assert samples == sorted(samples)
        for k in range(21):
            assert samples[k] + samples[20 - k] == pytest.approx(1.0)

    def test_geometry_back_out_overshoots_then_settles(self) -> None:
        samples = [back_out(k / 100) for k in range(101)]
        assert max(samples) > 1.05 and samples[-1] == pytest.approx(1.0)
        assert back_out(0.5) == pytest.approx(
            1 + 2.70158 * (-0.5) ** 3 + 1.70158 * (-0.5) ** 2
        )  # the formula of piloto/compose.py


class TestScreenState:
    KEYS = (
        ScreenKey(0, (0.5, 0.5, 1.0), (1040, 476)),
        ScreenKey(30, (0.7, 0.4, 0.3), (1000, 760)),
        ScreenKey(60, (0.2, 0.2, 0.2), (900, 900)),
    )

    def test_geometry_screen_state_at_a_key_is_that_key(self) -> None:
        assert screen_state(self.KEYS, 0) == ((0.5, 0.5, 1.0), (1040.0, 476.0))
        crop, card = screen_state(self.KEYS, 30)
        assert crop == pytest.approx((0.7, 0.4, 0.3)) and card == pytest.approx((1000.0, 760.0))

    def test_geometry_screen_state_between_keys_is_eased_not_linear(self) -> None:
        crop, card = screen_state(self.KEYS, 15)  # halfway: ease_in_out_cubic(0.5) = 0.5
        assert crop == pytest.approx((0.6, 0.45, 0.65)) and card == pytest.approx((1020.0, 618.0))
        crop, _ = screen_state(self.KEYS, 5)  # a sixth of the way: ease is 4 * (1/6)^3
        u = 4 * (5 / 30) ** 3
        assert crop[0] == pytest.approx(0.5 + 0.2 * u)

    def test_geometry_screen_state_after_the_last_key_stays_there(self) -> None:
        assert screen_state(self.KEYS, 60)[1] == (900.0, 900.0)
        assert screen_state(self.KEYS, 600)[1] == (900.0, 900.0)

    def test_geometry_screen_state_before_the_first_key_is_the_first(self) -> None:
        assert screen_state(self.KEYS, -5)[1] == (1040.0, 476.0)

    def test_geometry_screen_state_one_key_is_a_still(self) -> None:
        only = (ScreenKey(0, (0.4, 0.4, 0.4), (500, 600)),)
        assert screen_state(only, 0) == screen_state(only, 99) == ((0.4, 0.4, 0.4), (500.0, 600.0))

    def test_geometry_screen_state_the_second_segment_uses_its_own_keys(self) -> None:
        crop, _ = screen_state(self.KEYS, 45)
        assert crop == pytest.approx((0.45, 0.3, 0.25))

    def test_geometry_screen_state_values_are_finite_everywhere(self) -> None:
        for f in range(-5, 100):
            crop, card = screen_state(self.KEYS, f)
            assert all(math.isfinite(v) for v in (*crop, *card))


class TestUpscaleFactor:
    def test_geometry_upscale_factor_is_the_width_over_the_box_width(self) -> None:
        assert upscale_factor(1.0, 1440, 2560, W, H) == pytest.approx(0.75)
        assert upscale_factor(1.5, 1440, 2560, W, H) == pytest.approx(1.125)

    def test_geometry_upscale_factor_a_source_that_is_just_the_output_size(self) -> None:
        assert upscale_factor(1.0, 1080, 1920, W, H) == pytest.approx(1.0)
        assert upscale_factor(1.05, 1080, 1920, W, H) == pytest.approx(1.05)

    def test_geometry_upscale_factor_a_wide_screen_uses_its_height(self) -> None:
        assert upscale_factor(1.0, 1894, 866, W, H) == pytest.approx(1080 / (866 * 9 / 16))

    def test_geometry_upscale_factor_grows_with_the_zoom(self) -> None:
        values = [upscale_factor(z, 1440, 2560, W, H) for z in (1.0, 1.2, 1.5, 3.0)]
        assert values == sorted(values)
