"""Fixtures for the doctor unit tests: fake ffmpeg binaries and light stand-in checks."""

import pytest

from kcut import proc
from kcut.doctor import checks
from kcut.doctor.checks import CheckResult
from tests.unit.doctor_fakes import FAKE_FFMPEG, FAKE_FFPROBE


@pytest.fixture
def fake_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        proc, "tool_path", lambda name: FAKE_FFMPEG if name == "ffmpeg" else FAKE_FFPROBE
    )


@pytest.fixture
def light_checks(monkeypatch: pytest.MonkeyPatch, fake_tools: None) -> None:
    """Replace the slow checks (imports, Whisper, Chromium) with canned passes."""
    for name in ("libs", "whisper_model", "chromium"):
        monkeypatch.setattr(
            checks,
            f"check_{name}",
            lambda *_a, _n=name: CheckResult(_n, True, True, "simulado", None),
        )
