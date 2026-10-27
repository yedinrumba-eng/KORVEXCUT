"""The limits of the graphics commands (spec S1.6b round 1, 001.31 point 5; row 23):

- `graphics still` makes at most `MAX_STILLS = 60` different frames in a call; more is a UsageError
  (exit 2) before Chromium starts.
- `graphics still` takes the lock `build-vN` like `capture` (both use `gfx/`).
- `render` and `graphics capture` add the layer that is going to be captured to the check of the
  disk (`GFX_FRAME_BYTES` for each active frame; 0 if the layer of the cache is reused or there is
  nothing to draw), with the figures before the path.

Chromium is the `Shooter` of `fake_shooter.py`; the disk is `shutil.disk_usage`, patched.
"""

import json
import shutil
from collections import namedtuple
from pathlib import Path
from typing import Any

import playwright.sync_api as sync_api
import pytest

from kcut.audio.voice_track import SPARE_BYTES
from kcut.errors import LockedError
from kcut.gfx.layer import GFX_FRAME_BYTES
from kcut.render.lock import OutputLock
from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import write_graphics_v1
from tests.integration.fake_shooter import Hooks, install_fake_shooter
from tests.integration.graphics_helpers import plant_words
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
__all__ = ["small", "small_base"]
BUILD = ".kcut/build/v1"
VOICE = 60 * 1600 * 4  # the voice of the small EDL: 60 frames at 30 fps
LAYER = 30 * GFX_FRAME_BYTES  # the label of `_write` is on at frames 10 to 39
MESSAGE_2 = "graphics still hace hasta 60 frames por llamada; pide menos"


def _write(root: Path, *, enabled: bool = False) -> None:
    cue = {"id": "x", "component": "label", "start": 10, "end": 40, "params": {"text": "x"}}
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": enabled}, "cues": [cue]}
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


def _disk(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage(10**12, 10**12 - free, free))


@pytest.fixture
def stills_project(view_fresh: Path) -> Path:
    write_edl_v1(view_fresh)
    plant_words(view_fresh)
    write_graphics_v1(view_fresh, False)
    return view_fresh


