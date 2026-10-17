"""Fixtures of the integration tests."""

import shutil
from pathlib import Path

import pytest

from tests.conftest import run_kcut
from tests.fixtures.synth_media import MediaTruth


@pytest.fixture
def blank(tmp_path: Path) -> Path:
    """A new, empty project in a path with a space and an accent."""
    root = tmp_path / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    return root


@pytest.fixture
def two_cameras(
    tmp_path_factory: pytest.TempPathFactory, synth_project: tuple[Path, MediaTruth]
) -> Path:
    """A fresh project with copies of the two synthetic cameras only (no ingest yet)."""
    root = tmp_path_factory.mktemp("edge") / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    for name in ("cam a.mp4", "cam b.mov"):
        shutil.copy2(synth_project[0] / "crudo" / name, root / "crudo" / name)
    return root
