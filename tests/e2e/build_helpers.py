"""What the e2e tests of `kcut build` share (spec S1.9b): the synthetic project prepared and built
once for each module that imports the fixtures, and the little functions around `kcut build`.

`prepared` is the synthetic project with everything `kcut build` reads, not built yet; `built` is a
copy of it built once with `kcut build --json`. Both folders are deleted when the module closes.
"""

import hashlib
import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from tests.conftest import run_kcut
from tests.fixtures.synth_media import MediaTruth
from tests.fixtures.synth_project import ProjectTruth, finish_project
from tests.tmp_cleanup import remove_tree

__all__ = [
    "VIDEO",
    "BuildRun",
    "build",
    "build_inproc",
    "built",
    "check",
    "copy",
    "copy_built",
    "disapprove",
    "prepared",
    "sha256",
]
VIDEO = "salida/v1.mp4"
BuildRun = tuple[int, dict[str, Any], Path]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(root: Path, *flags: str) -> tuple[int, dict[str, Any], str]:
    """`kcut build --json` in a fresh interpreter: the exit code, the JSON on stdout (the error
    document or the result), and stderr."""
    done = run_kcut("build", "--project", str(root), "--json", *flags)
    return done.returncode, json.loads(done.stdout), done.stderr


@pytest.fixture(scope="module")
def prepared(
    tmp_path_factory: pytest.TempPathFactory, synth_project: tuple[Path, MediaTruth]
) -> Iterator[tuple[Path, ProjectTruth]]:
    """The synthetic project with everything `kcut build` reads, and not built yet. Its folder is
    deleted when the module closes."""
    folder = tmp_path_factory.mktemp("buildprepared")
    root = folder / "proyecto ñandú"
    try:
        shutil.copytree(synth_project[0], root)
        yield root, finish_project(root, synth_project[1])
    finally:
        remove_tree(folder)


@pytest.fixture(scope="module")
def built(
    tmp_path_factory: pytest.TempPathFactory, prepared: tuple[Path, ProjectTruth]
) -> Iterator[BuildRun]:
    """`kcut build --json` once on a copy of `prepared`: the exit code, the JSON it printed and the
    project. Its folder is deleted when the module closes."""
    folder = tmp_path_factory.mktemp("buildbuilt")
    root = folder / "proyecto ñandú"
    try:
        shutil.copytree(prepared[0], root)
        code, doc, stderr = build(root)
        assert code in (0, 1), (code, doc, stderr)  # a failed QA is exit 1, with the video made
        yield code, doc, root
    finally:
        remove_tree(folder)


def copy(prepared: tuple[Path, ProjectTruth], tmp_path: Path) -> Path:
    """A project of its own, as `prepared` is."""
    root = tmp_path / "proyecto ñandú"
    shutil.copytree(prepared[0], root)
    return root


def check(report: dict[str, Any], check_id: str) -> dict[str, Any]:
    found = [c for c in report["checks"] if c["id"] == check_id]
    assert len(found) == 1, (check_id, [c["id"] for c in report["checks"]])
    check: dict[str, Any] = found[0]
    return check


def disapprove(root: Path) -> None:
    """`edit/estrategia.md` with `aprobado: no`."""
    path = root / "edit" / "estrategia.md"
    text = path.read_text(encoding="utf-8")
    assert "aprobado: si" in text
    path.write_text(text.replace("aprobado: si", "aprobado: no"), encoding="utf-8", newline="\n")


def build_inproc(
    capsys: pytest.CaptureFixture[str], root: Path, *flags: str
) -> tuple[int, dict[str, Any], str]:
    """`kcut build --json` in this process (a spy or a mutant can reach it): the exit code, the
    JSON on stdout and stderr."""
    capsys.readouterr()
    code = cli.main(["build", "--project", str(root), "--json", *flags])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def copy_built(built: BuildRun, tmp_path: Path) -> Path:
    """A project of its own, as `built` left it (with its video, its report and its snapshot)."""
    root = tmp_path / "proyecto ñandú"
    shutil.copytree(built[2], root)
    return root
