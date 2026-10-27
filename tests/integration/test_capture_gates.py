"""The refusals of `kcut graphics capture` and of the graphics of `kcut render` (spec S1.6b): the
lock of the output (exit 6), an image that nobody approved (G10, exit 5), errors in the graphics
(exit 1), and a document that has nothing visible (no frame to capture, so no Chromium) but is not
empty.
"""

import json
from pathlib import Path
from typing import Any

import playwright.sync_api as sync_api
import pytest

from kcut.gfx.components import COMPONENTS
from kcut.gfx.components_base import TITLE, ComponentDef
from kcut.params import ParamSpec
from kcut.render.lock import OutputLock
from tests.integration.graphics_helpers import plant_words
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
__all__ = ["small", "small_base"]
BUILD = ".kcut/build/v1"
WORDS = [("Llama", 2100, 2400), ("ya", 2500, 2800), ("gracias", 2900, 3200)]


def _write(root: Path, document: dict[str, Any]) -> None:
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


def _no_chromium(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("se lanzó Chromium"))


def test_capture_gates_a_lock_that_is_held_is_exit_6(small: Path, kcut_json: Run) -> None:
    with OutputLock(small / ".kcut" / "locks", "build-v1"):
        code, doc, _ = kcut_json("graphics", "capture", *project_args(small))
    assert code == 6 and doc["error"]["kind"] == "LockedError"
    assert not (small / BUILD / "gfx").exists()


def test_capture_gates_the_lock_is_the_one_of_the_render(small: Path, kcut_json: Run) -> None:
    """`graphics capture` and `render` share `build-vN`: one holds it, the other is refused."""
    with OutputLock(small / ".kcut" / "locks", "build-v1"):
        code, doc, _ = kcut_json("render", *project_args(small))
    assert code == 6 and doc["error"]["kind"] == "LockedError"


