"""`blackdetect` and `freezedetect` (spec S1.9a, row 1; 001.15 T3): the parsers of what they print
at the `info` level, and which intervals are expected. The texts are what ffmpeg 8.1.1 printed (a
video of 5 s at 30 fps; the last two are intervals that run to the end of the video).

The rules of the spec: a black interval is expected if 80 % or more of its frames are in a `color`
span with luma at most 0.12 (`0.2126 R + 0.7152 G + 0.0722 B`, normalized) or in a fade zone; a
frozen one if 80 % or more are in a `color`, `screen` or `broll` span. A freeze inside a `cam` is
the one that fails.
"""

from pathlib import Path
from typing import Any

import pytest

from kcut.qa.detect import (
    Classified,
    black_args,
    check_detect,
    classify_intervals,
    freeze_args,
    parse_black,
    parse_freeze,
)
from tests.unit.edl_fakes import edit, parsed

NOISE = """\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'salida/v1.mp4':
  Metadata:
    major_brand     : isom
    encoder         : Lavf62.12.100
  Duration: 00:00:05.00, start: 0.000000, bitrate: 98 kb/s
  Stream #0:0[0x1](und): Video: h264 (High), yuv420p(tv, bt709), 216x384, 30 fps
Stream mapping:
  Stream #0:0 (h264) -> blackdetect:default (graph 0)
Output #0, null, to 'pipe:':
"""
BLACK = (
    NOISE + "[Parsed_blackdetect_0 @ 000001e3c0aaa840] black_start:0 black_end:1 black_duration:1\n"
)
BLACK_TWO = BLACK + (
    "[Parsed_blackdetect_0 @ 000001e3c0aaa840] black_start:2 black_end:2.966667 "
    "black_duration:0.966667\n"
)
FREEZE = NOISE + (
    "[Parsed_freezedetect_0 @ 0000029e5e4819c0] lavfi.freezedetect.freeze_start: 0\n"
    "[Parsed_freezedetect_0 @ 0000029e5e4819c0] lavfi.freezedetect.freeze_duration: 1\n"
    "[Parsed_freezedetect_0 @ 0000029e5e4819c0] lavfi.freezedetect.freeze_end: 1\n"
    "[Parsed_freezedetect_0 @ 0000029e5e4819c0] lavfi.freezedetect.freeze_start: 3.2\n"
    "[Parsed_freezedetect_0 @ 0000029e5e4819c0] lavfi.freezedetect.freeze_duration: 0.833333\n"
    "[Parsed_freezedetect_0 @ 0000029e5e4819c0] lavfi.freezedetect.freeze_end: 4.033333\n"
)
FREEZE_OPEN = (
    NOISE + "[Parsed_freezedetect_0 @ 000001fa667fe880] lavfi.freezedetect.freeze_start: 2\n"
)


def test_qa_detect_black_the_intervals_are_in_frames_of_the_video() -> None:
    assert parse_black(BLACK, 30) == [(0, 30)]
    assert parse_black(BLACK_TWO, 30) == [(0, 30), (60, 89)]


def test_qa_detect_black_the_time_is_rounded_to_the_nearest_frame_at_any_fps() -> None:
    line = "[Parsed_blackdetect_0 @ 0] black_start:0.4 black_end:0.52 black_duration:0.12\n"
    assert parse_black(line, 25) == [(10, 13)]
    assert parse_black(line, 60) == [(24, 31)]


def test_qa_detect_black_nothing_to_read_is_no_interval() -> None:
    assert parse_black(NOISE, 30) == []
    assert parse_black("", 30) == []


@pytest.mark.parametrize(
    "line",
    [
        "black_start:abc black_end:1 black_duration:1",
        "black_start:inf black_end:nan black_duration:1",
        "black_start:1 black_end: black_duration:1",
        "black_start:1e999 black_end:2 black_duration:1",
    ],
)
def test_qa_detect_black_a_line_that_is_not_numbers_is_ignored(line: str) -> None:
    assert parse_black(f"[Parsed_blackdetect_0 @ 0] {line}\n", 30) == []


def test_qa_detect_freeze_the_start_and_the_end_make_an_interval() -> None:
    assert parse_freeze(FREEZE, 30) == [(0, 30), (96, 121)]


