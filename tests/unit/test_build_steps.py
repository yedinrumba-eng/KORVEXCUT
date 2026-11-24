"""What `run_build` does with what its steps give back (spec 001.52, rows 40 and 43).

- `build_snapshot_first`: the snapshot holds the bytes of the first reading, even if a file changes
  after the second one (the spy changes it inside `clear_stale`, which runs after it).
- `build_warnings_m06`: the `M06` that the mixer adds to `issues` while it works comes out of
  `kcut build` in stderr and in `BuildResult.warnings`, in the format of `kcut mix`.

The heavy steps are doubles (`tests/unit/build_early_helpers.py`).
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.issues import MAX_SHOWN, Issue
from kcut.pipeline import build as build_module
from tests.unit.build_early_helpers import early_build, run

M06 = Issue("M06", "warning", "music", "la canción es más corta que el video y no tiene loop")


def test_build_snapshot_first_the_copy_and_its_sha_are_the_bytes_of_the_first_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = early_build(tmp_path, monkeypatch, stop_at_picture=False)
    root = early.project.root
    graphics = root / "edit" / "graphics.json"
    first = graphics.read_bytes()
    real = build_module.clear_stale

    def spy(*args: Any, **kwargs: Any) -> None:
        graphics.write_text('{"graphics": 2}', encoding="utf-8")  # after the second reading
        real(*args, **kwargs)

    monkeypatch.setattr(build_module, "clear_stale", spy)
    run(early)
    assert graphics.read_bytes() != first  # the spy did change it
    inputs = json.loads((root / "qa/v1/inputs/inputs.json").read_text(encoding="utf-8"))
    assert (root / "qa/v1/inputs/graphics.json").read_bytes() == first  # 001.52
    assert inputs["files"]["edit/graphics.json"] == hashlib.sha256(first).hexdigest()


def test_build_warnings_m06_the_warning_of_the_mixer_comes_out_of_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    early = early_build(tmp_path, monkeypatch, stop_at_picture=False)
    early.issues.append(M06)  # the mixer adds it to `issues` while it works
    root = early.project.root
    capsys.readouterr()
    code = cli.main(["build", "--project", str(root), "--json", "--skip-qa", "--force"])
    captured = capsys.readouterr()
    line = f"M06 music: {M06.message_es}"
    assert code == 0, captured.err
    assert line in json.loads(captured.out)["warnings"]  # in `BuildResult.warnings`
    assert f"[AVISO] {line}" in captured.err  # and in stderr


def test_build_warnings_m06_two_findings_with_the_same_text_are_two_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = early_build(tmp_path, monkeypatch, stop_at_picture=False)
    early.issues += [
        Issue("A08", "warning", "events[3]", "se corta"),
        Issue("A08", "warning", "events[9]", "se corta"),
    ]
    result = run(early)
    assert [w for w in result.warnings if w.startswith("A08")] == [
        "A08 events[3]: se corta",
        "A08 events[9]: se corta",
    ]  # 001.52: not merged by text


def test_build_warnings_m06_more_than_the_cap_ends_with_how_many_were_left_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    early = early_build(tmp_path, monkeypatch, stop_at_picture=False)
    early.issues += [
        Issue("A08", "warning", f"events[{n}]", "se corta") for n in range(MAX_SHOWN + 3)
    ]
    result = run(early)
    assert len(result.warnings) == MAX_SHOWN + 1
    assert result.warnings[-1] == "... y 3 más"
