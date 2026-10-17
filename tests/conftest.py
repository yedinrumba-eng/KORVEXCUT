"""Shared test setup: clean skips for tests that need external tools, and a CLI runner."""

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest

from tests.fixtures.synth_media import MediaTruth, make_media


def run_kcut(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run `python -m kcut <args>` in a fresh isolated interpreter, capturing UTF-8 text."""
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-m", "kcut", *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


@cache
def _ffmpeg_available() -> bool:
    return bool(os.environ.get("KCUT_FFMPEG")) or shutil.which("ffmpeg") is not None


@cache
def _chromium_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            return Path(pw.chromium.executable_path).exists()
    except Exception:
        return False


@cache
def _whisper_available() -> bool:
    try:
        from faster_whisper.utils import download_model

        download_model("medium", local_files_only=True)
    except Exception:
        return False
    return True


@cache
def _flite_available() -> bool:
    if not _ffmpeg_available():
        return False
    from kcut import proc
    from kcut.doctor.ffmpeg_caps import parse_filters
    from kcut.errors import KcutError

    try:
        result = proc.run(
            [str(proc.tool_path("ffmpeg")), "-hide_banner", "-nostdin", "-filters"],
            capture_stderr=True,
        )
    except KcutError:
        return False
    text = result.stdout.decode("utf-8", errors="replace") + result.stderr
    return "flite" in parse_filters(text)


_REQUIREMENTS: dict[str, tuple[Callable[[], bool], str]] = {
    "ffmpeg": (_ffmpeg_available, "ffmpeg no está disponible"),
    "chromium": (_chromium_available, "Chromium de Playwright no está instalado"),
    "whisper": (_whisper_available, "el modelo medium de Whisper no está en local"),
    "flite": (_flite_available, "ffmpeg no tiene el filtro flite"),
}


def pytest_sessionstart(session: pytest.Session) -> None:
    """Import `scipy.signal` once, before any test runs: its first import costs 1.5-4.5 s and the
    test that happened to run first would carry it in its duration (the fast suite keeps every
    test under 2 s, S1.2-47)."""
    import scipy.signal  # noqa: F401


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Skip, instead of failing, every test whose marker needs something missing."""
    for item in items:
        for marker, (available, reason) in _REQUIREMENTS.items():
            if item.get_closest_marker(marker) is not None and not available():
                item.add_marker(pytest.mark.skip(reason=reason))


@pytest.fixture(scope="session")
def synth_project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, MediaTruth]:
    """A synthetic project in `<tmp>/proyecto ñandú`: `kcut new`, generated media, `kcut ingest`.

    Tests that use it carry the `ffmpeg` marker, so they are skipped when ffmpeg is missing.
    """
    root = tmp_path_factory.mktemp("synth") / "proyecto ñandú"
    created = run_kcut("new", str(root))
    assert created.returncode == 0, created.stderr
    truth = make_media(root / "crudo")
    ingested = run_kcut("ingest", "--project", str(root), "--json")
    assert ingested.returncode == 0, ingested.stderr
    return root, truth
