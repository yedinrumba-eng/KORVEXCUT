"""`kcut build`, round 1 of S1.9b (spec 001.51 points 2, 3 and 5; rows 27, 28 and 30).

- `build_stale`: a build over an existing video deletes the report and the sheet of the old one.
- `build_frozen`: the snapshot holds what was built, not what the files say at the end.
- `build_warnings`: the warnings of `sfx.json` and `music.json` come out of `kcut build`.

All run `kcut build` in this process (`build_inproc`, `run_build`) so that a spy, or a mutant that
shows the test can fail, can reach it. They start from `built`, the synthetic project built once.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.console import Out, Progress
from kcut.errors import CheckFailed
from kcut.pipeline import build as build_module
from kcut.pipeline.build import STEPS, run_build
from kcut.project import open_project
from tests.e2e.build_helpers import (
    VIDEO,
    BuildRun,
    build_inproc,
    built,
    copy,
    copy_built,
    prepared,
    sha256,
)
from tests.fixtures.synth_project import ProjectTruth

__all__ = ["built", "prepared"]
pytestmark = [  # 001.52: fixtures prepared/built cost ~290 s alone
    pytest.mark.ffmpeg,
    pytest.mark.slow,
    pytest.mark.e2e,
    pytest.mark.timeout(900),
]
EDL = "edit/edl-v1.json"
INPUTS = "qa/v1/inputs/inputs.json"


def _other_look(root: Path, rel: str) -> None:
    """`rel` is the EDL of `edit/` with another `look`: the same cut."""
    document = json.loads((root / EDL).read_text(encoding="utf-8"))
    document["look"] = "contraste"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, indent=1), encoding="utf-8", newline="\n")


def test_build_stale_a_new_video_leaves_no_report_or_sheet_of_the_old_one(
    built: BuildRun, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = copy_built(built, tmp_path)
    assert (root / "qa/v1/report.json").is_file() and (root / "qa/v1/contact.jpg").is_file()
    before = sha256(root / VIDEO)
    _other_look(root, "otros/edl-v1.json")
    code, doc, err = build_inproc(
        capsys, root, "--force", "--skip-qa", "--edl", "otros/edl-v1.json"
    )
    assert code == 0, (doc, err)
    assert sha256(root / VIDEO) != before  # another look: another video
    assert not (root / "qa/v1/report.json").exists()
    assert not (root / "qa/v1/contact.jpg").exists()
    assert doc["verdict"] is None and doc["report"] is None
    inputs = json.loads((root / INPUTS).read_text(encoding="utf-8"))
    assert inputs["files"]["otros/edl-v1.json"] == sha256(root / "otros/edl-v1.json")
    assert sha256(root / "qa/v1/inputs/edl-v1.json") == sha256(root / "otros/edl-v1.json")


def _run(root: Path) -> None:
    """`run_build` over `root` with `--force` and no QA, as the command does."""
    run_build(
        open_project(str(root)),
        None,
        skip_qa=True,
        force=True,
        progress=Progress("build", STEPS, "pasos"),
        out=Out(json_mode=True),
    )


def _after_the_mux(monkeypatch: pytest.MonkeyPatch, root: Path, then: Any) -> None:
    """Run `then()` right after the ffmpeg that writes `salida/v1.partial.mp4`."""
    real = proc.run

    def run(args: list[str], **kwargs: Any) -> Any:
        result = real(args, **kwargs)
        if any(str(item).endswith("v1.partial.mp4") for item in args):
            then()
        return result

    monkeypatch.setattr(proc, "run", run)


def test_build_frozen_an_input_that_changes_during_the_mux_stops_the_build(
    built: BuildRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_built(built, tmp_path)
    video, inputs = sha256(root / VIDEO), sha256(root / INPUTS)
    _after_the_mux(monkeypatch, root, lambda: _other_look(root, EDL))
    with pytest.raises(CheckFailed, match=r"edit/edl-v1\.json cambió mientras se construía") as e:
        _run(root)
    assert e.value.exit_code == 1 and "corre kcut build otra vez" in str(e.value)
    assert sha256(root / VIDEO) == video and sha256(root / INPUTS) == inputs
    assert not (root / "salida" / "v1.partial.mp4").exists()
    assert (root / "qa/v1/report.json").is_file()  # nothing of the old video was deleted


def test_build_frozen_the_snapshot_holds_the_bytes_of_the_first_reading(
    built: BuildRun, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file changes after the second reading, right before the snapshot: the snapshot says
    what was read at the start (and rendered), not what the file says by then."""
    root = copy_built(built, tmp_path)
    original = (root / EDL).read_bytes()
    real = build_module.snapshot_inputs

    def spy(*args: Any, **kwargs: Any) -> Path:
        _other_look(root, EDL)
        return real(*args, **kwargs)

    monkeypatch.setattr(build_module, "snapshot_inputs", spy)
    _run(root)
    assert (root / EDL).read_bytes() != original  # the spy did change it
    inputs = json.loads((root / INPUTS).read_text(encoding="utf-8"))
    assert inputs["files"][EDL] == hashlib.sha256(original).hexdigest()
    assert (root / "qa/v1/inputs/edl-v1.json").read_bytes() == original


def test_build_warnings_the_warnings_of_sfx_come_out_of_build_as_from_mix(
    prepared: tuple[Path, ProjectTruth], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = copy(prepared, tmp_path)
    path = root / "edit" / "sfx.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    first = len(document["events"])
    for _ in range(2):  # 001.52: two events cut the same way are two lines, not one
        document["events"].append({"type": "boom", "at": 0, "align": "end"})  # before frame 0
    path.write_text(json.dumps(document, indent=1), encoding="utf-8", newline="\n")
    code, doc, err = build_inproc(capsys, root, "--skip-qa")
    assert code == 0, (doc, err)
    for index in (first, first + 1):  # 001.52: `<code> <path>: <message>`, as `kcut mix` lists it
        found = [w for w in doc["warnings"] if w.startswith(f"A08 events[{index}]: ")]
        assert len(found) == 1, doc["warnings"]
        assert f"[AVISO] {found[0]}" in err
