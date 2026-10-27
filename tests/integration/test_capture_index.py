"""The index of the graphics in the cache, through the commands (spec S1.6b row 6, 001.15).

`index.json` has the frames that have a PNG and the hash of the page they were made from: the same
page is not captured again (except with `--force`), and an index that is not valid (frames out of
order, a frame past the end of the video, a PNG that is missing, a hash that is not hex...) is
treated as if it were not there: the graphics are captured again, with the notice `cache_rebuilt`.
A PNG that is damaged when the render needs it is exit 3 and says how to make it again.
"""

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kcut.gfx import capture as gfx_capture
from tests.conftest import run_kcut
from tests.integration.render_small_cases import small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.chromium, pytest.mark.slow]
__all__ = ["small_base"]
GFX = ".kcut/build/v1/gfx"
Change = Callable[[dict[str, Any], Path], None]
GRAPHICS = {
    "schema": "kcut.graphics/1",
    "captions": {"enabled": False},
    "cues": [
        {
            "id": "pill",
            "component": "label",
            "start": 10,
            "end": 40,
            "params": {"text": "hecho con kcut", "y": 0.58},
        }
    ],
}


def _write(root: Path, document: dict[str, Any]) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    (root / "edit" / "graphics.json").write_text(text, encoding="utf-8", newline="\n")


