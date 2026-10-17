"""`kcut ingest` output on the synthetic project: JSON document, human lines, logs."""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from kcut.audio.wavio import write_wav_s16_mono
from tests.conftest import run_kcut
from tests.fixtures.synth_media import MediaTruth
from tests.unit.sync_signals import SR, speechlike, world

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]

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


def _ingest(root: Path) -> tuple[int, str, str]:
    result = run_kcut("ingest", "--project", str(root), "--no-proxy")
    return result.returncode, result.stdout.replace("\r\n", "\n"), result.stderr


def _edit_inventory(root: Path, change: Callable[[dict[str, Any]], object]) -> None:
    path = root / ".kcut" / "inventory.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def _master_is_s1(root: Path) -> None:
    toml = root / "kcut.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace('master = ""', 'master = "s1"'))


class TestHumanLinesNeverPrintStoredText:
    """The `AVISO`/`OK` lines come from fixed tables, never from `reason` or `method` (001.7)."""

    @pytest.fixture
    def rejected_pair(self, blank: Path) -> Path:
        """Periodic audio, 12 s, B 4 s later: rejected as ambiguous."""
        write_wav_s16_mono(blank / "crudo" / "a.wav", world(0.0), SR)
        write_wav_s16_mono(blank / "crudo" / "b.wav", world(4.0), SR)
        _master_is_s1(blank)
        assert _ingest(blank)[0] == 0
        return blank

    @pytest.fixture
    def accepted_pair(self, blank: Path) -> Path:
        scene = speechlike(60, 7)
        write_wav_s16_mono(blank / "crudo" / "a.wav", scene[: 30 * SR], SR)
        write_wav_s16_mono(blank / "crudo" / "b.wav", scene[2 * SR : 32 * SR], SR)
        _master_is_s1(blank)
        code, out, _ = _ingest(blank)
        assert code == 0 and re.search(r"\[OK\] s2: offset \+\d+ ms \(envelope\+raw\)\n", out)
        return blank

    def test_reason_hygiene_the_line_comes_from_the_fixed_table(self, rejected_pair: Path) -> None:
        _edit_inventory(
            rejected_pair,
            lambda d: d["sync"]["rejected"][0].update(reason="sync_weak_refine: texto-propio-xyz"),
        )
        code, out, err = _ingest(rejected_pair)
        assert code == 0
        assert "[AVISO] s2: sin sincronía - el audio fino no coincide lo bastante\n" in out
        assert "texto-propio-xyz" not in out + err

    def test_reason_hygiene_a_reason_kcut_does_not_write_gets_no_text(
        self, rejected_pair: Path
    ) -> None:
        _edit_inventory(
            rejected_pair,
            lambda d: d["sync"]["rejected"][0].update(reason="un texto que kcut no escribe"),
        )
        code, out, err = _ingest(rejected_pair)
        assert code == 0 and "[AVISO] s2: sin sincronía\n" in out
        assert "un texto que kcut no escribe" not in out + err

    def test_reason_hygiene_escape_sequences_invalidate_the_inventory(
        self, rejected_pair: Path
    ) -> None:
        hostile = "\x1b]0;pwned\x07\x1b[2J\r"
        _edit_inventory(rejected_pair, lambda d: d["sync"]["rejected"][0].update(reason=hostile))
        code, out, err = _ingest(rejected_pair)
        assert code == 0 and "inventory_invalid" in err
        assert "\x1b" not in out + err and "\r" not in out.replace("\r\n", "")

    def test_method_hygiene_an_unknown_method_is_not_printed(self, accepted_pair: Path) -> None:
        _edit_inventory(
            accepted_pair, lambda d: d["sync"]["members"][0].update(method="metodo-raro")
        )
        code, out, err = _ingest(accepted_pair)
        assert code == 0 and re.search(r"\[OK\] s2: offset \+\d+ ms\n", out)
        assert "metodo-raro" not in out + err

    def test_method_hygiene_escape_sequences_invalidate_the_inventory(
        self, accepted_pair: Path
    ) -> None:
        _edit_inventory(
            accepted_pair, lambda d: d["sync"]["members"][0].update(method="\x1b[2Jlimpia")
        )
        code, out, err = _ingest(accepted_pair)
        assert code == 0 and "inventory_invalid" in err and "\x1b" not in out + err
