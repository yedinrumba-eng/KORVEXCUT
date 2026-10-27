"""The page of the graphics is a function of the time (spec S1.6b row 2): the same frame gives the
same picture however the others were visited. Frame 50, then 200, then 50 again, in one Chromium,
and the first and the last are the same pixels; and the capture makes the files it says it makes.
"""

from pathlib import Path

import numpy as np
import pytest

from kcut.gfx.capture import Shooter, capture, capture_stills
from tests.integration.capture_helpers import FPS, H, W, decode_png, sample_page

pytestmark = [pytest.mark.chromium, pytest.mark.slow]


def test_capture_determinism_frame_50_then_200_then_50_gives_the_same_pixels(
    tmp_path: Path,
) -> None:
    with Shooter(sample_page(), tmp_path, FPS, (W, H)) as shooter:
        first = decode_png(shooter.shoot(50))
        other = decode_png(shooter.shoot(200))
        again = decode_png(shooter.shoot(50))
    assert first.shape == (H, W, 4) and first.dtype == np.uint8
    assert np.array_equal(first, again)  # the page remembers nothing of frame 200
    assert not np.array_equal(first, other)  # and the two frames are really different pictures
    assert first[:, :, 3].max() > 0 and other[:, :, 3].max() > 0  # both have something drawn


def test_capture_determinism_a_second_chromium_gives_the_same_pixels_too(tmp_path: Path) -> None:
    with Shooter(sample_page(), tmp_path / "a", FPS, (W, H)) as one:
        a = decode_png(one.shoot(170))
    with Shooter(sample_page(), tmp_path / "b", FPS, (W, H)) as two:
        b = decode_png(two.shoot(170))
    assert np.array_equal(a, b)
    assert a[:, :, 3].max() > 0  # frame 170 has a subtitle


def test_capture_determinism_the_background_is_transparent_where_nothing_is_drawn(
    tmp_path: Path,
) -> None:
    with Shooter(sample_page(), tmp_path, FPS, (W, H)) as shooter:
        empty = decode_png(shooter.shoot(330))  # no cue and no subtitle at frame 330
    assert empty.shape == (H, W, 4) and int(empty[:, :, 3].max()) == 0


def test_capture_determinism_capture_keeps_only_the_frames_that_have_something(
    tmp_path: Path,
) -> None:
    out = tmp_path / "gfx"
    kept = capture(sample_page(), tmp_path, [330, 50, 335, 200], FPS, (W, H), out, None)
    assert kept == [50, 200]  # in the order asked for; 330 and 335 are empty
    assert sorted(p.name for p in out.glob("*.png")) == ["000050.png", "000200.png"]
    assert (tmp_path / "page.html").is_file()
    assert decode_png(out / "000050.png").shape == (H, W, 4)


def test_capture_determinism_capture_stills_keeps_the_empty_ones_too(tmp_path: Path) -> None:
    out = tmp_path / "stills"
    found = capture_stills(sample_page(), tmp_path, [330, 50], FPS, (W, H), out, None)
    assert sorted(found) == [50, 330]
    assert sorted(p.name for p in out.glob("*.png")) == ["000050.png", "000330.png"]
    assert int(decode_png(found[330])[:, :, 3].max()) == 0
    assert int(decode_png(found[50])[:, :, 3].max()) > 0
