"""Frame/millisecond arithmetic: integers only, exact at the boundaries (spec 0.6)."""

import pytest

from kcut.errors import ProjectError
from kcut.timebase import (
    ALLOWED_FPS,
    f_to_ms_round,
    fmt_s,
    fmt_tc,
    ms_to_f_ceil,
    ms_to_f_floor,
    ms_to_f_round,
    rdiv,
    spf,
)


def test_allowed_fps_set() -> None:
    assert frozenset({24, 25, 30, 48, 50, 60}) == ALLOWED_FPS


@pytest.mark.parametrize(
    ("fps", "samples"), [(24, 2000), (25, 1920), (30, 1600), (48, 1000), (50, 960), (60, 800)]
)
def test_samples_per_frame_are_integers(fps: int, samples: int) -> None:
    assert spf(fps) == samples
    assert spf(fps) * fps == 48000


@pytest.mark.parametrize("fps", [0, 23, 29, 31, 120, -30])
def test_other_fps_is_a_project_error(fps: int) -> None:
    with pytest.raises(ProjectError) as info:
        spf(fps)
    assert info.value.exit_code == 3


@pytest.mark.parametrize(
    ("x", "d", "expected"),
    [(1, 2, 1), (3, 2, 2), (5, 2, 3), (1, 3, 0), (2, 3, 1), (0, 7, 0), (-1, 2, 0), (-3, 2, -1)],
)
def test_rdiv_rounds_halves_up(x: int, d: int, expected: int) -> None:
    assert rdiv(x, d) == expected == (2 * x + d) // (2 * d)


def test_rdiv_rejects_non_positive_divisor() -> None:
    with pytest.raises(ValueError):
        rdiv(1, 0)


def test_floor_ceil_round_at_the_frame_boundary_30fps() -> None:
    # one frame at 30 fps = 33.33 ms: 33 ms is just under it, 34 ms just over
    assert (ms_to_f_floor(33, 30), ms_to_f_ceil(33, 30), ms_to_f_round(33, 30)) == (0, 1, 1)
    assert (ms_to_f_floor(34, 30), ms_to_f_ceil(34, 30), ms_to_f_round(34, 30)) == (1, 2, 1)
    assert (ms_to_f_floor(1000, 30), ms_to_f_ceil(1000, 30), ms_to_f_round(1000, 30)) == (30,) * 3


def test_round_ms_to_frame_halves_go_up() -> None:
    # 25 fps: 20 ms is exactly half a frame (40 ms per frame) -> rounds up
    assert ms_to_f_round(20, 25) == 1
    assert ms_to_f_round(19, 25) == 0
    assert ms_to_f_round(60, 25) == 2  # 1.5 frames


def test_frames_to_ms_roundtrip_is_stable_for_every_fps() -> None:
    for fps in ALLOWED_FPS:
        for frame in (0, 1, 7, 90, 144, 3936):
            assert ms_to_f_round(f_to_ms_round(frame, fps), fps) == frame


def test_a_real_clip_duration_gives_the_documented_frame_count() -> None:
    assert ms_to_f_floor(131233, 30) == 3936


def test_negative_milliseconds_use_integer_arithmetic() -> None:
    assert ms_to_f_floor(-1, 30) == -1
    assert ms_to_f_ceil(-1, 30) == 0
    assert ms_to_f_round(-15, 30) == 0
    assert ms_to_f_round(-17, 30) == -1
    assert ms_to_f_round(-1200, 30) == -36


@pytest.mark.parametrize(
    ("frame", "fps", "tc", "seconds"),
    [
        (0, 30, "00:00.0", "0.00"),
        (100, 30, "00:03.3", "3.33"),
        (1800, 30, "01:00.0", "60.00"),
        (1799, 30, "01:00.0", "59.97"),
        (45, 24, "00:01.9", "1.88"),
        (-30, 30, "-00:01.0", "-1.00"),
    ],
)
def test_formatters(frame: int, fps: int, tc: str, seconds: str) -> None:
    assert fmt_tc(frame, fps) == tc
    assert fmt_s(frame, fps) == seconds
