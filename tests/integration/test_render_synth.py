"""`kcut render` on the synthetic project (spec S1.5b rows 5, 6, 8, 9, 11 and 12).

The example EDL of the spec is rendered once for the session (`rendered_example`, a copy of the
synthetic project); the tests that break something (the gate, `sources`, a sidecar, a short wav)
work on copies of their own, with a small EDL of 2 s so each render takes seconds.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut.audio.wavio import read_f32
from kcut.render.lock import OutputLock
from tests.conftest import run_kcut
from tests.fixtures.av_probe import stream_tags
from tests.fixtures.synth_edl import write_edl_v1
from tests.integration.render_dest_cases import *  # noqa: F403  (001.25: 300-line rule)
from tests.integration.render_early_cases import *  # noqa: F403  (001.26: 300-line rule)
from tests.integration.render_mezz_cases import *  # noqa: F403  (001.25: 300-line rule)
from tests.integration.render_small_cases import *  # noqa: F403  (300-line rule)
from tests.integration.render_small_cases import approve, mezz_files
from tests.integration.render_step0_cases import *  # noqa: F403  (001.27: 300-line rule)
from tests.integration.render_step0b_cases import *  # noqa: F403  (001.30: 300-line rule)
from tests.integration.render_tail_cases import *  # noqa: F403  (001.26: 300-line rule)
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
Rendered = tuple[Path, dict[str, Any]]
BUILD = ".kcut/build/v1"


class TestRenderOfTheExample:
    """Row 5: the example of the spec, rendered."""

    def test_render_synth_the_json_says_what_was_made(self, rendered_example: Rendered) -> None:
        _, doc = rendered_example
        assert set(doc) == {"ok", "video", "render", "frames", "mezz_built", "mezz_reused",
                            "elapsed_s"}  # fmt: skip
        assert doc["ok"] is True and doc["frames"] == 345
        assert (doc["video"], doc["render"]) == (f"{BUILD}/video.mp4", f"{BUILD}/render.mp4")
        assert (doc["mezz_built"], doc["mezz_reused"]) == (6, 0)
        assert isinstance(doc["elapsed_s"], float) and doc["elapsed_s"] > 0

    def test_render_synth_the_video_is_345_frames_of_1080_by_1920(
        self, rendered_example: Rendered
    ) -> None:
        root, _ = rendered_example
        tags = stream_tags(root / BUILD / "video.mp4", "codec_name,width,height,nb_frames,pix_fmt")
        assert tags == {"codec_name": "h264", "width": "1080", "height": "1920",
                        "nb_frames": "345", "pix_fmt": "yuv420p"}  # fmt: skip

    def test_render_synth_the_voice_is_552000_samples(self, rendered_example: Rendered) -> None:
        root, _ = rendered_example
        samples = read_f32(root / BUILD / "voice_raw.f32")
        assert samples.shape == (345 * 1600,) == (552000,)
        assert float(np.abs(samples).max()) > 0.05  # it is the voice, not silence

    def test_render_synth_the_review_mp4_copies_the_video_and_has_aac_stereo(
        self, rendered_example: Rendered
    ) -> None:
        root, _ = rendered_example
        render = root / BUILD / "render.mp4"
        video = stream_tags(render, "codec_name,width,height,nb_frames")
        assert video == {"codec_name": "h264", "width": "1080", "height": "1920",
                         "nb_frames": "345"}  # fmt: skip
        audio = stream_tags(render, "codec_name,channels,sample_rate", "a:0")
        assert audio == {"codec_name": "aac", "sample_rate": "48000", "channels": "2"}

    def test_render_synth_no_partial_file_is_left_behind(self, rendered_example: Rendered) -> None:
        root, _ = rendered_example
        left = [p.name for p in (root / ".kcut").rglob("*") if ".partial." in p.name]
        assert left == []
        assert sorted(p.name for p in (root / BUILD).iterdir()) == [
            "render.mp4", "video.mp4", "voice_raw.f32"]  # fmt: skip

    def test_render_synth_nothing_is_written_in_crudo(
        self, rendered_example: Rendered, synth_project: tuple[Path, Any]
    ) -> None:
        root, _ = rendered_example
        before = sorted(p.name for p in (synth_project[0] / "crudo").iterdir())
        assert sorted(p.name for p in (root / "crudo").iterdir()) == before


def test_video_color_tags(rendered_example: Rendered) -> None:
    """Row 8 (001.4): the four tags, bt709 and limited range, on the video of the render."""
    root, _ = rendered_example
    tags = stream_tags(
        root / BUILD / "video.mp4", "color_space,color_primaries,color_transfer,color_range"
    )
    assert tags == {
        "color_space": "bt709",
        "color_primaries": "bt709",
        "color_transfer": "bt709",
        "color_range": "tv",
    }


def test_mezz_lazy(rendered_example: Rendered) -> None:
    """Row 6: only what the cut uses is made, with the sizes and ranges of the spec."""
    root, _ = rendered_example
    names = [p.name for p in mezz_files(root)]
    assert names == [
        "a1_195-255_1440x2560_tm2.mp4",
        "a1_285-360_1440x2560_tm2.mp4",
        "a1_45-135_1440x2560_tm2.mp4",
        "a2_69-189_1080x1920_tm2.mp4",
        "b1_0-45_1894x866_tm2.mp4",
        "b1_75-164_1894x866_tm2.mp4",
    ]
    a1 = [re.fullmatch(r"a1_(\d+)-(\d+)_.*", n) for n in names if n.startswith("a1")]
    assert not any(m and int(m[1]) <= 0 < int(m[2]) for m in a1)  # none holds frame 0
    for path in mezz_files(root):
        found = re.fullmatch(r"(\w+)_(\d+)-(\d+)_(\d+)x(\d+)_tm2\.mp4", path.name)
        assert found is not None
        _, start, end, w, h = found.groups()
        tags = stream_tags(
            path, "width,height,nb_frames,pix_fmt,color_space,color_primaries,color_transfer"
        )
        assert (tags["width"], tags["height"]) == (w, h) and tags["pix_fmt"] == "yuv420p"
        assert tags["nb_frames"] == str(int(end) - int(start))
        assert (tags["color_space"], tags["color_primaries"], tags["color_transfer"]) == (
            "bt709", "bt709", "bt709")  # fmt: skip
    assert (root / ".kcut" / "mezz" / "a2_69-189_1080x1920_tm2.mp4.json").is_file()


def test_mezz_lazy_the_a2_mezzanine_was_tone_mapped_from_hlg(rendered_example: Rendered) -> None:
    """a2 is 10-bit HLG: its mezzanine is 8-bit SDR with the bt709 tags (the approved chain)."""
    root, _ = rendered_example
    tags = stream_tags(
        root / ".kcut" / "mezz" / "a2_69-189_1080x1920_tm2.mp4", "profile,pix_fmt,color_range"
    )
    assert tags["pix_fmt"] == "yuv420p" and tags["color_range"] == "tv"
    assert tags["profile"] in ("High", "Constrained Baseline", "Main")  # not High 10


class TestGateAndCheck:
    def test_render_synth_without_approval_is_exit_5_and_makes_nothing(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        write_edl_v1(view_fresh)
        approve(view_fresh, "no")
        code, doc, _ = kcut_json("render", "--no-graphics", *project_args(view_fresh))
        assert code == 5 and doc["error"]["kind"] == "GateError"
        assert "estrategia" in doc["error"]["message"]
        assert not (view_fresh / ".kcut" / "build").exists()
        assert mezz_files(view_fresh) == []

    def test_render_synth_the_gate_is_read_before_the_edl(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        write_edl_v1(view_fresh)
        approve(view_fresh, "no")
        (view_fresh / "edit" / "edl-v1.json").write_text("{}", encoding="utf-8")
        assert kcut_json("render", "--no-graphics", *project_args(view_fresh))[0] == 5

    def test_render_synth_an_edl_with_errors_is_exit_1_and_makes_nothing(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        write_edl_v1(view_fresh)
        path = view_fresh / "edit" / "edl-v1.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["frames"] = 346
        path.write_text(json.dumps(document), encoding="utf-8")
        code, doc, _ = kcut_json("render", "--no-graphics", *project_args(view_fresh))
        assert code == 1 and doc["error"]["kind"] == "CheckFailed"
        assert "E08" in doc["error"]["message"] and "kcut edl check" in doc["error"]["message"]
        assert not (view_fresh / ".kcut" / "build").exists() and mezz_files(view_fresh) == []

    def test_render_synth_a_lock_that_is_held_is_exit_6(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        write_edl_v1(view_fresh)
        with OutputLock(view_fresh / ".kcut" / "locks", "build-v1"):
            code, doc, _ = kcut_json("render", "--no-graphics", *project_args(view_fresh))
        assert code == 6 and doc["error"]["kind"] == "LockedError"
        assert not (view_fresh / ".kcut" / "build").exists()

    def test_render_synth_no_edl_is_exit_3(self, view_fresh: Path, kcut_json: Run) -> None:
        code, doc, _ = kcut_json("render", "--no-graphics", *project_args(view_fresh))
        assert code == 3 and "edl-vN.json" in doc["error"]["message"]

    def test_render_synth_a_path_outside_the_project_is_exit_3(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        write_edl_v1(view_fresh)
        code, _, _ = kcut_json("render", "--edl", "../edl-v1.json", *project_args(view_fresh))
        assert code == 3

    def test_render_synth_without_an_inventory_is_exit_3_and_says_ingest(
        self, tmp_path: Path, kcut_json: Run
    ) -> None:
        root = tmp_path / "proyecto ñandú"
        assert run_kcut("new", str(root)).returncode == 0
        code, doc, _ = kcut_json("render", "--no-graphics", *project_args(root))
        assert code == 3 and "kcut ingest" in doc["error"]["message"]


class TestSources:
    """Row 9 (001.6): with a bad `sources` block render exits with 1 and renders nothing."""

    @staticmethod
    def _rewrite(root: Path, change: Callable[[dict[str, Any]], object]) -> None:
        write_edl_v1(root)
        path = root / "edit" / "edl-v1.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        change(document)
        path.write_text(json.dumps(document), encoding="utf-8")

    @staticmethod
    def _renumbered(doc: dict[str, Any]) -> None:
        doc["sources"]["b1"]["qhash"] = "sha256:" + "0" * 64

    @staticmethod
    def _gone(doc: dict[str, Any]) -> None:
        doc["sources"]["x9"] = doc["sources"].pop("a2")
        doc["spans"][2]["src"] = "x9"

    @staticmethod
    def _no_entry(doc: dict[str, Any]) -> None:
        doc["sources"].pop("a1")

    @pytest.mark.parametrize(
        ("change", "named"),
        [(_renumbered, "'b1'"), (_gone, "'x9'"), (_no_entry, "'a1'")],
        ids=["qhash-changed", "clip-not-in-inventory", "src-without-entry"],
    )
    def test_render_synth_sources_bad_block_is_exit_1_without_rendering(
        self,
        view_fresh: Path,
        kcut_json: Run,
        capsys: pytest.CaptureFixture[str],
        change: Callable[[dict[str, Any]], object],
        named: str,
    ) -> None:
        self._rewrite(view_fresh, change)
        code, doc, _ = kcut_json("render", "--no-graphics", *project_args(view_fresh))
        assert code == 1 and "E04" in doc["error"]["message"], doc
        assert not (view_fresh / ".kcut" / "build").exists() and mezz_files(view_fresh) == []
        human = run_kcut("render", "--no-graphics", "--project", str(view_fresh))
        assert human.returncode == 1 and "[ERROR] E04 sources: " in human.stdout
        assert named in human.stdout
