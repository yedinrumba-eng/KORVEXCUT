"""The folders of the graphics are looked at before each write (spec S1.6b round 1, 001.31 point 2;
row 20): `gfx/`, `gfx/stills/` and `gfx/stills_work/` pass through `assert_own_folder` before they
are made and again right before `page.html`, each PNG of a frame, `index.json` and each still; with
`--out`, `_target` is repeated before each still.

A capture takes minutes, and in the middle one of those folders can be changed for a junction. The
tests do that on purpose, in process, with a `Shooter` that has no Chromium (`fake_shooter.py`) and
a hook at the moment that matters: what is outside stays empty, and `transcripts/` stays as it was.
"""

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kcut.commands import graphics_capture
from kcut.gfx import capture as gfx_capture
from tests.fixtures.links import make_dir_link, remove_dir_link
from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import write_graphics_v1
from tests.integration.fake_shooter import Hooks, install_fake_shooter
from tests.integration.graphics_helpers import plant_words, tree_hash
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
__all__ = ["small", "small_base"]
BUILD = ".kcut/build/v1"
MESSAGE = "es un archivo; kcut espera una carpeta"


def _label_doc(start: int = 3, end: int = 9) -> dict[str, Any]:
    cue = {"id": "x", "component": "label", "start": start, "end": end, "params": {"text": "x"}}
    return {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}


def _write(root: Path, document: dict[str, Any]) -> None:
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def stills_project(view_fresh: Path) -> Path:
    """The synthetic project with the example EDL, a transcript and the fixture graphics: the
    one `graphics still` is run on (it needs the proxy of a1)."""
    write_edl_v1(view_fresh)
    plant_words(view_fresh)
    write_graphics_v1(view_fresh, False)
    return view_fresh


@pytest.fixture
def outside(tmp_path: Path) -> Path:
    folder = tmp_path / "ajeno"
    folder.mkdir()
    return folder


def _swap(folder: Path, target: Path) -> Callable[[], None]:
    """A hook that puts a junction to `target` where `folder` is (the folder is kept beside it)."""

    def swap() -> None:
        folder.rename(folder.with_name(f"{folder.name}-real"))
        make_dir_link(folder, target)

    return swap


def _unlink(folder: Path) -> None:
    remove_dir_link(folder)
    real = folder.with_name(f"{folder.name}-real")
    if real.exists() and not folder.exists():
        real.rename(folder)


def _planted_transcripts(root: Path) -> tuple[Path, str]:
    """`.kcut/transcripts/` with one more file in it, and a hash of its names and bytes."""
    folder = root / ".kcut" / "transcripts"
    folder.mkdir(exist_ok=True)
    (folder / "keep-me.json").write_text('{"keep": "me"}', encoding="utf-8")
    return folder, tree_hash(folder)


