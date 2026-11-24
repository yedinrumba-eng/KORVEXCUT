"""`kcut qa` looks at `salida/` again right before each tool that reads the video (spec S1.9b step
0, row 9; 001.43 point 7, 001.47 point 2).

The ffprobe, the loudness, the black and the freeze filters each take minutes on a long video, and
in that time `salida/` can become a junction to somebody else's folder. A spy of `proc.run` swaps
`salida/` for a junction after its N-th call: the next tool must not run, and the exit is 3, the
same one `_video_path` gives. The freeze filter is the 4th call: after it the only reader of the
video is the sheet of a project that does not mask (the ear has no transcript in this project).
"""

import shutil
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.qa import run as qa_run
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.integration.graphics_helpers import plant_words
from tests.integration.qa_contact_helpers import mask_pii_off
from tests.integration.qa_helpers import VIDEO, built, copy_of, spy_on_ffmpeg
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["built"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]


@pytest.mark.parametrize(
    ("swap_after", "unmasked"),
    [(1, False), (2, False), (3, False), (4, True)],
    ids=["probe", "loudness", "black", "sheet_from_the_video"],
)
def test_qa_relook_a_salida_that_becomes_a_junction_in_the_middle_stops_the_next_tool(
    built: Path,
    tmp_path: Path,
    kcut_json: Run,
    monkeypatch: pytest.MonkeyPatch,
    swap_after: int,
    unmasked: bool,
) -> None:
    """The sheet only reads the video with `privacy.mask_pii = false`; masked, it is the proxy."""
    root = copy_of(built, tmp_path)
    if unmasked:
        mask_pii_off(root)
    elsewhere = tmp_path / "otra carpeta"
    elsewhere.mkdir()
    shutil.copy2(root / VIDEO, elsewhere / "v1.mp4")
    calls: list[list[str]] = []
    real_run = proc.run

    def run(args: list[str], **kwargs: Any) -> Any:
        calls.append(args)
        result = real_run(args, **kwargs)
        if len(calls) == swap_after:  # right after this tool: `salida/` is somebody else's now
            shutil.move(root / "salida", root / "salida_real")
            make_dir_link(root / "salida", elsewhere)
        return result

    monkeypatch.setattr(proc, "run", run)
    try:
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    finally:
        remove_dir_link(root / "salida")
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert len(calls) == swap_after  # the tool after the swap did not run
    assert not (root / "qa" / "v1" / "report.json").exists()


def _swap_salida(root: Path, elsewhere: Path) -> None:
    """`salida/` of `root` becomes a junction to `elsewhere`, which has its own `v1.mp4`."""
    shutil.copy2(root / VIDEO, elsewhere / "v1.mp4")
    shutil.move(root / "salida", root / "salida_real")
    make_dir_link(root / "salida", elsewhere)


def test_qa_relook_a_salida_that_changes_while_the_edl_is_judged_stops_ffprobe(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """001.49 point 1: between the first look and ffprobe run two `assert_writable`, the inventory,
    `_edl_rel` and `check_edl_file`; `salida/` is looked at again right before ffprobe."""
    root = copy_of(built, tmp_path)
    elsewhere = tmp_path / "otra carpeta"
    elsewhere.mkdir()
    real_check = qa_run.check_edl_file

    def check(*args: Any, **kwargs: Any) -> Any:
        result = real_check(*args, **kwargs)  # the last thing that runs before ffprobe
        _swap_salida(root, elsewhere)
        return result

    monkeypatch.setattr(qa_run, "check_edl_file", check)
    seen = spy_on_ffmpeg(monkeypatch)
    try:
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    finally:
        remove_dir_link(root / "salida")
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert seen == []  # not ffprobe: nothing was run on what is now somebody else's folder


def test_qa_relook_a_salida_that_changes_right_before_the_ear_stops_the_ear(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """001.49 point 2: with a transcript, after the last `run_detect` and right before the ear."""
    root = copy_of(built, tmp_path)
    plant_words(root)
    elsewhere = tmp_path / "otra carpeta"
    elsewhere.mkdir()
    heard: list[Path] = []

    def ear(_project: Any, video: Path, *_a: Any, **_k: Any) -> None:
        heard.append(video)  # the double of the ear: it is never to be called here

    monkeypatch.setattr(qa_run, "hear", ear)
    calls: list[list[str]] = []
    real_run = proc.run

    def run(args: list[str], **kwargs: Any) -> Any:
        calls.append(args)
        result = real_run(args, **kwargs)
        if len(calls) == 4:  # probe, loudness, black, freeze: the last tool before the ear
            _swap_salida(root, elsewhere)
        return result

    monkeypatch.setattr(proc, "run", run)
    try:
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    finally:
        remove_dir_link(root / "salida")
    assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
    assert len(calls) == 4 and heard == []


def test_qa_relook_the_size_in_the_report_is_the_one_taken_at_the_look_before_ffprobe(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """001.50 point 2: masked, the sheet never looks at `salida/` again, so a `salida/` that turns
    into a junction while the sheet is made must not change `file_mb`: the size is read at the
    look right before ffprobe and no `stat` of the video is made after it."""
    root = copy_of(built, tmp_path)
    real_bytes = (root / VIDEO).stat().st_size
    elsewhere = tmp_path / "otra carpeta"
    elsewhere.mkdir()
    real_sheet = qa_run.contact_sheet

    def sheet(*args: Any, **kwargs: Any) -> Any:
        _swap_salida(root, elsewhere)  # after the last tool that reads the video
        (elsewhere / "v1.mp4").write_bytes(b"\0" * (real_bytes + 2**20))  # 1 MB bigger
        return real_sheet(*args, **kwargs)

    monkeypatch.setattr(qa_run, "contact_sheet", sheet)
    try:
        code, doc, _ = kcut_json("qa", VIDEO, *project_args(root))
    finally:
        remove_dir_link(root / "salida")
    assert code == 0, doc
    assert doc["file_mb"] == round(real_bytes / 2**20, 1), doc
    assert doc["file_mb"] != round((real_bytes + 2**20) / 2**20, 1)
