"""Fixtures of the unit tests: fake ffmpeg binaries, light stand-in checks, a bare project."""

from pathlib import Path

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


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A folder with an empty `kcut.toml`: a project as far as `cli.main` can tell (modules with
    a project of their own define theirs and shadow this one)."""
    root = tmp_path / "proyecto ñandú"
    root.mkdir()
    (root / "kcut.toml").write_text("", encoding="utf-8")
    return root


@pytest.fixture
def lonely(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A working directory with no kcut.toml anywhere above it."""
    folder = tmp_path / "sin proyecto"
    folder.mkdir()
    monkeypatch.chdir(folder)
    return folder
