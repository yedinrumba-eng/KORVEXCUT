"""`kcut pack` on one transcribed camera: the whole document, the tsv, the config, the sounds."""

import json
from pathlib import Path

import numpy as np
import pytest

from tests.unit.test_pack_command import (
    HEADER_LINES,
    TSV_HEADER,
    _md,
    _pack,
    _ready,
    _tsv,
)
from tests.unit.transcribe_fakes import FakeClip, tone


class TestOneCamera:
    def test_the_whole_document(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        root = _ready(tmp_path, monkeypatch)
        assert _pack(root) == 0
        assert _md(root)[HEADER_LINES:] == [
            "## a1 - `crudo/cam.mp4` - 8.00 s - idioma es (0.97) - maestro de sincronia",
            "[f30-90 | 1.00-3.00] ¿Te da {eh} curiosidad",
            "[f135-180 | 4.50-6.00] (pausa 1.50 s LARGA) «{bueno bueno}» hola?",
        ]

    def test_the_header_names_the_project_and_the_fps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(
            tmp_path, monkeypatch, toml='[project]\nname = "piloto 01"\n[output]\nfps = 25\n'
        )
        assert _pack(root) == 0
        lines = _md(root)
        assert lines[0] == "# Transcripcion - piloto 01"
        assert lines[2].startswith("fps 25 · tiempos de fuente")
        assert lines[4].startswith("Antes de botar una pausa LARGA")
        assert "[f25-75 | 1.00-3.00]" in lines[HEADER_LINES + 1]

    def test_the_tsv_has_one_row_per_word_with_frames_seconds_and_flags(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        assert _pack(root) == 0
        rows = _tsv(root)
        assert rows[0] == TSV_HEADER
        assert len(rows) == 8
        assert rows[1] == ["a1:w0000", "a1", "30", "39", "1.00", "0.90", "", "¿Te", "", ""]
        assert rows[3][6] == "F" and rows[4] == [
            "a1:w0003", "a1", "54", "102", "1.80", "0.90", "", "curiosidad", "", ""
        ]  # fmt: skip
        assert [r[6] for r in rows[5:]] == ["F", "FR", "?"]
        assert rows[6][1:6] == ["a1", "150", "165", "5.00", "0.90"]
        assert rows[7][1:6] == ["a1", "165", "180", "5.50", "0.20"]

    def test_the_files_are_utf8_with_unix_newlines_and_the_run_is_repeatable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        assert _pack(root) == 0
        first = [(root / "edit" / n).read_bytes() for n in ("transcripcion.md", "palabras.tsv")]
        assert _pack(root) == 0
        again = [(root / "edit" / n).read_bytes() for n in ("transcripcion.md", "palabras.tsv")]
        assert first == again and all(b"\r" not in b and b.endswith(b"\n") for b in first)
        assert "¿Te".encode() in first[0]

    def test_json_and_human_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        capsys.readouterr()
        assert _pack(root) == 0
        assert (
            capsys.readouterr().out
            == "[OK] edit/transcripcion.md y edit/palabras.tsv: 1 clips con texto\n"
        )
        assert _pack(root, "--json") == 0
        assert json.loads(capsys.readouterr().out) == {
            "ok": True,
            "md": "edit/transcripcion.md",
            "tsv": "edit/palabras.tsv",
            "clips": [{"id": "a1", "words": 7, "phrases": 2}],
            "warnings": [],
        }

    def test_the_config_decides_pauses_fillers_and_doubt(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = "[analysis]\nphrase_pause_ms = 3000\nlong_pause_ms = 4000\nlow_prob = 0.1\n"
        toml += '[transcribe]\nfillers = ["curiosidad"]\n'
        root = _ready(tmp_path, monkeypatch, toml=toml)
        assert _pack(root) == 0
        # one phrase now (the silences are shorter than 3 s), "hola" is no longer doubtful
        assert _md(root)[HEADER_LINES + 1 :] == [
            "[f30-180 | 1.00-6.00] ¿Te da eh {curiosidad} «bueno bueno» hola"
        ]

    def test_voice_without_words_is_listed_in_its_place(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audio = np.concatenate([tone(1.0, 0), tone(1.0), tone(1.0, 0), tone(1.0)])
        root = _ready(
            tmp_path, monkeypatch, [FakeClip("a1", audio)], {"a1": [("hola", 3000, 4000, 0.9)]}
        )
        assert _pack(root) == 0
        assert _md(root)[HEADER_LINES + 1 :] == [
            "<sonido sin texto 1.00 s f30-60>",
            "[f90-120 | 3.00-4.00] hola",
        ]
