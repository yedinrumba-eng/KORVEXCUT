"""`kcut render` on a small EDL of 2 s (spec S1.5b rows 11 and 12): a sidecar that is stale,
missing or corrupt, a mezzanine that already holds the range, and a wav48 that is too short.

Collected from `test_render_synth.py`, which is at the 300-line limit. `small_base` renders the
small EDL once for the module; `small` is a copy of it for each test.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut.audio.wavio import write_wav_s16_mono
from kcut.ingest.inventory import load_inventory
from tests.conftest import run_kcut

__all__ = ["TestMezzSidecar", "TestShortWav", "small", "small_base"]
BUILD = ".kcut/build/v1"
Rendered = tuple[Path, dict[str, Any]]


def small_edl(root: Path) -> None:
    """A 2 s EDL: a synchronized camera of a1 over one voice clip (source frames 60 to 119)."""
    inventory = load_inventory(root / ".kcut" / "inventory.json", root)
    clip = inventory.by_id("a1")
    assert clip is not None
    document = {
        "schema": "kcut.edl/1",
        "version": 1,
        "fps": 30,
        "output": {"w": 1080, "h": 1920},
        "frames": 60,
        "look": "neutro",
        "sources": {"a1": {"qhash": clip.qhash}},
        "clips": [{"kind": "voice", "at_f": 0, "src": "a1", "in_f": 60, "out_f": 120, "why": "x"}],
        "spans": [{"kind": "cam", "at_f": 0, "dur_f": 60, "src": "a1", "zoom": 1.2}],
    }
    (root / "edit").mkdir(exist_ok=True)
    (root / "edit" / "edl-v1.json").write_text(json.dumps(document, indent=1), encoding="utf-8")
    approve(root)


def approve(root: Path, value: str = "si") -> None:
    text = f"---\nvideo: sintetico\naprobado: {value}\n---\n# Estrategia\n"
    (root / "edit" / "estrategia.md").write_text(text, encoding="utf-8", newline="\n")


def render_json(root: Path, *extra: str) -> tuple[int, dict[str, Any], str]:
    done = run_kcut("render", "--no-graphics", "--json", "--project", str(root), *extra)
    return done.returncode, json.loads(done.stdout), done.stderr


@pytest.fixture(scope="module")
def small_base(tmp_path_factory: pytest.TempPathFactory, view_shared: Path) -> Path:
    """The synthetic project with the small EDL, rendered once (the mezzanine and wav48 exist)."""
    root = tmp_path_factory.mktemp("small") / "proyecto ñandú"
    shutil.copytree(view_shared, root)
    small_edl(root)
    code, doc, err = render_json(root)
    assert code == 0 and doc["mezz_built"] == 1, err
    return root


@pytest.fixture
def small(small_base: Path, tmp_path: Path) -> Path:
    """A copy of `small_base` for one test (`copytree` keeps the modification times)."""
    root = tmp_path / "proyecto ñandú"
    shutil.copytree(small_base, root)
    return root


def mezz_files(root: Path) -> list[Path]:
    return sorted(p for p in (root / ".kcut" / "mezz").glob("*.mp4") if ".partial." not in p.name)


class TestMezzSidecar:
    """Row 11 (001.15): a mezzanine is reused only if its sidecar says it is fresh."""

    def test_render_synth_mezz_sidecar_a_second_render_reuses_everything(self, small: Path) -> None:
        (mezz,) = mezz_files(small)
        before = (mezz.stat().st_mtime_ns, Path(f"{mezz}.json").stat().st_mtime_ns)
        code, doc, err = render_json(small)
        assert code == 0, err
        assert (doc["mezz_built"], doc["mezz_reused"]) == (0, 1)
        assert (mezz.stat().st_mtime_ns, Path(f"{mezz}.json").stat().st_mtime_ns) == before

    def test_render_synth_mezz_sidecar_the_whole_example_is_reused_too(
        self, rendered_example: Rendered, tmp_path: Path
    ) -> None:
        root, _ = rendered_example
        copy = tmp_path / "proyecto ñandú"
        shutil.copytree(root, copy)
        stamps = {p.name: p.stat().st_mtime_ns for p in mezz_files(copy)}
        (copy / BUILD / "render.mp4").unlink()  # only the mezzanines matter here
        code, doc, err = render_json(copy)
        assert code == 0, err
        assert (doc["mezz_built"], doc["mezz_reused"]) == (0, 6)
        assert {p.name: p.stat().st_mtime_ns for p in mezz_files(copy)} == stamps

    def test_render_synth_mezz_sidecar_other_params_make_that_file_again(self, small: Path) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["params"]["crf"] = 23
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        old = mezz.stat().st_mtime_ns
        code, doc, err = render_json(small)
        assert code == 0, err
        assert (doc["mezz_built"], doc["mezz_reused"]) == (1, 0)
        assert mezz.stat().st_mtime_ns > old
        assert json.loads(sidecar.read_text(encoding="utf-8"))["params"]["crf"] == 14
        assert "cache_rebuilt" not in err  # stale is not corrupt

    def test_render_synth_mezz_sidecar_another_qhash_makes_it_again(self, small: Path) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        data["qhash"] = "sha256:" + "1" * 64
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), err

    def test_render_synth_mezz_sidecar_a_missing_sidecar_makes_it_again(self, small: Path) -> None:
        (mezz,) = mezz_files(small)
        Path(f"{mezz}.json").unlink()
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), err
        assert Path(f"{mezz}.json").is_file()

    def test_render_synth_mezz_sidecar_a_corrupt_one_is_made_again_with_a_notice(
        self, small: Path
    ) -> None:
        (mezz,) = mezz_files(small)
        sidecar = Path(f"{mezz}.json")
        sidecar.write_text("{no es json", encoding="utf-8")
        old = mezz.stat().st_mtime_ns
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), err
        assert "cache_rebuilt" in err and mezz.name in err
        assert mezz.stat().st_mtime_ns > old
        assert json.loads(sidecar.read_text(encoding="utf-8"))["params"]["crf"] == 14

    def test_render_synth_mezz_sidecar_a_bigger_fresh_mezzanine_that_holds_the_range_is_used(
        self, small: Path
    ) -> None:
        """The EDL changes to need less of a1: the file made for the first one holds it."""
        (mezz,) = mezz_files(small)
        edl = small / "edit" / "edl-v1.json"
        document = json.loads(edl.read_text(encoding="utf-8"))
        document["clips"][0].update(in_f=70, out_f=110)  # 40 frames inside 60-119
        document.update(frames=40)
        document["spans"][0]["dur_f"] = 40
        edl.write_text(json.dumps(document), encoding="utf-8")
        code, doc, err = render_json(small)
        assert code == 0, err
        assert (doc["mezz_built"], doc["mezz_reused"]) == (0, 1)  # [55, 125) is in [45, 135)
        assert mezz_files(small) == [mezz]

    def test_render_synth_mezz_sidecar_a_range_that_is_not_held_makes_a_new_file(
        self, small: Path
    ) -> None:
        edl = small / "edit" / "edl-v1.json"
        document = json.loads(edl.read_text(encoding="utf-8"))
        document["clips"][0].update(in_f=200, out_f=260)
        edl.write_text(json.dumps(document), encoding="utf-8")
        code, doc, err = render_json(small)
        assert code == 0 and (doc["mezz_built"], doc["mezz_reused"]) == (1, 0), err
        assert len(mezz_files(small)) == 2


class TestShortWav:
    """Row 12 (T6): a wav48 shorter than a clip is a CheckFailed, exit 1, never an InternalError."""

    def _shorten(self, root: Path, frames: int) -> Path:
        wav = next((root / ".kcut" / "wav48").glob("a1_*.wav"))
        write_wav_s16_mono(wav, np.zeros(frames * 1600, dtype=np.float32), 48000)
        return wav

    def test_render_synth_short_wav_is_exit_1_and_names_the_clip(self, small: Path) -> None:
        self._shorten(small, 100)  # the clip asks for source frames up to 120
        code, doc, _ = render_json(small)
        assert code == 1 and doc["error"]["kind"] == "CheckFailed", doc
        message = doc["error"]["message"]
        assert message == (
            f"el wav48 de a1 tiene {100 * 1600} muestras y clips[0] pide hasta {120 * 1600}; "
            "corre kcut ingest o acorta el clip"
        )

    def test_render_synth_short_wav_leaves_no_render_and_no_partial_file(self, small: Path) -> None:
        self._shorten(small, 100)
        code, _, _ = render_json(small)
        assert code == 1
        assert list((small / ".kcut").rglob("*.partial.*")) == []

    def test_render_synth_short_wav_a_wav_that_is_long_enough_renders(self, small: Path) -> None:
        self._shorten(small, 120)
        code, doc, err = render_json(small)
        assert code == 0 and doc["frames"] == 60, err
