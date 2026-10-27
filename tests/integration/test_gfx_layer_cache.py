"""The graphics layer in the cache, through `kcut graphics capture` and `kcut render` (spec S1.6b
round 1, 001.31 points 3 and 6; rows 21 and 24). Chromium is replaced by the `Shooter` of
`fake_shooter.py`: what is looked at is what kcut does with the files of the cache.

- A PNG or an `index.json` with more than one name (a hard link to something outside the project)
  makes the index invalid: the layer is captured again, with the notice `cache_rebuilt`, and the
  file outside is not touched.
- A lone surrogate in a text of the page is not an error: the hash of the page and the file that
  is written have the same bytes, so the second capture finds the layer it made.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.links import make_hard_link
from tests.integration.fake_shooter import install_fake_shooter
from tests.integration.graphics_helpers import plant_words
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
__all__ = ["small", "small_base"]
GFX = ".kcut/build/v1/gfx"
PRIVATE = b"PRIVATE-PICTURE-OF-SOMEONE-ELSE" * 8
WORDS = [("Llama", 2100, 2400), ("ya", 2500, 2800), ("gracias", 2900, 3200)]


def _label_doc(text: str = "x") -> dict[str, Any]:
    cue = {"id": "x", "component": "label", "start": 3, "end": 8, "params": {"text": text}}
    return {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}


def _write(root: Path, document: dict[str, Any]) -> None:
    # `ensure_ascii` (the default): a lone surrogate goes into the file as the escape `\ud800`
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _codes(doc: dict[str, Any]) -> list[str]:
    return [w["code"] for w in doc["warnings"]]


def _plant_surrogate(root: Path) -> None:
    """The transcript of a1 (`WORDS`) with a lone surrogate at the end of its first word, put into
    the JSON file as the escape `\\ud800` (not with `save_transcript`, which would turn it into a
    `?`), and checked to be read back from it."""
    from kcut.ingest.inventory import load_inventory
    from kcut.paths import resolve_in_project
    from kcut.project import open_project
    from kcut.transcribe.cache import load_transcript, wav16_length_ms

    plant_words(root, WORDS)
    found = [p for p in (root / ".kcut" / "transcripts").glob("*.json") if p.name != "index.json"]
    assert len(found) == 1
    document = json.loads(found[0].read_text(encoding="utf-8"))
    document["words"][0]["w"] = "Llama\ud800"
    found[0].write_text(json.dumps(document), encoding="utf-8")  # ensure_ascii: the escape
    assert b"\\ud800" in found[0].read_bytes()
    clip = load_inventory(root / ".kcut" / "inventory.json", root).by_id("a1")
    assert clip is not None and clip.work is not None and clip.work.wav16 is not None
    wav_ms = wav16_length_ms(resolve_in_project(root, clip.work.wav16))
    loaded = load_transcript(open_project(str(root)), "a1", wav_ms=wav_ms)
    assert loaded is not None and loaded.words[0].text == "Llama\ud800"


class TestHardLink:
    def test_gfx_hardlink_a_png_with_two_names_is_captured_again_and_the_other_name_is_left(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _write(small, _label_doc())
        install_fake_shooter(monkeypatch)
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["captured"] is True and doc["frames"] == 5, (doc, err)
        outside = tmp_path / "ajeno.png"
        outside.write_bytes(PRIVATE)
        before = _sha(outside)
        png = small / GFX / "000003.png"
        png.unlink()
        make_hard_link(png, outside)
        assert os.stat(png).st_nlink == 2
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))  # no `--force`
        assert code == 0 and doc["captured"] is True, (doc, err)
        assert "cache_rebuilt" in _codes(doc)
        assert _sha(outside) == before and os.stat(outside).st_nlink == 1
        assert os.stat(png).st_nlink == 1 and png.read_bytes() != PRIVATE

    def test_gfx_hardlink_an_index_with_two_names_is_captured_again_too(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _write(small, _label_doc())
        install_fake_shooter(monkeypatch)
        assert kcut_json("graphics", "capture", *project_args(small))[0] == 0
        index = small / GFX / "index.json"
        outside = tmp_path / "otro-nombre.json"
        make_hard_link(outside, index)
        before = _sha(outside)
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["captured"] is True, (doc, err)
        assert "cache_rebuilt" in _codes(doc)
        assert _sha(outside) == before  # the other name still holds the old index
        assert os.stat(index).st_nlink == 1

    def test_gfx_hardlink_a_layer_that_is_all_right_is_not_captured_again(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small, _label_doc())
        install_fake_shooter(monkeypatch)
        kcut_json("graphics", "capture", *project_args(small))
        code, doc, _ = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["captured"] is False and _codes(doc) == []


class TestSurrogate:
    def test_gfx_surrogate_a_lone_one_in_a_cue_is_exit_0_and_the_layer_is_reused(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(small, _label_doc("hola \ud800 mundo"))
        install_fake_shooter(monkeypatch)
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["captured"] is True, (doc, err)  # it was exit 10
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["captured"] is False, (doc, err)
        code, doc, err = kcut_json("render", *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)

    def test_gfx_surrogate_the_page_on_disk_has_the_bytes_that_were_hashed(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kcut.gfx.capture_index import page_hash

        _write(small, _label_doc("a \ud800 b"))
        install_fake_shooter(monkeypatch)
        assert kcut_json("graphics", "capture", *project_args(small))[0] == 0
        written = (small / GFX / "page.html").read_bytes()
        index = json.loads((small / GFX / "index.json").read_text(encoding="utf-8"))
        assert index["hash"] == hashlib.sha256(written).hexdigest()
        assert index["hash"] == page_hash(written.decode("utf-8"))

    def test_gfx_surrogate_a_lone_one_in_a_transcript_is_exit_0_everywhere(
        self, small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """001.32 point 7 (row 38): the case of row 24 with the surrogate in a word of the
        transcript, which is what that row says. The default captions draw that word."""
        _plant_surrogate(small)
        install_fake_shooter(monkeypatch)
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["captured"] is True and doc["frames"] > 0, (doc, err)
        code, doc, err = kcut_json("graphics", "capture", *project_args(small))
        assert code == 0 and doc["captured"] is False, (doc, err)
        code, doc, err = kcut_json("render", *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)
        code, doc, err = kcut_json("graphics", "still", "20", *project_args(small))
        assert code == 0 and doc["ok"] is True, (doc, err)
