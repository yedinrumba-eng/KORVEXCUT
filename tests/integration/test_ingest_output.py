"""`kcut ingest` output on the synthetic project: JSON document, human lines, logs."""

import json
from pathlib import Path

import pytest

from tests.conftest import run_kcut
from tests.fixtures.synth_media import MediaTruth

pytestmark = pytest.mark.ffmpeg

Project = tuple[Path, MediaTruth]


class TestCommandOutput:
    def test_json_is_one_document_with_the_documented_keys(self, synth_project: Project) -> None:
        result = run_kcut("ingest", "--project", str(synth_project[0]), "--json")
        doc = json.loads(result.stdout)
        assert result.returncode == 0
        assert set(doc) == {"ok", "inventory", "clips", "by_class", "sync", "warnings", "elapsed_s"}
        assert doc["ok"] is True
        assert doc["inventory"] == ".kcut/inventory.json"
        assert doc["clips"] == 5
        assert doc["by_class"] == {"doc": 1, "video_voz": 2, "imagen": 1, "video_mudo": 1}
        assert doc["sync"]["master"] == "a1"
        assert doc["sync"]["members"][0]["id"] == "a2"
        assert {"id": "a2", "code": "hdr"} in doc["warnings"]
        assert doc["elapsed_s"] >= 0

    def test_human_output(self, synth_project: Project) -> None:
        result = run_kcut("ingest", "--project", str(synth_project[0]))
        assert result.returncode == 0
        assert "[OK] a1: video_voz - crudo/cam a.mp4" in result.stdout
        assert "[AVISO] a2: hdr" in result.stdout
        assert (
            "[OK] a2: offset +1200 ms" in result.stdout
            or "[OK] a2: offset +1201 ms" in result.stdout
        )
        assert "—" not in result.stdout

    def test_it_runs_from_inside_the_project(self, synth_project: Project) -> None:
        result = run_kcut("ingest", "--json", cwd=synth_project[0] / "crudo")
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)["clips"] == 5

    def test_outside_a_project_it_is_a_project_error(self, tmp_path: Path) -> None:
        result = run_kcut("ingest", "--json", cwd=tmp_path)
        assert result.returncode == 3
        assert json.loads(result.stdout)["error"]["kind"] == "ProjectError"

    def test_crudo_is_never_written(self, synth_project: Project) -> None:
        crudo = synth_project[0] / "crudo"
        assert sorted(p.name for p in crudo.iterdir()) == [
            "brief.txt",
            "cam a.mp4",
            "cam b.mov",
            "foto.png",
            "pantalla.mp4",
        ]

    def test_the_log_records_each_child(self, synth_project: Project) -> None:
        logs = sorted((synth_project[0] / ".kcut" / "logs").glob("ingest-*.log"))
        assert logs
        text = logs[0].read_text(encoding="utf-8")
        assert text.count("$ ") >= 6
        assert "-loglevel error" in text
        assert "[exit 0" in text
