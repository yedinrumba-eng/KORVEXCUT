"""Windows of gain (spec S1.8a row 2, 001.15): `apply_gain_windows` raises or lowers a stretch of a
track by `gain_db`, with a linear ramp of 10 ms inside each edge, and leaves everything outside the
windows exactly as it was (gain 1)."""

import numpy as np
import pytest

from kcut.audio.gain import apply_gain_windows

SR = 48000
SPF = 1600  # 30 fps
RAMP = 480  # 10 ms at 48 kHz
SIX_DB = 20 * np.log10(2.0)  # a factor of exactly 2


def _track(frames: int = 20) -> np.ndarray:
    return np.linspace(-0.5, 0.5, frames * SPF, dtype=np.float32) + np.float32(0.25)


def test_gain_the_middle_of_a_window_is_the_factor_of_its_db() -> None:
    x = _track()
    out = apply_gain_windows(x, [(5, 12, SIX_DB)], SPF, SR)
    first, last = 5 * SPF, 12 * SPF
    middle = slice(first + RAMP, last - RAMP)
    assert np.allclose(out[middle], x[middle] * 2.0, rtol=1e-6, atol=1e-7)
    low = apply_gain_windows(x, [(5, 12, -SIX_DB)], SPF, SR)
    assert np.allclose(low[middle], x[middle] * 0.5, rtol=1e-6, atol=1e-7)


def test_gain_outside_every_window_the_gain_is_exactly_1() -> None:
    x = _track()
    out = apply_gain_windows(x, [(5, 12, 9.0), (15, 17, -9.0)], SPF, SR)
    outside = np.ones(len(x), dtype=bool)
    outside[5 * SPF : 12 * SPF] = False
    outside[15 * SPF : 17 * SPF] = False
    assert np.array_equal(out[outside], x[outside])  # not "close": the same bits
    assert not np.array_equal(out[~outside], x[~outside])


def test_gain_the_edges_have_a_linear_ramp_of_10_ms_inside_the_window() -> None:
    x = np.ones(20 * SPF, dtype=np.float32)
    out = apply_gain_windows(x, [(5, 12, SIX_DB)], SPF, SR)
    first, last = 5 * SPF, 12 * SPF
    assert out[first - 1] == 1.0 and out[last] == 1.0  # the samples just outside
    up, down = out[first : first + RAMP], out[last - RAMP : last]
    assert up[0] == 1.0 and np.all(np.diff(up) > 0)  # starts at 1 and climbs without a jump
    assert np.allclose(np.diff(up), np.diff(up)[0], rtol=1e-4)  # in a straight line
    assert np.all(np.diff(down) < 0) and down[0] == pytest.approx(2.0, rel=1e-6)
    assert np.allclose(np.diff(down), np.diff(down)[0], rtol=1e-4)
    assert out[first + RAMP] == pytest.approx(2.0, rel=1e-6)  # the plateau starts after the ramp
    assert out[last - RAMP - 1] == pytest.approx(2.0, rel=1e-6)
    assert float(out[first:last].max()) <= 2.0 + 1e-6  # the ramps never overshoot


def test_gain_the_input_is_not_changed_and_the_result_is_float32() -> None:
    x = _track()
    before = x.copy()
    out = apply_gain_windows(x, [(1, 3, 6.0)], SPF, SR)
    assert np.array_equal(x, before) and out.dtype == np.float32 and out is not x
    assert out.shape == x.shape


def test_gain_no_windows_is_a_copy_with_the_same_samples() -> None:
    x = _track()
    out = apply_gain_windows(x, [], SPF, SR)
    assert np.array_equal(out, x) and out is not x


def test_gain_a_window_shorter_than_two_ramps_has_shorter_ramps() -> None:
    """At 60 fps a frame is 800 samples: two ramps of 480 would not fit, each is cut to half."""
    x = np.ones(10 * 800, dtype=np.float32)
    out = apply_gain_windows(x, [(3, 4, SIX_DB)], 800, SR)
    window = out[3 * 800 : 4 * 800]
    assert window[0] == 1.0 and float(window.max()) <= 2.0 + 1e-6
    assert np.all(np.diff(window[:400]) > 0) and np.all(np.diff(window[400:]) < 0)
    assert out[4 * 800] == 1.0 and out[3 * 800 - 1] == 1.0


def test_gain_ramp_ms_is_a_parameter_and_zero_is_a_step() -> None:
    x = np.ones(10 * SPF, dtype=np.float32)
    step = apply_gain_windows(x, [(2, 4, SIX_DB)], SPF, SR, ramp_ms=0)
    assert step[2 * SPF - 1] == 1.0 and step[2 * SPF] == pytest.approx(2.0)
    assert step[4 * SPF - 1] == pytest.approx(2.0) and step[4 * SPF] == 1.0
    long = apply_gain_windows(x, [(2, 8, SIX_DB)], SPF, SR, ramp_ms=20)
    assert long[2 * SPF + 960] == pytest.approx(2.0, rel=1e-6)  # 20 ms: 960 samples
    assert long[2 * SPF + 959] < 2.0


def test_gain_a_window_that_goes_past_the_track_is_cut_where_the_track_ends() -> None:
    """The ramps are those of the whole window: the part that is left is not given a ramp down at
    the end of the track, because the window goes on past it."""
    x = np.ones(10 * SPF, dtype=np.float32)
    out = apply_gain_windows(x, [(8, 30, SIX_DB), (-5, 1, SIX_DB), (40, 50, 6.0)], SPF, SR)
    assert out.shape == x.shape
    assert out[-1] == pytest.approx(2.0, rel=1e-6)  # still the factor at the last sample
    assert out[8 * SPF] == 1.0 and out[8 * SPF + RAMP] == pytest.approx(2.0, rel=1e-6)
    assert out[0] == pytest.approx(2.0, rel=1e-6)  # the ramp up of the window was before 0
    assert 1.0 < out[SPF - 1] < 2.0 and out[SPF] == 1.0  # and the ramp down is in the track
    assert np.array_equal(out[2 * SPF : 8 * SPF], x[2 * SPF : 8 * SPF])  # nothing else changed


def test_gain_windows_that_overlap_multiply() -> None:
    x = np.ones(20 * SPF, dtype=np.float32)
    out = apply_gain_windows(x, [(2, 12, SIX_DB), (6, 10, SIX_DB)], SPF, SR)
    assert out[8 * SPF] == pytest.approx(4.0, rel=1e-6)  # both: 2 * 2
    assert out[4 * SPF] == pytest.approx(2.0, rel=1e-6)  # only the first


def test_gain_0_db_is_the_same_samples() -> None:
    x = _track()
    assert np.array_equal(apply_gain_windows(x, [(2, 9, 0.0)], SPF, SR), x)