@pytest.mark.parametrize("command", ["capture", "render"])
def test_capture_gates_an_image_that_nobody_approved_is_exit_5_before_anything(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    picture = ComponentDef(
        "picture", TITLE.js_files, False, (ParamSpec("image", "path", True),),
        "Imagen", "una imagen aprobada", "nada", "bajo", "", "test",
    )  # fmt: skip
    monkeypatch.setitem(COMPONENTS, "picture", picture)
    (small / "recursos").mkdir(exist_ok=True)
    (small / "recursos" / "logo.png").write_bytes(b"not even a picture")
    cue = {"id": "foto", "component": "picture", "start": 0, "end": 30}
    _write(
        small,
        {
            "schema": "kcut.graphics/1",
            "captions": {"enabled": False},
            "cues": [{**cue, "params": {"image": "recursos/logo.png"}}],
        },
    )
    _no_chromium(monkeypatch)
    args = ("graphics", "capture") if command == "capture" else ("render",)
    code, doc, _ = kcut_json(*args, *project_args(small))
    assert code == 5 and doc["error"]["kind"] == "GateError" and "G10" in doc["error"]["message"]
    assert not (small / BUILD / "gfx").exists()


@pytest.mark.parametrize("command", ["capture", "render"])
def test_capture_gates_playwright_start_that_fails_is_exit_7_and_not_10(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """001.31 point 11: the driver of Playwright that does not start is a MissingDependency."""
    from types import SimpleNamespace

    def start() -> Any:
        raise sync_api.Error("the driver of Playwright did not start")

    _write(
        small,
        {
            "schema": "kcut.graphics/1",
            "captions": {"enabled": False},
            "cues": [
                {"id": "x", "component": "label", "start": 5, "end": 20, "params": {"text": "x"}}
            ],
        },
    )
    monkeypatch.setattr(sync_api, "sync_playwright", lambda: SimpleNamespace(start=start))
    args = ("graphics", "capture") if command == "capture" else ("render",)
    code, doc, _ = kcut_json(*args, *project_args(small))
    assert code == 7 and doc["error"]["kind"] == "MissingDependency", doc
    assert "kcut doctor" in doc["error"]["message"]


def test_capture_gates_errors_in_the_graphics_are_exit_1_and_name_the_code(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        small,
        {
            "schema": "kcut.graphics/1",
            "captions": {"enabled": False},
            "cues": [{"id": "x", "component": "label", "start": 5, "end": 999,
                      "params": {"text": "x"}}],
        },
    )  # fmt: skip
    _no_chromium(monkeypatch)
    code, doc, _ = kcut_json("render", *project_args(small))
    assert code == 1 and doc["error"]["kind"] == "CheckFailed"
    assert "1 errores (G07)" in doc["error"]["message"] and "kcut graphics check" in doc["error"][
        "message"]  # fmt: skip


def test_capture_gates_subtitles_with_no_transcript_are_g08_exit_1_in_the_render(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default captions need the transcript: a render without `--no-graphics` and without it
    is exit 1 with G08 (that is why the tests of S1.5b run with `--no-graphics`)."""
    _no_chromium(monkeypatch)
    code, doc, _ = kcut_json("render", *project_args(small))
    assert code == 1 and doc["error"]["kind"] == "CheckFailed" and "G08" in doc["error"]["message"]


def test_capture_gates_a_document_with_nothing_visible_has_no_frames_and_no_chromium(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Captions on, but every window of the video hidden: it is not `empty` (the subtitles are on)
    but no frame can have anything drawn. The index is written with no frames, Chromium is not
    started, and a render with it is the picture without graphics."""
    plant_words(small, WORDS)
    _write(
        small,
        {"schema": "kcut.graphics/1", "captions": {"enabled": True,
         "hide": [{"start": 0, "end": 60}]}, "cues": []},
    )  # fmt: skip
    _no_chromium(monkeypatch)
    code, doc, err = kcut_json("graphics", "capture", *project_args(small))
    assert code == 0 and doc["frames"] == 0 and doc["captured"] is True, (doc, err)
    index = json.loads((small / BUILD / "gfx" / "index.json").read_text(encoding="utf-8"))
    assert index["frames"] == [] and index["fps"] == 30
    code, doc, err = kcut_json("graphics", "capture", *project_args(small))
    assert code == 0 and doc["captured"] is False  # the index with no frames is a valid one
    code, doc, err = kcut_json("render", *project_args(small))
    assert code == 0 and doc["ok"] is True, (doc, err)


def test_capture_gates_nothing_to_draw_writes_nothing_and_says_so(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    toml = small / "kcut.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(
        text.replace("[captions]\nenabled = true", "[captions]\nenabled = false"),
        encoding="utf-8",
        newline="\n",
    )
    _no_chromium(monkeypatch)
    code, doc, err = kcut_json("graphics", "capture", *project_args(small))
    assert code == 0 and doc["ok"] is True, (doc, err)
    assert doc["frames"] == 0 and doc["captured"] is False and doc["index"] is None
    assert [w["code"] for w in doc["warnings"]] == ["G12"]
    assert not (small / BUILD / "gfx").exists()


def test_capture_gates_an_edl_with_errors_is_exit_1_with_the_e_codes(
    small: Path, kcut_json: Run
) -> None:
    path = small / "edit" / "edl-v1.json"
    edl = json.loads(path.read_text(encoding="utf-8"))
    edl["frames"] = 61
    path.write_text(json.dumps(edl), encoding="utf-8")
    code, doc, _ = kcut_json("graphics", "capture", *project_args(small))
    assert code == 1 and doc["error"]["kind"] == "CheckFailed" and "E08" in doc["error"]["message"]


def test_capture_gates_a_build_folder_that_is_a_link_is_refused(
    small: Path, kcut_json: Run
) -> None:
    """`build/v1` as a link (even to somewhere inside `.kcut/`) is refused like `render` refuses
    it: nothing is captured through it."""
    from tests.fixtures.links import make_dir_link, remove_dir_link

    _write(
        small,
        {
            "schema": "kcut.graphics/1",
            "captions": {"enabled": False},
            "cues": [
                {"id": "x", "component": "label", "start": 5, "end": 20, "params": {"text": "x"}}
            ],
        },
    )
    folder = small / ".kcut" / "build" / "v1"
    real = folder.with_name("v1-real")
    folder.rename(real)
    make_dir_link(folder, small / ".kcut")
    try:
        code, doc, _ = kcut_json("graphics", "capture", *project_args(small))
    finally:
        remove_dir_link(folder)
    assert code == 3 and "enlace" in doc["error"]["message"]
    assert not (small / ".kcut" / "gfx").exists()
