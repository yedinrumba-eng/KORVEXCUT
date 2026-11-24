"""`kcut qa` refuses what is not `salida/vN.mp4` and what it must not write through (spec S1.9a
row 8; 001.15 T3 and T4). Collected from `test_qa_synth.py`, which is at the 300-line limit; the
module that imports it has to bring the fixture `built`.

T3: the measurement filters print metadata at the `info` level, so they only run over what kcut
made: any other path is exit 2 before ffmpeg or ffprobe are started, and a video that is a link
or a second name of another file (a hard link to a file of `crudo/`) is not measured. T4:
`qa/vN/report.json` and `qa/vN/contact.jpg` go through `assert_writable`: a symlink, a hard link
or a junction in them is exit 3 and nothing goes through it.
"""

import json
import os
import shutil
from pathlib import Path

import pytest

from kcut.errors import ProjectError
from kcut.paths import same_path
from kcut.project import open_project
from kcut.qa.run import _video_path
from tests.fixtures.links import make_dir_link, make_hard_link, remove_dir_link
from tests.integration.qa_helpers import VIDEO, check_of, copy_of, sha256_of, spy_on_ffmpeg
from tests.integration.view_frames_helpers import Run, project_args

__all__ = [
    "test_qa_only_salida_a_video_that_is_a_hard_link_is_not_measured",
    "test_qa_only_salida_a_video_that_is_not_there_is_exit_3",
    "test_qa_only_salida_anything_else_is_exit_2_and_no_ffmpeg_runs",
    "test_qa_video_link_a_file_symlink_is_refused",
    "test_qa_video_link_a_hard_link_is_still_exit_3",
    "test_qa_video_link_a_plain_video_is_accepted_and_is_the_resolved_path",
    "test_qa_video_link_salida_as_a_junction_to_crudo_is_exit_3_and_no_tool_runs",
    "test_qa_video_link_salida_as_a_junction_to_crudo_is_refused_before_it_is_resolved",
    "test_qa_writable_a_fail_verdict_still_writes_the_report_and_is_exit_1",
    "test_qa_writable_a_report_that_is_a_hard_link_is_exit_3_and_the_target_is_not_touched",
    "test_qa_writable_a_report_that_is_a_symlink_is_exit_3_and_the_target_is_not_touched",
    "test_qa_writable_the_contact_sheet_as_a_hard_link_is_refused_too",
    "test_qa_writable_the_edl_of_the_build_snapshot_is_the_one_used_when_it_is_there",
    "test_qa_writable_the_folder_of_the_report_as_a_junction_is_exit_3_and_nothing_goes_through",
]


@pytest.mark.parametrize(
    "video",
    [
        "crudo/x.mp4",
        "edit/x.mp4",
        "salida/x.mp4",
        "salida/v0.mp4",
        "salida/v01.mp4",
        "salida/v10000.mp4",
        "salida/v1.mov",
        "salida/v1.mp4.bak",
        "salida/sub/v1.mp4",
        "salida/../crudo/v1.mp4",
        "salida\\v1.mp4",
        "./salida/v1.mp4",
        "C:/salida/v1.mp4",
        "/salida/v1.mp4",
        "salida/v1.mp4 ",
        "",
    ],
)
def test_qa_only_salida_anything_else_is_exit_2_and_no_ffmpeg_runs(
    built: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, video: str
) -> None:
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", video, *project_args(built))
    assert code == 2 and doc["error"]["kind"] == "UsageError", doc
    assert seen == []  # not ffprobe, not a measurement filter
    assert video.strip() == "" or video not in doc["error"]["message"]  # it does not echo it