class TestRenderAndCapture:
    def test_gfx_limits_disk_a_render_with_graphics_asks_for_the_voice_and_the_layer(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small)
        hooks = install_fake_shooter(monkeypatch)
        free = SPARE_BYTES + VOICE + 1_000_000  # the voice fits; the layer (5.6 MiB) does not
        _disk(monkeypatch, free)
        code, doc, err = kcut_json("render", *project_args(small))
        needed = VOICE + LAYER + SPARE_BYTES
        head = (
            f"no hay espacio en el disco: faltan {needed - free} bytes (la voz del corte, la capa "
            f"de gráficos y 1 GiB libre piden {needed}, hay {free}) en "
        )
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        assert doc["error"]["message"].startswith(head), doc["error"]["message"]
        assert hooks.started == 0 and not (small / BUILD / "gfx").exists()

    def test_gfx_limits_disk_the_same_render_without_graphics_passes_the_check(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small)
        _disk(monkeypatch, SPARE_BYTES + VOICE + 1_000_000)
        code, doc, err = kcut_json("render", "--no-graphics", *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)

    def test_gfx_limits_disk_with_the_layer_in_the_cache_the_same_disk_is_enough(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small)
        install_fake_shooter(monkeypatch)
        assert kcut_json("graphics", "capture", *project_args(small))[0] == 0  # the room is there
        _disk(monkeypatch, SPARE_BYTES + VOICE + 1_000_000)
        code, doc, err = kcut_json("render", *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)  # nothing to capture: it is not asked

    def test_gfx_limits_disk_a_render_with_nothing_to_draw_keeps_the_message_of_before(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = small / "kcut.toml"
        text = toml.read_text(encoding="utf-8")
        toml.write_text(
            text.replace("[captions]\nenabled = true", "[captions]\nenabled = false"),
            encoding="utf-8",
            newline="\n",
        )
        free = SPARE_BYTES + VOICE - 1000
        _disk(monkeypatch, free)
        code, doc, _ = kcut_json("render", *project_args(small))
        message = doc["error"]["message"]
        assert code == 3 and "(la voz del corte y 1 GiB libre piden" in message
        assert "capa" not in message and "faltan 1000 bytes" in message

    def test_gfx_limits_disk_graphics_capture_with_a_short_disk_is_exit_3_and_names_the_layer(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small)
        hooks = install_fake_shooter(monkeypatch)
        free = SPARE_BYTES + LAYER - 12345
        _disk(monkeypatch, free)
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        head = (
            f"no hay espacio en el disco: faltan 12345 bytes (la capa de gráficos y 1 GiB libre "
            f"piden {SPARE_BYTES + LAYER}, hay {free}) en "
        )
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        assert doc["error"]["message"].startswith(head), doc["error"]["message"]
        assert hooks.started == 0 and not (small / BUILD / "gfx" / "index.json").exists()

    def test_gfx_limits_disk_graphics_capture_with_the_layer_in_the_cache_asks_for_nothing(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small)
        install_fake_shooter(monkeypatch)
        assert kcut_json("graphics", "capture", *project_args(small))[0] == 0
        _disk(monkeypatch, 1000)  # a disk with no room at all
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["captured"] is False, (doc, err)
        code, doc, _ = kcut_json("graphics", "capture", "--force", *project_args(small))
        assert code == 3 and "la capa de gráficos y 1 GiB libre piden" in doc["error"]["message"]

    def test_gfx_limits_disk_graphics_capture_with_nothing_to_draw_asks_for_nothing(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = small / "kcut.toml"
        text = toml.read_text(encoding="utf-8")
        toml.write_text(
            text.replace("[captions]\nenabled = true", "[captions]\nenabled = false"),
            encoding="utf-8",
            newline="\n",
        )
        _disk(monkeypatch, 1000)
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["index"] is None, (doc, err)


class TestStill:
    def test_gfx_limits_disk_61_different_frames_is_exit_2_and_chromium_is_not_started(
        self, stills_project: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("se lanzó Chromium"))
        frames = [str(f) for f in range(61)]
        code, doc, _ = kcut_json("graphics", "still", *frames, *project_args(stills_project))
        assert code == 2 and doc["error"]["kind"] == "UsageError", doc
        assert doc["error"]["message"] == MESSAGE_2
        assert not (stills_project / BUILD / "gfx" / "stills").exists()

    def test_gfx_limits_disk_60_frames_pass_the_count_and_a_frame_asked_twice_is_one(
        self, stills_project: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The limit is of different frames: 120 arguments of 60 frames, or 60 frames, are fine
        (`--out crudo` stops them later, at exit 3, so that no 60 stills are made here)."""
        monkeypatch.setattr(sync_api, "sync_playwright", lambda: pytest.fail("se lanzó Chromium"))
        frames = [str(f) for f in range(60)]
        for given in (frames, frames + frames):
            args = ("graphics", "still", *given, "--out", "crudo", *project_args(stills_project))
            code, doc, _ = kcut_json(*args)
            assert code == 3 and doc["error"]["kind"] == "ProjectError", doc
        args = ("graphics", "still", *frames, "60", "--out", "crudo", *project_args(stills_project))
        code, doc, _ = kcut_json(*args)
        assert code == 2 and doc["error"]["message"] == MESSAGE_2

    def test_gfx_limits_disk_a_still_with_the_lock_taken_is_like_a_capture_with_it_taken(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small)
        install_fake_shooter(monkeypatch)
        with OutputLock(small / ".kcut" / "locks", "build-v1"):
            capture = kcut_json("graphics", "capture", *project_args(small))
            still = kcut_json("graphics", "still", "20", *project_args(small))
        assert capture[0] == still[0] == 6
        assert capture[1]["error"]["kind"] == still[1]["error"]["kind"] == "LockedError"
        assert capture[1]["error"]["message"] == still[1]["error"]["message"]
        assert not (small / BUILD / "gfx" / "stills").exists()
        assert not (small / BUILD / "gfx" / "stills_work").exists()

    def test_gfx_limits_disk_a_still_holds_the_lock_while_it_makes_the_frames(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small)
        taken: list[Any] = []

        def try_the_lock() -> None:
            try:
                with OutputLock(small / ".kcut" / "locks", "build-v1"):
                    taken.append("the lock was free")
            except LockedError as exc:
                taken.append(exc.exit_code)

        install_fake_shooter(monkeypatch, Hooks(on_init=try_the_lock))
        code, doc, err = kcut_json("graphics", "still", "20", *project_args(small))
        assert code == 0, (doc, err)
        assert taken == [6]  # while it worked, nobody else could take `build-v1`
        with OutputLock(small / ".kcut" / "locks", "build-v1"):  # and it let go at the end
            pass
