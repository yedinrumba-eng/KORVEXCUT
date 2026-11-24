"""The contact sheet of `kcut qa` takes the graphics of the snapshot, not the ones of `edit/` (spec
001.51 point 4, row 29; 001.40 point 3).

When the EDL `kcut qa` judges is the copy of the build (`qa/vN/inputs/edl-vN.json`), the graphics
of the sheet are `qa/vN/inputs/graphics.json`; a snapshot without that file means the implicit
document, never `edit/graphics.json`. Without a snapshot they are `edit/graphics.json`. Chromium is
a double (`install_solid_layer`); a spy on `resolve` says which document was read.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from kcut.gfx.resolve import ResolvedGraphics
from kcut.qa import contact_gfx
from tests.fixtures.synth_graphics import write_graphics_v1
from tests.integration.qa_contact_helpers import install_solid_layer
from tests.integration.qa_helpers import VIDEO, built, copy_of
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["built"]
pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
SNAPSHOT = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": []}


def _spy(monkeypatch: pytest.MonkeyPatch) -> list[ResolvedGraphics]:
    """Wrap `resolve` as the contact sheet calls it, and keep what it gave."""
    real = contact_gfx.resolve
    seen: list[ResolvedGraphics] = []

    def resolve(*args: Any, **kwargs: Any) -> ResolvedGraphics:
        seen.append(real(*args, **kwargs))
        return seen[-1]

    monkeypatch.setattr(contact_gfx, "resolve", resolve)
    install_solid_layer(monkeypatch)
    return seen


def _project(built: Path, tmp_path: Path, snapshot: dict[str, object] | None) -> Path:
    """A copy of the built project with the EDL snapshot, and its `graphics.json` if given."""
    root = copy_of(built, tmp_path)
    write_graphics_v1(root)  # the one of `edit/`: four cues and the subtitles on
    folder = root / "qa" / "v1" / "inputs"
    folder.mkdir(parents=True)
    shutil.copy2(root / "edit" / "edl-v1.json", folder / "edl-v1.json")
    if snapshot is not None:
        (folder / "graphics.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return root


def test_contact_snapshot_graphics_the_sheet_reads_the_graphics_of_the_snapshot(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(built, tmp_path, SNAPSHOT)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0, (doc, err)
    assert len(seen) == 1 and seen[0].source == "file"
    assert seen[0].cues == () and seen[0].captions is False  # the snapshot's, not the one of edit/


def test_contact_snapshot_graphics_a_snapshot_without_graphics_is_the_implicit_document(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(built, tmp_path, None)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0, (doc, err)
    assert len(seen) == 1 and seen[0].source == "default" and seen[0].cues == ()


def test_contact_snapshot_graphics_without_a_snapshot_it_is_edit_graphics_json(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    write_graphics_v1(root)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0, (doc, err)
    assert len(seen) == 1 and seen[0].source == "file" and len(seen[0].cues) > 0


def test_contact_snapshot_graphics_unreadable_snapshot_warning_names_the_snapshot(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(built, tmp_path, None)
    (root / "qa" / "v1" / "inputs" / "graphics.json").write_text("{ 972 808", encoding="utf-8")
    _spy(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0, (doc, err)  # 001.52
    messages = [w["message_es"] for w in doc["warnings"] if w["code"] == "contact_skipped"]
    assert len(messages) == 1
    assert messages[0].startswith("qa/v1/inputs/graphics.json no se puede leer")
    assert "edit/graphics.json" not in messages[0]


def test_contact_snapshot_graphics_graphics_json_is_the_path_that_was_read(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(built, tmp_path, SNAPSHOT)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0, (doc, err)
    assert seen[0].graphics_json == "qa/v1/inputs/graphics.json"  # 001.52
    other = _project(built, tmp_path / "other", None)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(other))
    assert code == 0, (doc, err)
    assert seen[0].graphics_json is None  # the implicit document


def test_contact_snapshot_graphics_json_without_a_snapshot_is_edit_graphics_json(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    write_graphics_v1(root)
    seen = _spy(monkeypatch)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0, (doc, err)
    assert seen[0].graphics_json == "edit/graphics.json"  # 001.52
