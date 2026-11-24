"""`kcut build` on the synthetic project, from end to end (spec S1.9b rows 1, 2, 3 and 5).

`built` is the whole synthetic project (`tests/fixtures/synth_project.py`: media, transcript if
there is a model, the example EDL, the graphics with the showpieces and the plans of audio) built
once for the module with `kcut build --json`. Row 1 reads its report; row 3 its snapshot. The
refusals of rows 2 and 5 happen before any work, so they run on a copy of the project as it was
before the build (`prepared`), and each takes seconds.
"""

import json
import os
from pathlib import Path

import pytest

from tests.e2e.build_helpers import (  # 001.51: the fixtures and helpers live in `build_helpers`
    VIDEO,
    BuildRun,
    built,
    prepared,
)
from tests.e2e.build_helpers import build as _build
from tests.e2e.build_helpers import check as _check
from tests.e2e.build_helpers import copy as _copy
from tests.e2e.build_helpers import disapprove as _disapprove
from tests.e2e.build_helpers import sha256 as _sha256
from tests.fixtures.links import make_hard_link
from tests.fixtures.synth_project import ProjectTruth

__all__ = ["built", "prepared"]
pytestmark = [  # 001.52: fixtures prepared/built cost ~290 s alone
    pytest.mark.ffmpeg,
    pytest.mark.slow,
    pytest.mark.e2e,
    pytest.mark.timeout(900),
]


def test_build_synth_makes_the_video_and_its_report_passes(
    built: BuildRun, prepared: tuple[Path, ProjectTruth]
) -> None:
    code, doc, root = built
    assert code == 0, doc
    assert (root / VIDEO).is_file() and doc["video"] == VIDEO and doc["frames"] == 345
    assert not (root / "salida" / "v1.partial.mp4").exists()
    report = doc["report"]
    assert report["schema"] == "kcut.qa/1" and report["video"] == VIDEO
    assert report["edl"] == "qa/v1/inputs/edl-v1.json"  # judged against what was built
    assert report["verdict"] in ("pass", "incomplete"), report
    assert (root / "qa" / "v1" / "report.json").is_file()
    assert _check(report, "frames")["value"] == 345
    assert _check(report, "av_delta")["value_ms"] <= 25
    loudness = _check(report, "loudness")
    assert -15 <= loudness["I_LUFS"] <= -13 and loudness["TP_dBTP"] <= -1.0, loudness
    assert _check(report, "black")["status"] == "pass"
    assert _check(report, "freeze")["status"] == "pass"
    transcript = _check(report, "transcript")
    if prepared[1].transcribed:  # with the model of Whisper the voice is heard and compared
        assert transcript["status"] == "pass" and transcript["match"] >= 0.5, transcript
    else:
        assert transcript["status"] == "skipped", transcript
    assert set(doc["timings_s"]) == {"picture", "mix", "mux", "snapshot", "qa"}


def test_snapshot_inputs_json_has_the_sha256_of_each_input_and_each_copy(built: BuildRun) -> None:
    _, doc, root = built
    folder = root / "qa" / "v1" / "inputs"
    inputs = json.loads((folder / "inputs.json").read_text(encoding="utf-8"))
    assert doc["inputs"] == "qa/v1/inputs/inputs.json"
    assert inputs["schema"] == "kcut.inputs/1" and inputs["version"] == 1
    wanted = [
        "edit/edl-v1.json",
        "edit/estrategia.md",
        "edit/graphics.json",
        "edit/music.json",
        "edit/sfx.json",
        "kcut.toml",
    ]
    if (root / "edit" / "correcciones.json").is_file():  # only if somebody wrote corrections
        wanted.append("edit/correcciones.json")
    assert sorted(inputs["files"]) == sorted(wanted)
    for rel, digest in inputs["files"].items():
        assert digest == _sha256(root / rel), rel  # what the file says now is what was built
        assert digest == _sha256(folder / Path(rel).name), rel  # and the copy is the same
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        ["inputs.json", *(Path(rel).name for rel in inputs["files"])]
    )


def test_build_no_overwrite_a_video_that_is_there_is_exit_3_without_force(
    prepared: tuple[Path, ProjectTruth], tmp_path: Path
) -> None:
    root = _copy(prepared, tmp_path)
    (root / "salida").mkdir(exist_ok=True)
    (root / VIDEO).write_bytes(b"not a video, and not to be touched")
    before = _sha256(root / VIDEO)
    code, doc, _ = _build(root)
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert "--force" in doc["error"]["message"]
    assert _sha256(root / VIDEO) == before
    assert not (root / ".kcut" / "build" / "v1").exists()  # nothing was made


def test_build_gate_without_the_approval_is_exit_5_and_makes_nothing(
    prepared: tuple[Path, ProjectTruth], tmp_path: Path
) -> None:
    root = _copy(prepared, tmp_path)
    _disapprove(root)
    code, doc, _ = _build(root)
    assert code == 5 and doc["error"]["kind"] == "GateError", doc
    assert not (root / VIDEO).exists() and not (root / ".kcut" / "build" / "v1").exists()


def test_build_error_order_a_video_there_and_no_approval_is_3_and_with_force_is_5(
    prepared: tuple[Path, ProjectTruth], tmp_path: Path
) -> None:
    """001.15: with `salida/v1.mp4`, no `--force` and no approval the exit is 3, not 5."""
    root = _copy(prepared, tmp_path)
    _disapprove(root)
    (root / "salida").mkdir(exist_ok=True)
    (root / VIDEO).write_bytes(b"not a video")
    code, doc, _ = _build(root)
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    code, doc, _ = _build(root, "--force")  # the first check is passed: now the gate speaks
    assert code == 5 and doc["error"]["kind"] == "GateError", doc
    assert (root / VIDEO).read_bytes() == b"not a video"


def test_build_writable_a_symlink_to_a_file_of_crudo_is_exit_3_and_the_file_stays(
    prepared: tuple[Path, ProjectTruth], tmp_path: Path
) -> None:
    root = _copy(prepared, tmp_path)
    decoy = next((root / "crudo").glob("*.mp4"))
    before = _sha256(decoy)
    (root / "salida").mkdir(exist_ok=True)
    try:
        os.symlink(decoy, root / VIDEO)
    except OSError as exc:
        pytest.skip(f"no se pudo crear el enlace simbólico: {exc}")
    code, doc, _ = _build(root, "--force")
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert _sha256(decoy) == before
    assert not (root / "salida" / "v1.partial.mp4").exists()


def test_build_writable_a_hard_link_to_a_file_of_crudo_is_exit_3_and_the_file_stays(
    prepared: tuple[Path, ProjectTruth], tmp_path: Path
) -> None:
    root = _copy(prepared, tmp_path)
    decoy = next((root / "crudo").glob("*.mp4"))
    before = _sha256(decoy)
    (root / "salida").mkdir(exist_ok=True)
    make_hard_link(root / VIDEO, decoy)
    code, doc, _ = _build(root, "--force")
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert _sha256(decoy) == before and _sha256(root / VIDEO) == before