class TestCapture:
    def test_gfx_own_folder_gfx_as_a_junction_to_transcripts_is_exit_3_and_they_stay(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The case of the verifier: the `index.json` of the capture landed over the one of
        `transcripts/`."""
        _write(small, _label_doc())
        transcripts, before = _planted_transcripts(small)
        hooks = install_fake_shooter(monkeypatch)
        build = small / BUILD
        make_dir_link(build / "gfx", transcripts)
        try:
            code, doc, _ = kcut_json("graphics", "capture", *project_args(small))
        finally:
            remove_dir_link(build / "gfx")
        assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        assert tree_hash(transcripts) == before
        assert hooks.started == 0 and hooks.shot == []

    @pytest.mark.parametrize("when", ["page", "png", "index"])
    def test_gfx_own_folder_gfx_changed_for_a_junction_during_the_capture_is_exit_3(
        self,
        small: Path,
        kcut_json: Run,
        monkeypatch: pytest.MonkeyPatch,
        outside: Path,
        when: str,
    ) -> None:
        """Before `page.html`, after the first PNG, and before `index.json`: each write looks again,
        so nothing is written through the link."""
        _write(small, _label_doc())
        gfx = small / BUILD / "gfx"
        swap = _swap(gfx, outside)
        if when == "page":
            install_fake_shooter(monkeypatch, Hooks(on_init=swap))
        elif when == "png":
            install_fake_shooter(monkeypatch, Hooks(on_png=lambda n: swap() if n == 1 else None))
        else:
            install_fake_shooter(monkeypatch)
            real = gfx_capture.capture

            def then_swap(*args: Any, **kwargs: Any) -> list[int]:
                kept = real(*args, **kwargs)
                swap()
                return kept

            monkeypatch.setattr(gfx_capture, "capture", then_swap)
        try:
            code, doc, _ = kcut_json("graphics", "capture", *project_args(small))
        finally:
            _unlink(gfx)
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (when, doc)
        assert list(outside.iterdir()) == [], when

    def test_gfx_own_folder_gfx_that_is_a_file_is_exit_3_with_the_message_and_not_10(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small, _label_doc())
        install_fake_shooter(monkeypatch)
        (small / BUILD / "gfx").write_text("not a folder", encoding="utf-8")
        code, doc, _ = kcut_json("graphics", "capture", *project_args(small))
        assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        assert MESSAGE in doc["error"]["message"]
        assert (small / BUILD / "gfx").read_text(encoding="utf-8") == "not a folder"

    def test_gfx_own_folder_the_render_with_gfx_as_a_file_is_exit_3_too(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small, _label_doc())
        install_fake_shooter(monkeypatch)
        (small / BUILD / "gfx").write_text("not a folder", encoding="utf-8")
        code, doc, _ = kcut_json("render", *project_args(small))
        assert code == 3 and MESSAGE in doc["error"]["message"], doc


class TestStill:
    def test_gfx_own_folder_stills_as_a_junction_to_transcripts_is_exit_3_and_they_stay(
        self, stills_project: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        transcripts, before = _planted_transcripts(stills_project)
        install_fake_shooter(monkeypatch)
        gfx = stills_project / BUILD / "gfx"
        gfx.mkdir(parents=True, exist_ok=True)
        make_dir_link(gfx / "stills", transcripts)
        try:
            args = ("graphics", "still", "60", *project_args(stills_project))
            code, doc, _ = kcut_json(*args)
        finally:
            remove_dir_link(gfx / "stills")
        assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        assert tree_hash(transcripts) == before

    def test_gfx_own_folder_stills_changed_for_a_junction_after_the_first_still_is_exit_3(
        self,
        stills_project: Path,
        kcut_json: Run,
        monkeypatch: pytest.MonkeyPatch,
        outside: Path,
    ) -> None:
        install_fake_shooter(monkeypatch)
        stills = stills_project / BUILD / "gfx" / "stills"
        swap = _swap(stills, outside)
        written: list[Path] = []
        real = graphics_capture.write_bytes_atomic

        def after_first(path: Path, data: bytes, **kwargs: Any) -> None:
            real(path, data, **kwargs)
            written.append(path)
            if len(written) == 1:
                swap()

        monkeypatch.setattr(graphics_capture, "write_bytes_atomic", after_first)
        try:
            args = ("graphics", "still", "60", "85", *project_args(stills_project))
            code, doc, _ = kcut_json(*args)
        finally:
            _unlink(stills)
        assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        assert len(written) == 1 and list(outside.iterdir()) == []

    def test_gfx_own_folder_the_out_folder_changed_for_a_junction_after_the_first_still_is_exit_3(
        self,
        stills_project: Path,
        kcut_json: Run,
        monkeypatch: pytest.MonkeyPatch,
        outside: Path,
    ) -> None:
        """`--out` goes through `assert_writable` for each still, not once before the first."""
        install_fake_shooter(monkeypatch)
        target = stills_project / "qa" / "vistas"
        swap = _swap(target, outside)
        written: list[Path] = []
        real = graphics_capture.write_bytes_atomic

        def after_first(path: Path, data: bytes, **kwargs: Any) -> None:
            real(path, data, **kwargs)
            written.append(path)
            if len(written) == 1:
                swap()

        monkeypatch.setattr(graphics_capture, "write_bytes_atomic", after_first)
        try:
            args = ("graphics", "still", "60", "85", "--out", "qa/vistas")
            code, doc, _ = kcut_json(*args, *project_args(stills_project))
        finally:
            _unlink(target)
        assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        assert len(written) == 1 and list(outside.iterdir()) == []

    def test_gfx_own_folder_stills_work_changed_for_a_junction_while_it_is_made_is_exit_3(
        self,
        stills_project: Path,
        kcut_json: Run,
        monkeypatch: pytest.MonkeyPatch,
        outside: Path,
    ) -> None:
        work = stills_project / BUILD / "gfx" / "stills_work"
        swap = _swap(work, outside)
        install_fake_shooter(monkeypatch, Hooks(on_png=lambda n: swap() if n == 1 else None))
        try:
            args = ("graphics", "still", "60", "85", *project_args(stills_project))
            code, doc, _ = kcut_json(*args)
        finally:
            _unlink(work)
        assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        assert list(outside.iterdir()) == []

    @pytest.mark.parametrize("which", ["gfx", "stills_work"])
    def test_gfx_own_folder_a_file_where_the_folder_goes_is_exit_3_with_the_message_not_10(
        self,
        stills_project: Path,
        kcut_json: Run,
        monkeypatch: pytest.MonkeyPatch,
        which: str,
    ) -> None:
        install_fake_shooter(monkeypatch)
        gfx = stills_project / BUILD / "gfx"
        gfx.parent.mkdir(parents=True, exist_ok=True)
        if which == "gfx":
            blocker = gfx
        else:
            gfx.mkdir(exist_ok=True)
            blocker = gfx / "stills_work"
        blocker.write_text("not a folder", encoding="utf-8")
        code, doc, _ = kcut_json("graphics", "still", "60", *project_args(stills_project))
        assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        assert MESSAGE in doc["error"]["message"]
        assert blocker.read_text(encoding="utf-8") == "not a folder"
        assert os.path.isfile(blocker)
