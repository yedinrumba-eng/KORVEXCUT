"""`kcut edl check` and `kcut edl sources` on the synthetic project (spec S1.5a, rows 5, 7, 8, 10).

The project is a copy of the session's synthetic one (cameras a1 and a2, the screen b1, a photo and
a note) with the example EDL of the spec in `edit/edl-v1.json` and an approved strategy.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut.audio.wavio import write_wav_s16_mono
from kcut.ingest.inventory import load_inventory
from kcut.paths import resolve_in_project
from tests.conftest import run_kcut
from tests.fixtures.synth_edl import write_edl_v1
from tests.integration.view_frames_helpers import Run, project_args, remove

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
EDL = "edit/edl-v1.json"


@pytest.fixture
def edl_project(view_fresh: Path) -> Path:
    write_edl_v1(view_fresh)
    return view_fresh


def _rewrite(
    root: Path, change: Callable[[dict[str, Any]], object], name: str = "edl-v1.json"
) -> None:
    path = root / "edit" / name
    doc = json.loads((root / EDL).read_text(encoding="utf-8"))
    change(doc)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def _qhashes(root: Path) -> dict[str, str]:
    inventory = load_inventory(root / ".kcut" / "inventory.json", root)
    return {clip.id: clip.qhash for clip in inventory.clips}


class TestCheckCli:
    def test_edl_check_cli_the_example_is_ok_with_one_warning(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 0, err
        assert doc["schema"] == "kcut.edlcheck/1" and doc["edl"] == EDL
        assert doc["ok"] is True and doc["frames"] == 345 and doc["duration_display"] == "00:11.5"
        assert doc["errors"] == []
        assert [(w["code"], w["path"]) for w in doc["warnings"]] == [("W01", "spans[3]")]
        assert doc["gate"] == {"approved": True, "file": "edit/estrategia.md"}

    def test_edl_check_cli_the_human_output_has_the_prefixes(self, edl_project: Path) -> None:
        done = run_kcut("edl", "check", "--project", str(edl_project))
        assert done.returncode == 0, done.stderr
        lines = done.stdout.splitlines()
        assert any(line.startswith("[AVISO] W01 spans[3]: ") for line in lines)
        assert any(line.startswith("[OK] edit/edl-v1.json: 345 frames (00:11.5)") for line in lines)
        assert any(line.startswith("[OK] estrategia") for line in lines)

    def test_edl_check_cli_errors_are_exit_1_and_listed(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        _rewrite(edl_project, lambda d: d.update(frames=346))
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 1 and doc["ok"] is False
        assert [(e["code"], e["path"]) for e in doc["errors"]] == [
            ("E08", "clips"),
            ("E08", "spans"),
        ]
        assert doc["errors"][0]["message"] and doc["frames"] == 346

    def test_edl_check_cli_the_human_output_lists_each_error(self, edl_project: Path) -> None:
        _rewrite(edl_project, lambda d: d["clips"][1].update(out_f=99999))
        done = run_kcut("edl", "check", "--project", str(edl_project))
        assert done.returncode == 1
        assert "[ERROR] E06 clips[1]: " in done.stdout

    def test_edl_check_cli_a_strategy_that_is_not_approved_does_not_fail_the_check(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        (edl_project / "edit" / "estrategia.md").write_text(
            "---\naprobado: no\n---\n", encoding="utf-8"
        )
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 0 and doc["ok"] is True and doc["gate"]["approved"] is False

    def test_edl_check_cli_without_a_path_it_takes_the_highest_n(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        _rewrite(edl_project, lambda d: d.update(version=2), "edl-v2.json")
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 0 and doc["edl"] == "edit/edl-v2.json"
        code, doc, _ = kcut_json("edl", "check", EDL, *project_args(edl_project))
        assert code == 0 and doc["edl"] == EDL

    def test_edl_check_cli_the_version_has_to_be_the_one_of_the_name(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        _rewrite(edl_project, lambda d: None, "edl-v3.json")  # it says 1, the name says 3
        code, doc, _ = kcut_json("edl", "check", "edit/edl-v3.json", *project_args(edl_project))
        assert code == 1 and [e["code"] for e in doc["errors"]] == ["E02"]

    def test_edl_check_cli_schema_errors_are_e01_with_no_frames(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        _rewrite(edl_project, lambda d: d["clips"][1].update(in_f=60.0))
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 1 and doc["frames"] is None and doc["duration_display"] is None
        assert [(e["code"], e["path"]) for e in doc["errors"]] == [("E01", "clips[1].in_f")]

    def test_edl_check_cli_no_edl_or_a_broken_one_is_exit_3(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        (edl_project / EDL).write_text("{no es json", encoding="utf-8")
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 3 and doc["error"]["kind"] == "ProjectError"
        (edl_project / EDL).unlink()
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 3 and "edl-vN.json" in doc["error"]["message"]

    def test_edl_check_cli_a_path_outside_the_project_is_exit_3(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        for bad in ("../edl-v1.json", "C:/edl-v1.json"):
            assert kcut_json("edl", "check", bad, *project_args(edl_project))[0] == 3


class TestSourcesBlock:
    """Row 7: `sources` keeps a renumbered id from cutting the wrong video."""

    def test_edl_check_cli_sources_a_changed_qhash_is_exit_1_and_names_the_id(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        _rewrite(edl_project, lambda d: d["sources"]["b1"].update(qhash="sha256:" + "0" * 64))
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 1 and [e["code"] for e in doc["errors"]] == ["E04"]
        assert "'b1'" in doc["errors"][0]["message"]

    def test_edl_check_cli_sources_a_clip_that_is_not_in_the_inventory_is_exit_1(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        def change(doc: dict[str, Any]) -> None:
            doc["sources"]["x9"] = doc["sources"].pop("a2")
            doc["spans"][2]["src"] = "x9"

        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 0
        _rewrite(edl_project, change)
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 1 and "E04" in {e["code"] for e in doc["errors"]}
        assert any("'x9'" in e["message"] for e in doc["errors"] if e["code"] == "E04")

    def test_edl_check_cli_sources_a_src_with_no_entry_is_exit_1(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        _rewrite(edl_project, lambda d: d["sources"].pop("a1"))
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 1 and [e["code"] for e in doc["errors"]] == ["E04"]
        assert "'a1'" in doc["errors"][0]["message"]

    def test_edl_check_cli_sources_a_renumbered_id_is_caught(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        """The EDL was written when a1 and a2 were the other way round."""

        def swap(doc: dict[str, Any]) -> None:
            doc["sources"]["a1"], doc["sources"]["a2"] = doc["sources"]["a2"], doc["sources"]["a1"]

        _rewrite(edl_project, swap)
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 1 and [e["code"] for e in doc["errors"]] == ["E04", "E04"]
        named = " ".join(e["message"] for e in doc["errors"])
        assert "'a1'" in named and "'a2'" in named


class TestEdlSources:
    """Row 8: the block, ready to paste."""

    def test_edl_sources_the_block_and_the_clips(self, edl_project: Path, kcut_json: Run) -> None:
        code, doc, err = kcut_json("edl", "sources", *project_args(edl_project))
        assert code == 0, err
        assert doc["ok"] is True and set(doc["sources"]) == {"a1", "a2", "b1"}
        hashes = _qhashes(edl_project)
        assert doc["sources"] == {i: {"qhash": hashes[i]} for i in ("a1", "a2", "b1")}
        by_id = {c["id"]: c for c in doc["clips"]}
        assert list(by_id) == ["a1", "a2", "b1"]  # the order of the inventory
        assert by_id["a1"] == {
            "id": "a1", "qhash": hashes["a1"], "frames": 360, "w": 1440, "h": 2560,
            "vs_f": 0, "audio_f": 360,
        }  # fmt: skip
        assert (by_id["b1"]["w"], by_id["b1"]["h"], by_id["b1"]["frames"]) == (1894, 866, 240)
        assert by_id["b1"]["audio_f"] is None and by_id["a2"]["audio_f"] == 360

    def test_edl_sources_the_block_pasted_as_it_is_gives_no_e04(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        _rewrite(edl_project, lambda d: d.update(sources={"a1": {"qhash": "sha256:00"}}))
        assert "E04" in {
            e["code"] for e in kcut_json("edl", "check", *project_args(edl_project))[1]["errors"]
        }
        block = kcut_json("edl", "sources", *project_args(edl_project))[1]["sources"]
        _rewrite(edl_project, lambda d: d.update(sources=block))
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 0 and "E04" not in {e["code"] for e in doc["errors"]}

    def test_edl_sources_with_ids_only_those_in_the_order_given(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        code, doc, _ = kcut_json("edl", "sources", "b1", "a1", "b1", *project_args(edl_project))
        assert code == 0 and [c["id"] for c in doc["clips"]] == ["b1", "a1"]
        assert set(doc["sources"]) == {"a1", "b1"}

    def test_edl_sources_an_unknown_id_a_photo_or_a_note_is_exit_2(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        for bad in ("x9", "i1", "d1"):
            code, doc, _ = kcut_json("edl", "sources", bad, *project_args(edl_project))
            assert code == 2 and doc["error"]["kind"] == "UsageError", bad
        assert kcut_json("edl", "sources", "a1", "x9", *project_args(edl_project))[0] == 2

    def test_edl_sources_the_human_output_has_the_block_and_a_line_per_clip(
        self, edl_project: Path
    ) -> None:
        done = run_kcut("edl", "sources", "--project", str(edl_project))
        assert done.returncode == 0, done.stderr
        lines = done.stdout.splitlines()
        assert lines[0].startswith('[INFO] "sources": {"a1": {"qhash": "sha256:')
        assert json.loads("{" + lines[0].removeprefix("[INFO] ") + "}")["sources"].keys() == {
            "a1", "a2", "b1",
        }  # fmt: skip
        assert lines[1] == "[INFO] a1 - 360 frames - 1440x2560 - voz hasta f360"
        assert lines[3] == "[INFO] b1 - 240 frames - 1894x866 - sin voz"

    def test_edl_sources_has_no_file_names(self, edl_project: Path) -> None:
        done = run_kcut("edl", "sources", "--json", "--project", str(edl_project))
        assert (
            "cam a" not in done.stdout and "crudo" not in done.stdout and "mp4" not in done.stdout
        )

    def test_edl_sources_needs_the_inventory(self, tmp_path: Path, kcut_json: Run) -> None:
        root = tmp_path / "proyecto ñandú"
        assert run_kcut("new", str(root)).returncode == 0
        code, doc, _ = kcut_json("edl", "sources", *project_args(root))
        assert code == 3 and "corre kcut ingest" in doc["error"]["message"]

    def test_edl_sources_does_not_need_an_edl(self, view_fresh: Path, kcut_json: Run) -> None:
        assert not (view_fresh / EDL).exists()
        assert kcut_json("edl", "sources", *project_args(view_fresh))[0] == 0


class TestRealAudio:
    """Row 10 (T6): a voice is judged against the audio the wav16 really has."""

    def _short_wav16(self, root: Path, seconds: int) -> None:
        clip = load_inventory(root / ".kcut" / "inventory.json", root).by_id("a1")
        assert clip is not None and clip.work is not None and clip.work.wav16 is not None
        path = resolve_in_project(root, clip.work.wav16)
        write_wav_s16_mono(path, np.zeros(16000 * seconds, dtype=np.float32), 16000)

    def test_edl_check_cli_real_audio_out_f_past_the_wav16_is_e06_and_names_the_clip(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        self._short_wav16(edl_project, 8)  # 240 frames; the inventory still says 360
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 1 and [(e["code"], e["path"]) for e in doc["errors"]] == [
            ("E06", "clips[3]")
        ]
        assert "'a1'" in doc["errors"][0]["message"] and "240" in doc["errors"][0]["message"]

    def test_edl_check_cli_real_audio_the_edl_sources_audio_f_is_the_real_one(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        self._short_wav16(edl_project, 8)
        clips = {
            c["id"]: c for c in kcut_json("edl", "sources", *project_args(edl_project))[1]["clips"]
        }
        assert clips["a1"]["audio_f"] == 240 and clips["a2"]["audio_f"] == 360

    def test_edl_check_cli_real_audio_without_the_wav16_is_exit_3_and_says_ingest(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        remove(edl_project, "a1", "wav16")
        code, doc, _ = kcut_json("edl", "check", *project_args(edl_project))
        assert code == 3 and doc["error"]["message"] == "falta el wav16 de a1; corre kcut ingest"

    def test_edl_check_cli_real_audio_a_clip_whose_wav16_is_gone_has_a_null_audio_f(
        self, edl_project: Path, kcut_json: Run
    ) -> None:
        remove(edl_project, "a1", "wav16")
        clips = {
            c["id"]: c for c in kcut_json("edl", "sources", *project_args(edl_project))[1]["clips"]
        }
        assert clips["a1"]["audio_f"] is None