def test_qa_detect_freeze_one_that_never_closes_runs_to_the_end_of_the_video() -> None:
    assert parse_freeze(FREEZE_OPEN, 30, total_f=150) == [(60, 150)]
    assert parse_freeze(FREEZE + FREEZE_OPEN, 30, total_f=150) == [(0, 30), (96, 121), (60, 150)]


def test_qa_detect_freeze_one_that_never_closes_without_a_total_is_left_out() -> None:
    assert parse_freeze(FREEZE_OPEN, 30) == []


def test_qa_detect_freeze_an_end_without_a_start_is_ignored() -> None:
    text = "[Parsed_freezedetect_0 @ 0] lavfi.freezedetect.freeze_end: 3\n"
    assert parse_freeze(text, 30) == []


def test_qa_detect_freeze_nothing_to_read_is_no_interval() -> None:
    assert parse_freeze(NOISE, 30) == []


@pytest.mark.parametrize("builder", [black_args, freeze_args])
def test_qa_detect_the_commands_are_the_ones_of_the_spec(builder: Any, tmp_path: Path) -> None:
    args = builder(Path("C:/bin/ffmpeg.exe"), tmp_path / "v1.mp4")
    assert args[1:4] == ["-hide_banner", "-nostdin", "-nostats"]  # level info, no -loglevel error
    assert "-loglevel" not in args
    assert args[4:6] == ["-i", str(tmp_path / "v1.mp4")]
    assert args[6:9] == ["-map", "0:v:0", "-an"]
    assert args[9] == "-vf" and args[-3:] == ["-f", "null", "-"]


def test_qa_detect_the_filters_have_the_thresholds_of_the_spec(tmp_path: Path) -> None:
    video = tmp_path / "v1.mp4"
    assert black_args(Path("C:/b/ffmpeg.exe"), video)[10] == "blackdetect=d=0.15:pix_th=0.06"
    assert freeze_args(Path("C:/b/ffmpeg.exe"), video)[10] == "freezedetect=n=0.002:d=0.6"


def _classified(kind: Any, intervals: list[tuple[int, int]], doc: Any = None) -> list[bool]:
    return [item.expected for item in classify_intervals(intervals, parsed(doc), kind)]


def _colored(color: str) -> Any:
    """The example EDL with the first color span (frames 0 to 29) painted `color`."""
    return edit(lambda d: d["spans"][0].update(color=color))


def _replaced(index: int, span: dict[str, Any]) -> Any:
    """The example EDL with the span `index` swapped for `span`."""
    return edit(lambda d: d["spans"].__setitem__(index, span))


def test_qa_detect_classify_black_in_a_dark_color_span_is_expected() -> None:
    """The example EDL starts with a color span `#0B0B0E` of 30 frames, and ends with another
    one of 30 frames (315 to 344) that fades out."""
    assert _classified("black", [(0, 30)]) == [True]
    assert _classified("black", [(315, 345)]) == [True]


def test_qa_detect_classify_black_in_a_camera_is_not_expected() -> None:
    assert _classified("black", [(100, 130)]) == [False]


def test_qa_detect_classify_gives_back_the_interval_with_its_verdict() -> None:
    assert classify_intervals([(0, 30), (100, 130)], parsed(), "black") == [
        Classified(0, 30, True),
        Classified(100, 130, False),
    ]


@pytest.mark.parametrize(
    ("interval", "expected"),
    [((0, 35), True), ((0, 37), True), ((0, 38), False), ((20, 40), False), ((5, 30), True)],
)
def test_qa_detect_classify_the_rule_is_80_percent_of_the_frames(
    interval: tuple[int, int], expected: bool
) -> None:
    """The color span is frames 0 to 29: 30 of 37 is 81 %, 30 of 38 is 78.9 %."""
    assert _classified("black", [interval]) == [expected]


@pytest.mark.parametrize(
    ("color", "dark"),
    [("#000000", True), ("#0B0B0E", True), ("#1E1E1E", True), ("#1F1F1F", False)],
)
def test_qa_detect_classify_black_a_color_span_is_black_if_its_luma_is_at_most_0_12(
    color: str, dark: bool
) -> None:
    assert _classified("black", [(0, 30)], _colored(color)) == [dark]


