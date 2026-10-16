"""Real `kcut doctor` run on the reference machine (ffmpeg, Chromium and Whisper present)."""

import json

import pytest

from tests.conftest import run_kcut

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]

EXPECTED_IDS = [
    "python",
    "ffmpeg",
    "ffprobe",
    "filters",
    "filters_optional",
    "encoders",
    "libs",
    "whisper_model",
    "chromium",
    "fonts",
    "disk",
]


def test_doctor_json_passes_on_the_reference_machine() -> None:
    result = run_kcut("doctor", "--json")
    doc = json.loads(result.stdout)
    assert doc["schema"] == "kcut.doctor/1"
    assert doc["version"] == "0.1.0"
    assert [c["id"] for c in doc["checks"]] == EXPECTED_IDS
    failed = [c for c in doc["checks"] if c["required"] and not c["ok"]]
    assert failed == []
    assert doc["ok"] is True
    assert result.returncode == 0


def test_doctor_human_output_uses_ascii_tags() -> None:
    result = run_kcut("doctor")
    assert result.returncode == 0
    assert "[OK] python:" in result.stdout
    assert "—" not in result.stdout