def test_qa_only_salida_a_video_that_is_not_there_is_exit_3(
    built: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", "salida/v9.mp4", *project_args(built))
    assert code == 3 and doc["error"]["kind"] == "ProjectError" and seen == []


def test_qa_only_salida_a_video_that_is_a_hard_link_is_not_measured(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`salida/v2.mp4` as a second name of a file of `crudo/`: the filters would print its
    metadata. Refused, exit 3, before ffmpeg."""
    root = copy_of(built, tmp_path)
    crudo = next((root / "crudo").glob("*.mp4"))
    make_hard_link(root / "salida" / "v2.mp4", crudo)
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", "salida/v2.mp4", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError" and seen == []


def _decoy(root: Path) -> Path:
    """A file of `crudo/` that nothing may write through."""
    target = root / "crudo" / "no_tocar.txt"
    target.write_text("de otro", encoding="utf-8")
    (root / "qa" / "v1").mkdir(parents=True, exist_ok=True)
    return target


def test_qa_writable_a_report_that_is_a_symlink_is_exit_3_and_the_target_is_not_touched(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    target = _decoy(root)
    try:
        os.symlink(target, root / "qa" / "v1" / "report.json")
    except OSError as exc:
        pytest.skip(f"no se pudo crear el enlace simbólico: {exc}")
    seen = spy_on_ffmpeg(monkeypatch)
    before = sha256_of(target)
    code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError" and seen == []
    assert sha256_of(target) == before


def test_qa_writable_a_report_that_is_a_hard_link_is_exit_3_and_the_target_is_not_touched(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    target = _decoy(root)
    make_hard_link(root / "qa" / "v1" / "report.json", target)
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError" and seen == []
    assert target.read_text(encoding="utf-8") == "de otro"


def test_qa_writable_the_contact_sheet_as_a_hard_link_is_refused_too(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    target = _decoy(root)
    make_hard_link(root / "qa" / "v1" / "contact.jpg", target)
    seen = spy_on_ffmpeg(monkeypatch)
    code, _, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 3 and seen == [] and target.read_text(encoding="utf-8") == "de otro"


def test_qa_writable_the_folder_of_the_report_as_a_junction_is_exit_3_and_nothing_goes_through(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    outside = tmp_path / "ajeno"
    outside.mkdir()
    shutil.rmtree(root / "qa" / "v1", ignore_errors=True)
    make_dir_link(root / "qa" / "v1", outside)
    seen = spy_on_ffmpeg(monkeypatch)
    try:
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    finally:
        remove_dir_link(root / "qa" / "v1")
    assert code == 3 and doc["error"]["kind"] == "ProjectError" and seen == []
    assert list(outside.iterdir()) == []


def test_qa_writable_a_fail_verdict_still_writes_the_report_and_is_exit_1(
    built: Path, tmp_path: Path, kcut_json: Run
) -> None:
    """An EDL that is one frame shorter than the video: `frames` fails. The good EDL is the
    snapshot of the build, so an `--edl` that was ignored would give a pass (001.43, point 1)."""
    root = copy_of(built, tmp_path)
    good = root / "edit" / "edl-v1.json"
    snapshot = root / "qa" / "v1" / "inputs" / "edl-v1.json"  # 001.43: the good one, planted
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(good.read_bytes())
    document = json.loads(good.read_text(encoding="utf-8"))
    # 001.43: 1920x1080 would not pass the gate of `kcut qa` (E03), and this does
    document["frames"] = 344
    document["clips"][-1]["dur_f"] = 29
    document["spans"][-1]["dur_f"] = 29
    good.write_text(json.dumps(document), encoding="utf-8")
    code, doc, _ = kcut_json("qa", VIDEO, "--edl", "edit/edl-v1.json", *project_args(root))
    assert code == 1 and doc["verdict"] == "fail" and doc["edl"] == "edit/edl-v1.json"  # 001.41
    assert check_of(doc, "frames")["status"] == "fail"  # 001.43
    on_disk = json.loads((root / "qa" / "v1" / "report.json").read_text(encoding="utf-8"))
    assert on_disk["verdict"] == "fail"


def test_qa_writable_the_edl_of_the_build_snapshot_is_the_one_used_when_it_is_there(
    built: Path, tmp_path: Path, kcut_json: Run
) -> None:
    root = copy_of(built, tmp_path)
    inputs = root / "qa" / "v1" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "edl-v1.json").write_bytes((root / "edit" / "edl-v1.json").read_bytes())
    code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0 and doc["edl"] == "qa/v1/inputs/edl-v1.json"


def _link_salida_to_crudo(root: Path) -> None:
    """`salida/` as a link to `crudo/`, which has a `v1.mp4` in it: the file of the user that the
    link would lead `kcut qa` to (001.41, point 1)."""
    shutil.copy2(root / VIDEO, root / "crudo" / "v1.mp4")
    shutil.rmtree(root / "salida")
    make_dir_link(root / "salida", root / "crudo")


def test_qa_video_link_salida_as_a_junction_to_crudo_is_refused_before_it_is_resolved(
    built: Path, tmp_path: Path
) -> None:
    """`resolve()` turns a link into its target, so the link has to be looked at first: the
    resolved `salida/v1.mp4` would be `crudo/v1.mp4`, a file that is a file and has one name."""
    root = copy_of(built, tmp_path)
    project = open_project(str(root))  # opened while `salida/` is still a folder
    _link_salida_to_crudo(root)
    try:
        with pytest.raises(ProjectError, match=r"salida/v1\.mp4 es un enlace; kcut qa no lo mide"):
            _video_path(project, VIDEO)
    finally:
        remove_dir_link(root / "salida")


def test_qa_video_link_salida_as_a_junction_to_crudo_is_exit_3_and_no_tool_runs(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    _link_salida_to_crudo(root)
    seen = spy_on_ffmpeg(monkeypatch)
    try:
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    finally:
        remove_dir_link(root / "salida")
    assert code == 3 and doc["error"]["kind"] == "ProjectError" and seen == []
    assert not (root / "qa" / "v1" / "report.json").exists()


def test_qa_video_link_a_hard_link_is_still_exit_3(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    make_hard_link(root / "salida" / "v2.mp4", next((root / "crudo").glob("*.mp4")))
    with pytest.raises(ProjectError, match=r"salida/v2\.mp4 es un enlace; kcut qa no lo mide"):
        _video_path(open_project(str(root)), "salida/v2.mp4")
    seen = spy_on_ffmpeg(monkeypatch)
    code, doc, _ = kcut_json("qa", "salida/v2.mp4", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError" and seen == []


def test_qa_video_link_a_file_symlink_is_refused(built: Path, tmp_path: Path) -> None:
    root = copy_of(built, tmp_path)
    project = open_project(str(root))
    try:
        os.symlink(next((root / "crudo").glob("*.mp4")), root / "salida" / "v2.mp4")
    except OSError as exc:
        pytest.skip(f"no se pudo crear el enlace simbólico: {exc}")
    with pytest.raises(ProjectError, match=r"salida/v2\.mp4 es un enlace; kcut qa no lo mide"):
        _video_path(project, "salida/v2.mp4")


def test_qa_video_link_a_plain_video_is_accepted_and_is_the_resolved_path(built: Path) -> None:
    found = _video_path(open_project(str(built)), VIDEO)
    assert same_path(found, built.resolve() / "salida" / "v1.mp4") and found.is_file()
