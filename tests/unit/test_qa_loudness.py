"""The `loudness` check (spec S1.9a, row 1; 001.15 T3): `|I - target| <= tolerance` and
`TP <= max_tp`, from the `Summary` that `ebur128=peak=true` printed. `I` that could not be measured
is a `fail` with a reason; a true peak that could not be measured (silence) counts as under the
ceiling. The texts of `ebur128` are what ffmpeg 8.1.1 printed.
"""

from pathlib import Path

import pytest

from kcut.audio.loudnorm import EburMeasure, parse_ebur128
from kcut.config.model import QaSection
from kcut.qa.loudness import check_loudness, measure_args
from kcut.qa.report import Check
from tests.unit.edl_fakes import config

QA = config().qa
SUMMARY = """\
[Parsed_ebur128_0 @ 00000193366e0f00] Summary:

  Integrated loudness:
    I:         {i} LUFS
    Threshold: -24.4 LUFS

  Loudness range:
    LRA:         4.1 LU
    Threshold: -34.4 LUFS
    LRA low:   -16.0 LUFS
    LRA high:  -11.9 LUFS

  True peak:
    Peak:      {tp} dBFS
[out#0/null @ 00000193366e0580] video:0KiB audio:940KiB subtitle:0KiB other streams:0KiB
"""


def _check(i: float | None, tp: float | None, qa: QaSection = QA, target: float = -14.0) -> Check:
    return check_loudness(EburMeasure(i, tp, 4.1), qa, target)


def test_qa_loudness_the_example_of_the_spec_passes_with_its_fields() -> None:
    check = _check(-14.2, -1.4)
    assert check.to_json() == {
        "id": "loudness",
        "status": "pass",
        "I_LUFS": -14.2,
        "TP_dBTP": -1.4,
        "LRA": 4.1,
        "target": -14.0,
        "tolerance": 1.0,
        "max_tp": -1.0,
    }


@pytest.mark.parametrize(
    ("i", "status"),
    [(-14.0, "pass"), (-13.0, "pass"), (-15.0, "pass"), (-12.9, "fail"), (-15.1, "fail")],
)
def test_qa_loudness_the_tolerance_is_a_closed_interval_around_the_target(
    i: float, status: str
) -> None:
    assert _check(i, -2.0).status == status


@pytest.mark.parametrize(
    ("tp", "status"),
    [(-1.0, "pass"), (-1.1, "pass"), (-20.0, "pass"), (-0.9, "fail"), (0.0, "fail"), (3.5, "fail")],
)
def test_qa_loudness_the_true_peak_is_under_the_ceiling_or_it_fails(tp: float, status: str) -> None:
    assert _check(-14.0, tp).status == status


def test_qa_loudness_no_true_peak_counts_as_under_the_ceiling() -> None:
    check = _check(-14.0, None)
    assert check.status == "pass" and check.data["TP_dBTP"] is None


def test_qa_loudness_no_integrated_loudness_is_a_fail_with_its_reason() -> None:
    check = _check(None, None)
    assert check.status == "fail" and check.data["I_LUFS"] is None
    assert check.reason_es is not None and "sonoridad" in check.reason_es
    assert check.to_json()["reason_es"] == check.reason_es


def test_qa_loudness_the_limits_come_from_the_config_and_the_target_from_the_call() -> None:
    qa = QaSection(0.8, 0.5, -2.0, 25)
    assert _check(-15.0, -2.5, qa, target=-16.0).status == "fail"  # 1.0 away with 0.5 allowed
    assert _check(-16.4, -2.5, qa, target=-16.0).status == "pass"
    check = _check(-16.4, -1.5, qa, target=-16.0)
    assert check.status == "fail" and check.data["max_tp"] == -2.0
    assert check.data["target"] == -16.0 and check.data["tolerance"] == 0.5


def test_qa_loudness_it_reads_the_summary_that_ffmpeg_prints() -> None:
    measure = parse_ebur128(SUMMARY.format(i="-14.2", tp="-1.4"))
    check = check_loudness(measure, QA, -14.0)
    assert check.status == "pass" and check.data["LRA"] == 4.1
    silent = parse_ebur128(SUMMARY.format(i="-inf", tp="-inf"))
    assert check_loudness(silent, QA, -14.0).status == "fail"


def test_qa_loudness_the_command_measures_the_first_audio_stream_of_the_video(
    tmp_path: Path,
) -> None:
    args = measure_args(Path("C:/bin/ffmpeg.exe"), tmp_path / "v1.mp4")
    assert args[1:4] == ["-hide_banner", "-nostdin", "-nostats"]  # level info: no -loglevel error
    assert "-loglevel" not in args
    assert args[args.index("-i") + 1] == str(tmp_path / "v1.mp4")
    assert args[args.index("-af") + 1] == "ebur128=peak=true:framelog=quiet"
    assert args[args.index("-map") + 1] == "0:a:0" and args[-3:] == ["-f", "null", "-"]