@pytest.mark.parametrize("color", ["#FF0000", "#FFFFFF", "#00FF00"])
def test_qa_detect_classify_black_a_bright_color_span_is_not_black(color: str) -> None:
    assert _classified("black", [(0, 30)], _colored(color)) == [False]


def test_qa_detect_classify_black_the_luma_of_green_weighs_more_than_blue() -> None:
    """`#001A00` is 26/255 of green (luma 0.073 with the weights of bt709) and `#00001A` is 26/255
    of blue (0.0074): both are under 0.12; `#003000` is 48/255 of green (0.135): over it."""
    for color, dark in (("#001A00", True), ("#00001A", True), ("#003000", False)):
        assert _classified("black", [(0, 30)], _colored(color)) == [dark], color


def test_qa_detect_classify_black_a_fade_zone_of_any_span_is_expected() -> None:
    """A camera span that fades in for 6 frames is black at its first frames."""
    doc = edit(lambda d: d["spans"][1].update(fade_in_f=6))
    assert _classified("black", [(30, 36)], doc) == [True]
    assert _classified("black", [(30, 40)], doc) == [False]  # 6 of 10 is not enough
    out = edit(lambda d: d["spans"][2].update(fade_out_f=8))
    assert _classified("black", [(172, 180)], out) == [True]  # the last 8 frames of 90 to 179


def test_qa_detect_classify_black_a_fade_longer_than_its_span_stops_at_the_span() -> None:
    doc = edit(lambda d: d["spans"][3].update(fade_in_f=500))  # span 180 to 209
    assert _classified("black", [(180, 210)], doc) == [True]
    assert _classified("black", [(210, 240)], doc) == [False]  # the screen insert, not the fade


def test_qa_detect_classify_freeze_in_color_screen_and_broll_is_expected() -> None:
    assert _classified("freeze", [(0, 30)]) == [True]  # color
    assert _classified("freeze", [(210, 270)]) == [True]  # screen
    broll = _replaced(2, {"kind": "broll", "at_f": 90, "dur_f": 90, "src": "a2", "src_f": 0})
    assert _classified("freeze", [(90, 180)], broll) == [True]  # broll


def test_qa_detect_classify_freeze_in_a_camera_is_the_one_that_fails() -> None:
    assert _classified("freeze", [(30, 90)]) == [False]
    assert _classified("freeze", [(100, 150)]) == [False]
    assert _classified("freeze", [(270, 315)]) == [False]


def test_qa_detect_classify_freeze_a_color_span_that_is_not_dark_is_still_expected() -> None:
    assert _classified("freeze", [(0, 30)], _colored("#FFFFFF")) == [True]


def test_qa_detect_classify_an_interval_past_the_end_is_cut_at_the_video() -> None:
    assert _classified("black", [(320, 9999)]) == [True]  # 25 of the 25 frames that exist
    assert _classified("black", [(400, 500)]) == [False]  # nothing of it is in the video


def test_qa_detect_classify_an_empty_interval_counts_as_one_frame() -> None:
    assert _classified("black", [(10, 10)]) == [True]
    assert _classified("black", [(100, 100)]) == [False]


def test_qa_detect_check_all_expected_passes_with_the_fields_of_the_spec() -> None:
    check = check_detect("black", [(0, 30)], parsed())
    assert check.to_json() == {
        "id": "black",
        "status": "pass",
        "intervals": [{"start_f": 0, "end_f": 30, "expected": True}],
    }


def test_qa_detect_check_no_interval_passes_with_an_empty_list() -> None:
    check = check_detect("freeze", [], parsed())
    assert check.status == "pass" and check.data == {"intervals": []}


def test_qa_detect_check_one_that_is_not_expected_fails_the_check() -> None:
    check = check_detect("freeze", [(0, 30), (100, 150)], parsed())
    assert check.id == "freeze" and check.status == "fail"
    assert check.data["intervals"] == [
        {"start_f": 0, "end_f": 30, "expected": True},
        {"start_f": 100, "end_f": 150, "expected": False},
    ]
