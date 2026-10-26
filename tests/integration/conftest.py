"""Fixtures of the integration tests."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from tests.conftest import run_kcut
from tests.fixtures.synth_media import MediaTruth
from tests.integration.view_frames_helpers import Run, Synth


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


@pytest.fixture(scope="module")
def view_shared(tmp_path_factory: pytest.TempPathFactory, synth_project: Synth) -> Path:
    """A copy of the synthetic project for the `view` / `frames` tests that only add pictures
    under `.kcut/`: one per module."""
    root = tmp_path_factory.mktemp("viewframes") / "proyecto ñandú"
    shutil.copytree(synth_project[0], root)
    return root


@pytest.fixture
def view_fresh(tmp_path_factory: pytest.TempPathFactory, synth_project: Synth) -> Path:
    """A copy of its own, for the tests that break something (a wav16, a proxy) or watch crudo."""
    root = tmp_path_factory.mktemp("viewfresh") / "proyecto ñandú"
    shutil.copytree(synth_project[0], root)
    return root


@pytest.fixture
def kcut_json(capsys: pytest.CaptureFixture[str]) -> Run:
    """Run `kcut <args> --json` in process: (exit code, the JSON document, stderr)."""

    def run(*args: str) -> tuple[int, dict[str, Any], str]:
        capsys.readouterr()
        code = cli.main([*args, "--json"])
        captured = capsys.readouterr()
        return code, json.loads(captured.out), captured.err

    return run