def _index(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = json.loads((root / GFX / "index.json").read_text(encoding="utf-8"))
    return result


def _codes(doc: dict[str, Any]) -> list[str]:
    return [w["code"] for w in doc["warnings"]]


@pytest.fixture(scope="module")
def captured(tmp_path_factory: pytest.TempPathFactory, small_base: Path) -> Path:
    """The small project with one label cue, captured once (the index and the PNGs are there)."""
    root = tmp_path_factory.mktemp("capindex") / "proyecto ñandú"
    shutil.copytree(small_base, root)
    _write(root, GRAPHICS)
    done = run_kcut("graphics", "capture", "--project", str(root), "--json")
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["captured"] is True
    return root


@pytest.fixture
def root(captured: Path, tmp_path: Path) -> Path:
    """A copy of `captured` for one test."""
    copy = tmp_path / "proyecto ñandú"
    shutil.copytree(captured, copy)
    return copy


class _Calls:
    """Counts the calls to `capture` and lets them run."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.count = 0
        real = gfx_capture.capture

        def counting(*args: Any, **kwargs: Any) -> list[int]:
            self.count += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(gfx_capture, "capture", counting)


def test_capture_index_the_first_capture_writes_the_pngs_and_the_index(captured: Path) -> None:
    index = _index(captured)
    assert set(index) == {"fps", "frames", "hash"} and index["fps"] == 30
    frames = index["frames"]
    assert frames == sorted(set(frames)) and frames[0] > 10 and frames[-1] == 39
    assert 10 not in frames  # the label is not seen yet at its first frame: alpha 0, not kept
    names = sorted(p.name for p in (captured / GFX).iterdir())
    assert names == sorted(["index.json", "page.html", *(f"{f:06d}.png" for f in frames)])


def test_capture_index_the_same_page_is_not_captured_again(
    root: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _Calls(monkeypatch)
    stamp = (root / GFX / "index.json").stat().st_mtime_ns
    code, doc, err = kcut_json("graphics", "capture", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)
    assert doc["captured"] is False and doc["frames"] == len(_index(root)["frames"])
    assert doc["index"] == f"{GFX}/index.json" and calls.count == 0
    assert (root / GFX / "index.json").stat().st_mtime_ns == stamp


def test_capture_index_force_captures_again(
    root: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _Calls(monkeypatch)
    before = _index(root)
    code, doc, err = kcut_json("graphics", "capture", "--force", *project_args(root))
    assert code == 0 and doc["captured"] is True, (doc, err)
    assert calls.count == 1 and _codes(doc) == []
    assert _index(root) == before  # the same page gives the same index


def test_capture_index_a_changed_page_captures_again_and_leaves_no_old_frame(
    root: Path, kcut_json: Run
) -> None:
    changed = json.loads(json.dumps(GRAPHICS))
    changed["cues"][0].update(start=50, end=58)
    _write(root, changed)
    code, doc, err = kcut_json("graphics", "capture", *project_args(root))
    assert code == 0 and doc["captured"] is True, (doc, err)
    frames = _index(root)["frames"]
    assert frames and all(50 <= f < 58 for f in frames)
    left = sorted(p.name for p in (root / GFX).glob("*.png"))
    assert left == [f"{f:06d}.png" for f in frames]  # the 29 frames of before are gone


def test_capture_index_without_an_index_it_is_captured_with_no_notice(
    root: Path, kcut_json: Run
) -> None:
    (root / GFX / "index.json").unlink()
    code, doc, err = kcut_json("graphics", "capture", *project_args(root))
    assert code == 0 and doc["captured"] is True, (doc, err)
    assert "cache_rebuilt" not in _codes(doc)


def _unordered(index: dict[str, Any], _folder: Path) -> None:
    index["frames"] = index["frames"][::-1]


def _past_the_end(index: dict[str, Any], folder: Path) -> None:
    shutil.copy2(folder / f"{index['frames'][0]:06d}.png", folder / "000060.png")
    index["frames"].append(60)  # the video has 60 frames: 0 to 59


def _png_missing(index: dict[str, Any], folder: Path) -> None:
    (folder / f"{index['frames'][3]:06d}.png").unlink()


def _png_never_made(index: dict[str, Any], folder: Path) -> None:
    index["frames"].append(55)  # listed, with no PNG


def _not_hex(index: dict[str, Any], _folder: Path) -> None:
    index["hash"] = "zz" * 32


def _short_hash(index: dict[str, Any], _folder: Path) -> None:
    index["hash"] = "ab" * 10


def _other_fps(index: dict[str, Any], _folder: Path) -> None:
    index["fps"] = 25


def _bool_frame(index: dict[str, Any], _folder: Path) -> None:
    index["frames"][0] = True


def _extra_key(index: dict[str, Any], _folder: Path) -> None:
    index["note"] = "x"


def _negative(index: dict[str, Any], _folder: Path) -> None:
    index["frames"].insert(0, -1)


@pytest.mark.parametrize(
    "tamper",
    [
        _unordered, _past_the_end, _png_missing, _png_never_made, _not_hex,
        _short_hash, _other_fps, _bool_frame, _extra_key, _negative,
    ],
    ids=[
        "frames-disordered", "frame-past-the-end", "png-missing", "png-never-made", "hash-not-hex",
        "hash-short", "other-fps", "frame-is-bool", "extra-key", "negative-frame",
    ],
)  # fmt: skip
def test_capture_index_an_index_that_is_not_valid_is_rebuilt_with_cache_rebuilt(
    root: Path, kcut_json: Run, tamper: Change
) -> None:
    good = _index(root)
    index = json.loads(json.dumps(good))
    tamper(index, root / GFX)
    (root / GFX / "index.json").write_text(json.dumps(index), encoding="utf-8")
    code, doc, err = kcut_json("graphics", "capture", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)
    assert doc["captured"] is True and "cache_rebuilt" in _codes(doc)
    assert "cache_rebuilt" in err  # and it is said on the console too
    assert _index(root) == good  # the same page: the index is the one of before again


def test_capture_index_an_index_that_is_not_json_is_rebuilt_too(root: Path, kcut_json: Run) -> None:
    (root / GFX / "index.json").write_text("{no es json", encoding="utf-8")
    code, doc, err = kcut_json("graphics", "capture", *project_args(root))
    assert code == 0 and doc["captured"] is True and "cache_rebuilt" in _codes(doc), (doc, err)


def test_capture_index_a_folder_where_a_png_goes_is_exit_3_and_is_not_deleted(
    root: Path, kcut_json: Run
) -> None:
    frames = _index(root)["frames"]
    png = root / GFX / f"{frames[2]:06d}.png"
    png.unlink()
    png.mkdir()
    (png / "mine.txt").write_text("keep", encoding="utf-8")
    code, doc, _ = kcut_json("graphics", "capture", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError"
    assert "hay una carpeta donde kcut espera un archivo" in doc["error"]["message"]
    assert (png / "mine.txt").read_text(encoding="utf-8") == "keep"


def test_capture_index_a_png_that_is_damaged_when_rendering_is_exit_3_and_force_repairs_it(
    root: Path, kcut_json: Run
) -> None:
    frames = _index(root)["frames"]
    (root / GFX / f"{frames[5]:06d}.png").write_bytes(b"this is not a png")
    code, doc, err = kcut_json("render", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    assert f"el gráfico {frames[5]} de la caché está dañado" in doc["error"]["message"]
    assert "corre kcut graphics capture --force" in doc["error"]["message"]
    assert not list((root / ".kcut" / "build" / "v1").glob("*.partial*"))  # no partial is left
    code, doc, err = kcut_json("graphics", "capture", "--force", *project_args(root))
    assert code == 0 and doc["captured"] is True, (doc, err)
    code, doc, err = kcut_json("render", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)


def test_capture_index_a_png_of_another_size_is_exit_3_when_rendering(
    root: Path, kcut_json: Run
) -> None:
    from PIL import Image

    frames = _index(root)["frames"]
    Image.new("RGBA", (50, 50), (255, 0, 0, 255)).save(root / GFX / f"{frames[0]:06d}.png")
    code, doc, _ = kcut_json("render", *project_args(root))
    assert code == 3 and "corre kcut graphics capture --force" in doc["error"]["message"]


def test_capture_index_the_graphics_check_comes_before_anything_is_captured(
    root: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With errors in `graphics.json`, `capture` is exit 1 and Chromium is not started."""
    broken = json.loads(json.dumps(GRAPHICS))
    broken["cues"][0]["end"] = 999
    _write(root, broken)
    calls = _Calls(monkeypatch)
    code, doc, _ = kcut_json("graphics", "capture", *project_args(root))
    assert code == 1 and doc["error"]["kind"] == "CheckFailed" and "G07" in doc["error"]["message"]
    assert calls.count == 0
    code, doc, _ = kcut_json("render", *project_args(root))
    assert code == 1 and doc["error"]["kind"] == "CheckFailed"
    assert calls.count == 0
