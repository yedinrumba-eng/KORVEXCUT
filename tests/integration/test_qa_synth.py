"""`kcut qa` on a finished video (spec S1.9a, rows 5, 6 and 8).

The video is the example EDL rendered, mixed and joined (`qa_helpers.built`). Row 5 is here: the
report has 345 frames, an A/V difference of at most 25 ms and `loudness`, `black` and `freeze` in
pass, and the contact sheet shows the frames 0, 60, 120, 180, 240 and 300. Row 6 (T2, the phone that
was said) is in `qa_pii_cases.py` and row 8 (T3 and T4, only `salida/vN.mp4` and no writing through
links) in `qa_writable_cases.py`, both collected here by the 300-line rule.
"""

import io
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from kcut.qa.contact import contact_jpeg
from tests.integration.qa_helpers import VIDEO, QaRun, built, check_of, qa_run, ramp_video
from tests.integration.qa_pii_cases import *  # noqa: F403
from tests.integration.qa_writable_cases import *  # noqa: F403

__all__ = ["built", "qa_run"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
CHECKS = ["frames", "video_stream", "audio_stream", "av_delta", "loudness", "black", "freeze"]


def test_qa_report_the_checks_of_the_spec_pass_and_the_transcript_waits_for_words(
    qa_run: QaRun,
) -> None:
    code, doc, _ = qa_run
    assert code == 0, doc
    assert doc["schema"] == "kcut.qa/1" and doc["video"] == VIDEO
    assert [c["id"] for c in doc["checks"]] == [*CHECKS, "transcript"]
    assert {c["id"]: c["status"] for c in doc["checks"]} == {
        **dict.fromkeys(CHECKS, "pass"),
        "transcript": "skipped",
    }
    assert doc["verdict"] == "incomplete"  # nothing failed, one check was skipped
    assert check_of(doc, "transcript")["reason_es"]


def test_qa_report_has_345_frames_and_the_streams_of_the_preset(qa_run: QaRun) -> None:
    _, doc, _ = qa_run
    assert check_of(doc, "frames") == {
        "id": "frames", "status": "pass", "value": 345, "expected": 345,
    }  # fmt: skip
    assert check_of(doc, "video_stream")["value"] == {
        "codec": "h264", "size": "1080x1920", "fps": "30/1", "color_space": "bt709",
    }  # fmt: skip
    assert check_of(doc, "audio_stream")["value"] == {
        "codec": "aac", "sample_rate": 48000, "channels": 2,
    }  # fmt: skip


def test_qa_report_the_picture_and_the_sound_are_the_same_length_within_25_ms(
    qa_run: QaRun,
) -> None:
    _, doc, _ = qa_run
    delta = check_of(doc, "av_delta")
    assert delta["max_ms"] == 25 and 0 <= delta["value_ms"] <= 25, delta


def test_qa_report_the_loudness_is_at_the_target_and_the_peak_under_the_ceiling(
    qa_run: QaRun,
) -> None:
    _, doc, _ = qa_run
    loud = check_of(doc, "loudness")
    assert abs(loud["I_LUFS"] - loud["target"]) <= loud["tolerance"], loud
    assert loud["TP_dBTP"] <= loud["max_tp"], loud


def test_qa_report_black_and_freeze_are_only_where_the_edl_puts_a_color_or_a_screen(
    qa_run: QaRun,
) -> None:
    _, doc, _ = qa_run
    black, freeze = check_of(doc, "black"), check_of(doc, "freeze")
    assert black["intervals"] and all(i["expected"] for i in black["intervals"]), black
    assert all(i["expected"] for i in freeze["intervals"]), freeze


def test_qa_report_the_file_is_the_document_the_command_printed(qa_run: QaRun) -> None:
    _, doc, root = qa_run
    on_disk = json.loads((root / "qa" / "v1" / "report.json").read_text(encoding="utf-8"))
    assert on_disk == doc
    assert doc["contact_sheet"] == "qa/v1/contact.jpg" and doc["edl"] == "edit/edl-v1.json"
    assert doc["duration_display"] == "00:11.5" and doc["file_mb"] > 0
    assert set(doc["timings_s"]) == {"probe", "loudness", "detect", "transcript", "contact"}
    assert "warnings" not in doc  # nothing to warn about in this project


def test_qa_report_the_contact_sheet_is_a_jpeg_of_6_frames_of_216_by_384(qa_run: QaRun) -> None:
    _, _, root = qa_run
    image = Image.open(root / "qa" / "v1" / "contact.jpg")
    assert image.format == "JPEG" and image.size == (6 * 216, 384 + 24)  # a row: 6 frames + label


def test_qa_report_the_contact_sheet_uses_the_frames_0_60_120_180_240_and_300(
    tmp_path: Path,
) -> None:
    """Measured on a ramp: place `k` of the sheet has the gray of the frame `60 * k`, and not
    the one of the frames 29, 89, 149... that `fps=1/2` gives without `round=up`."""
    video = tmp_path / "ramp.mp4"
    ramp_video(video)
    sheet = Image.open(io.BytesIO(contact_jpeg(video, 345, 30, (216, 384), None)))
    pixels = np.asarray(sheet.convert("L"), dtype=np.float32)
    seen = [float(pixels[40:344, k * 216 + 20 : k * 216 + 196].mean()) for k in range(6)]
    wanted = [255 * (60 * k) / 344 for k in range(6)]
    for found, expect in zip(seen, wanted, strict=True):
        assert abs(found - expect) <= 4.0, (seen, wanted)
    # frame 29 would be 21.5 and the frame 60 is 44.5: the sampling is 23 levels away
    assert abs(seen[1] - 255 * 29 / 344) > 15


def test_qa_report_the_sheet_has_a_label_under_each_frame(tmp_path: Path) -> None:
    video = tmp_path / "ramp.mp4"
    ramp_video(video, frames=125)
    sheet = Image.open(io.BytesIO(contact_jpeg(video, 125, 30, (216, 384), None)))
    assert sheet.size == (3 * 216, 384 + 24)  # (125 + 59) // 60 = 3 frames
    label = np.asarray(sheet.convert("L"), dtype=np.float32)[384:, :216]
    assert label.max() > 200  # white letters on the dark background
