"""The room that the graphics layer asks of the disk (spec S1.6b round 1, 001.31 point 5; row 23):
`GFX_FRAME_BYTES = 192 * 1024` for each frame that is going to be drawn (`active_frames`), and 0 if
the layer of the cache is reused (same hash and a valid index) or if there is nothing to draw. The
message gives the figures before the path (001.30 point 4). Chromium is a double (`_Calls`).
"""

import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from kcut.audio.voice_track import SPARE_BYTES, require_disk_space
from kcut.errors import ProjectError
from kcut.gfx import capture as gfx_capture
from kcut.gfx.layer import GFX_FRAME_BYTES, ensure_layer, layer_bytes, require_layer_space
from kcut.gfx.resolve_cues import ResolvedCue
from kcut.project import Project
from tests.unit.edl_fakes import parsed
from tests.unit.gfx_resolve_fakes import make_project
from tests.unit.test_layer import _Calls, _resolved

VOICE = 345 * 1600 * 4  # the voice track of the example EDL: 345 frames at 30 fps


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


@pytest.fixture
def build(project: Project) -> Path:
    return project.layout.build_dir(1)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> _Calls:
    double = _Calls()
    monkeypatch.setattr(gfx_capture, "capture", double)
    return double


def _free(monkeypatch: pytest.MonkeyPatch, free: int) -> None:
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: usage(10**12, 0, free))


def test_gfx_limits_disk_a_frame_is_192_kib() -> None:
    assert GFX_FRAME_BYTES == 192 * 1024 == 196_608


def test_gfx_limits_disk_the_layer_asks_for_192_kib_for_each_active_frame(
    project: Project, build: Path
) -> None:
    resolved = _resolved((ResolvedCue("a", "label", 3, 6, {}), ResolvedCue("b", "label", 5, 8, {})))
    assert layer_bytes(project, resolved, build, force=False) == 5 * GFX_FRAME_BYTES  # 3..7


def test_gfx_limits_disk_nothing_to_draw_asks_for_nothing(project: Project, build: Path) -> None:
    assert layer_bytes(project, _resolved(empty=True), build, force=False) == 0
    assert layer_bytes(project, _resolved((), captions=True), build, force=False) == 0  # no frame


def test_gfx_limits_disk_a_layer_in_the_cache_asks_for_nothing_unless_it_is_forced(
    project: Project, build: Path, calls: _Calls
) -> None:
    resolved = _resolved()
    assert layer_bytes(project, resolved, build, force=False) == 3 * GFX_FRAME_BYTES
    ensure_layer(project, resolved, build, force=False, notices=[])
    assert layer_bytes(project, resolved, build, force=False) == 0  # the same page, a good index
    assert layer_bytes(project, resolved, build, force=True) == 3 * GFX_FRAME_BYTES
    moved = _resolved((ResolvedCue("pill", "label", 10, 14, {"text": "x"}),))
    assert layer_bytes(project, moved, build, force=False) == 4 * GFX_FRAME_BYTES  # another page


def test_gfx_limits_disk_an_index_that_is_not_valid_does_not_count_as_a_layer_in_the_cache(
    project: Project, build: Path, calls: _Calls
) -> None:
    resolved = _resolved()
    ensure_layer(project, resolved, build, force=False, notices=[])
    (build / "gfx" / "000003.png").unlink()  # the index says it is there
    assert layer_bytes(project, resolved, build, force=False) == 3 * GFX_FRAME_BYTES


def test_gfx_limits_disk_the_message_of_the_layer_has_the_figures_before_the_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layer = 7 * GFX_FRAME_BYTES
    _free(monkeypatch, SPARE_BYTES + layer - 1000)
    with pytest.raises(ProjectError) as info:
        require_layer_space(tmp_path, layer)
    needed, free = SPARE_BYTES + layer, SPARE_BYTES + layer - 1000
    assert info.value.exit_code == 3
    assert info.value.message_es == (
        f"no hay espacio en el disco: faltan 1000 bytes (la capa de gráficos y 1 GiB libre piden "
        f"{needed}, hay {free}) en {tmp_path}"
    )


def test_gfx_limits_disk_enough_room_and_no_layer_to_make_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _free(monkeypatch, SPARE_BYTES + 5 * GFX_FRAME_BYTES)
    require_layer_space(tmp_path, 5 * GFX_FRAME_BYTES)  # exactly what it asks
    _free(monkeypatch, 0)
    require_layer_space(tmp_path, 0)  # nothing to make: nothing is asked, not even the gigabyte


def test_gfx_limits_disk_the_voice_check_with_a_layer_says_voice_layer_and_the_gigabyte(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layer = 9 * GFX_FRAME_BYTES
    needed = VOICE + layer + SPARE_BYTES
    _free(monkeypatch, VOICE + SPARE_BYTES + 5)  # enough for the voice, 5 bytes over
    with pytest.raises(ProjectError) as info:
        require_disk_space(tmp_path, parsed(), layer_bytes=layer)
    assert info.value.message_es == (
        f"no hay espacio en el disco: faltan {needed - (VOICE + SPARE_BYTES + 5)} bytes (la voz "
        f"del corte, la capa de gráficos y 1 GiB libre piden {needed}, hay "
        f"{VOICE + SPARE_BYTES + 5}) en {tmp_path}"
    )


def test_gfx_limits_disk_the_voice_check_without_a_layer_is_the_message_of_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    needed = VOICE + SPARE_BYTES
    _free(monkeypatch, needed - 1)
    for kwargs in ({}, {"layer_bytes": 0}):
        with pytest.raises(ProjectError) as info:
            require_disk_space(tmp_path, parsed(), **kwargs)
        assert info.value.message_es == (
            f"no hay espacio en el disco: faltan 1 bytes (la voz del corte y 1 GiB libre piden "
            f"{needed}, hay {needed - 1}) en {tmp_path}"
        )
    _free(monkeypatch, needed)
    require_disk_space(tmp_path, parsed(), layer_bytes=0)  # as before: passes with what it asked
