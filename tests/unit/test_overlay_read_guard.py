"""The layer of the graphics looks right before it reads and before it deletes (spec S1.6b round 2,
001.32 point 8; row 39). `OverlaySource` looks at each PNG with `lone_file_reason(os.lstat(path))`
just before reading it: a PNG that is no longer a regular file with one name is a ProjectError (exit
3) that says it changed during the render, and its content is not used. `layer._clear` calls the
guard before each `unlink` and not once before the list.
"""

import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from kcut.errors import ProjectError
from kcut.gfx.capture_index import INDEX_NAME, png_name
from kcut.gfx.layer import _clear
from kcut.gfx.overlay import OverlaySource
from tests.fixtures.links import make_hard_link

W, H = 12, 8
CHANGED = (
    "el PNG del frame {f} de la capa de gráficos cambió durante el render; "
    "corre kcut graphics capture --force"
)


def _png(path: Path, bgra: np.ndarray) -> None:
    done, data = cv2.imencode(".png", bgra)
    assert done
    path.write_bytes(data.tobytes())


def _red() -> np.ndarray:
    over = np.zeros((H, W, 4), np.uint8)
    over[:, :, :3], over[:, :, 3] = (0, 0, 255), 255
    return over


def _source(folder: Path, frames: list[int]) -> OverlaySource:
    index = folder / INDEX_NAME
    index.write_text(json.dumps({"fps": 30, "frames": frames, "hash": "a" * 64}), encoding="utf-8")
    return OverlaySource(index, W, H)


def _blend(source: OverlaySource, f: int) -> None:
    source.blend(np.zeros((H, W, 3), np.uint8), f)


def test_gfx_read_guard_a_png_that_became_a_hard_link_is_refused_and_its_content_not_used(
    tmp_path: Path,
) -> None:
    (tmp_path / "gfx").mkdir()
    folder = tmp_path / "gfx"
    _png(folder / png_name(3), _red())
    source = _source(folder, [3])  # the index is read and valid here
    outside = tmp_path / "ajeno.png"
    _png(outside, _red())
    (folder / png_name(3)).unlink()
    make_hard_link(folder / png_name(3), outside)
    assert os.stat(outside).st_nlink == 2
    with pytest.raises(ProjectError) as info:
        _blend(source, 3)
    assert info.value.exit_code == 3 and info.value.message_es == CHANGED.format(f=3)


def test_gfx_read_guard_a_png_that_became_a_folder_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "gfx"
    folder.mkdir()
    _png(folder / png_name(5), _red())
    source = _source(folder, [5])
    (folder / png_name(5)).unlink()
    (folder / png_name(5)).mkdir()
    with pytest.raises(ProjectError) as info:
        _blend(source, 5)
    assert info.value.exit_code == 3 and info.value.message_es == CHANGED.format(f=5)


def test_gfx_read_guard_each_png_is_looked_at_when_it_is_read_not_when_the_source_is_made(
    tmp_path: Path,
) -> None:
    """The first PNG is fine and is blended; the second is changed after that and is refused."""
    folder = tmp_path / "gfx"
    folder.mkdir()
    for f in (1, 2):
        _png(folder / png_name(f), _red())
    source = _source(folder, [1, 2])
    _blend(source, 1)  # all right
    outside = tmp_path / "ajeno.png"
    _png(outside, _red())
    (folder / png_name(2)).unlink()
    make_hard_link(folder / png_name(2), outside)
    _blend(source, 1)  # the one that was not touched still goes
    with pytest.raises(ProjectError, match="el PNG del frame 2 de la capa"):
        _blend(source, 2)


def test_gfx_read_guard_a_png_that_is_missing_is_still_the_damaged_message(tmp_path: Path) -> None:
    folder = tmp_path / "gfx"
    folder.mkdir()
    source = _source(folder, [4])  # the PNG of frame 4 was never there
    with pytest.raises(ProjectError) as info:
        _blend(source, 4)
    assert info.value.message_es == (
        "el gráfico 4 de la caché está dañado; corre kcut graphics capture --force"
    )


def test_gfx_read_guard_a_png_with_one_name_is_read_as_before(tmp_path: Path) -> None:
    folder = tmp_path / "gfx"
    folder.mkdir()
    _png(folder / png_name(7), _red())
    source = _source(folder, [7])
    base = np.full((H, W, 3), 50, np.uint8)
    assert np.array_equal(source.blend(base, 7), np.full((H, W, 3), (0, 0, 255), np.uint8))


def _layer_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "gfx"
    folder.mkdir()
    for name in ("000001.png", "000002.png", "000003.png", INDEX_NAME):
        (folder / name).write_bytes(b"x")
    (folder / "stills").mkdir()  # a folder in it is not the layer's: it stays
    return folder


def test_gfx_read_guard_clear_calls_the_guard_right_before_each_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _layer_folder(tmp_path)
    events: list[str] = []
    real_unlink = Path.unlink

    def unlink(self: Path, *args: object, **kwargs: object) -> None:
        events.append(f"unlink {self.name}")
        real_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", unlink)
    _clear(lambda: events.append("guard"), folder)
    monkeypatch.undo()
    unlinks = [i for i, event in enumerate(events) if event.startswith("unlink ")]
    assert len(unlinks) == 4
    assert all(events[i - 1] == "guard" for i in unlinks), events  # each one has its own look
    assert sorted(p.name for p in folder.iterdir()) == ["stills"]


def test_gfx_read_guard_clear_stops_at_the_guard_that_says_no_and_deletes_nothing_more(
    tmp_path: Path,
) -> None:
    folder = _layer_folder(tmp_path)
    looks = {"n": 0}

    def guard() -> None:
        looks["n"] += 1
        if looks["n"] == 4:  # the first is before the list, the next ones before each unlink
            raise ProjectError("la carpeta de gráficos cambió")

    with pytest.raises(ProjectError, match="cambió"):
        _clear(guard, folder)
    left = sorted(p.name for p in folder.iterdir())
    assert len(left) == 3  # `stills` and two of the four: two went (looks 2 and 3), then it stopped
    assert "stills" in left
