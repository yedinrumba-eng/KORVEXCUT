"""The contact sheet, the pure part (spec S1.9a, row 5; 001.15): how many frames, which ones, how
they are labelled and how big each cell is. A frame every 2 s, so the frame `k` of the sheet is the
frame `2 * k * fps` of the video; `n = (frames + 2 * fps - 1) // (2 * fps)`.
"""

from itertools import pairwise

import pytest

from kcut.qa.contact import cell_size, contact_count, contact_frames, contact_label


@pytest.mark.parametrize(
    ("frames", "fps", "count"),
    [
        (345, 30, 6),  # the example: 0, 60, 120, 180, 240, 300
        (360, 30, 6),  # 12 s: the frame 360 does not exist
        (361, 30, 7),  # one frame past the sixth: the seventh is the frame 360
        (1, 30, 1),
        (60, 30, 1),
        (61, 30, 2),
        (1469, 30, 25),
        (100, 24, 3),
        (100, 60, 1),
        (121, 60, 2),
    ],
)
def test_qa_contact_count_is_one_frame_every_two_seconds_counting_the_one_at_zero(
    frames: int, fps: int, count: int
) -> None:
    assert contact_count(frames, fps) == count


def test_qa_contact_frames_of_the_example_are_0_60_120_180_240_300() -> None:
    assert contact_frames(345, 30) == [0, 60, 120, 180, 240, 300]


def test_qa_contact_frames_are_always_inside_the_video() -> None:
    for fps in (24, 25, 30, 48, 50, 60):
        for frames in (1, 2 * fps - 1, 2 * fps, 2 * fps + 1, 1000):
            found = contact_frames(frames, fps)
            assert found[0] == 0 and found[-1] < frames
            assert all(b - a == 2 * fps for a, b in pairwise(found))


@pytest.mark.parametrize(
    ("k", "fps", "label"),
    [
        (0, 30, "00:00.0 f0"),
        (1, 30, "00:02.0 f60"),
        (5, 30, "00:10.0 f300"),
        (17, 30, "00:34.0 f1020"),
        (30, 30, "01:00.0 f1800"),
        (1, 24, "00:02.0 f48"),
        (3, 60, "00:06.0 f360"),
    ],
)
def test_qa_contact_label_has_the_time_and_the_frame_of_the_video(
    k: int, fps: int, label: str
) -> None:
    assert contact_label(k, fps) == label


@pytest.mark.parametrize(("w", "h", "cell"), [(1080, 1920, (216, 384)), (1920, 1080, (384, 216))])
def test_qa_contact_cell_is_216_by_384_for_vertical_and_384_by_216_for_horizontal(
    w: int, h: int, cell: tuple[int, int]
) -> None:
    assert cell_size(w, h) == cell
