"""`kcut pack` with clips that are not just one transcribed camera: untranscribed, mute, extra."""

import json
from pathlib import Path

import numpy as np
import pytest

from tests.unit.test_pack_command import (
    HEADER_LINES,
    LAYOUT,
    SPEECH,
    TSV_HEADER,
    _md,
    _pack,
    _ready,
    _tsv,
)
from tests.unit.transcribe_fakes import FakeClip, tone


class TestOtherClips:
    def _mixed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        s1_audio = np.concatenate([tone(0.5, 0), tone(1.0), tone(6.5, 0)])
        clips = [
            FakeClip("a1", LAYOUT),
            FakeClip("a2", LAYOUT, slug="otra"),
            FakeClip("b1", tone(2.0), slug="muda", clip_class="video_mudo"),
            FakeClip("d1", tone(1.0), slug="brief", clip_class="doc"),
            FakeClip("i1", tone(1.0), slug="foto", clip_class="imagen"),
            FakeClip("s1", s1_audio, slug="voz", clip_class="audio"),
        ]
        script = {"a1": SPEECH, "s1": [("hello", 1000, 1400, 0.99)]}
        return _ready(tmp_path, monkeypatch, clips, script, only=["a1", "s1"])

    def test_an_untranscribed_clip_warns_and_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = self._mixed(tmp_path, monkeypatch)
        capsys.readouterr()
        assert _pack(root) == 0
        assert "[AVISO] a2: sin transcribir; corre kcut transcribe" in capsys.readouterr().out
        lines = _md(root)
        at = lines.index("## a2 - `crudo/otra.mp4`")
        assert lines[at + 1] == "sin transcribir"

    def test_the_json_carries_the_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = self._mixed(tmp_path, monkeypatch)
        capsys.readouterr()
        assert _pack(root, "--json") == 0
        document = json.loads(capsys.readouterr().out)
        assert document["warnings"] == [
            {
                "id": "a2",
                "code": "not_transcribed",
                "message_es": "a2: sin transcribir; corre kcut transcribe",
            }
        ]
        assert [c["id"] for c in document["clips"]] == ["a1", "s1"]

    def test_clips_without_audio_are_listed_and_documents_and_images_are_not(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._mixed(tmp_path, monkeypatch)
        assert _pack(root) == 0
        headings = [line for line in _md(root) if line.startswith("## ")]
        assert [h.split(" - ")[0] for h in headings] == ["## a1", "## a2", "## b1", "## s1"]
        assert "## b1 - `crudo/muda.mp4` - sin audio" in headings

    def test_a_clip_that_did_not_sync_is_read_in_full(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._mixed(tmp_path, monkeypatch)
        assert _pack(root) == 0
        lines = _md(root)
        at = next(i for i, line in enumerate(lines) if line.startswith("## s1"))
        assert lines[at] == "## s1 - `crudo/voz.mp4` - 8.00 s - idioma es (0.97) - sin sincronia"
        assert lines[at + 1] == "[f30-42 | 1.00-1.40] hello"

    def test_nothing_transcribed_still_writes_the_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch, only=["a1"])
        for path in (root / ".kcut" / "transcripts").glob("*.json"):
            path.unlink()
        assert _pack(root) == 0
        assert _md(root)[HEADER_LINES:] == ["## a1 - `crudo/cam.mp4`", "sin transcribir"]
        assert _tsv(root) == [TSV_HEADER]

    def test_without_an_inventory_pack_asks_for_ingest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "p"
        root.mkdir()
        (root / "kcut.toml").write_text("", encoding="utf-8")
        assert _pack(root) == 3
        assert "kcut ingest" in capsys.readouterr().err
        assert not (root / "edit" / "transcripcion.md").exists()


class TestRealLength:
    """Silences are measured over the whole wav16, not over the length the inventory declares."""

    def _liar(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, at_ms: int) -> Path:
        audio = np.concatenate([tone(10.0, 0), tone(10.0), tone(10.0, 0)])  # 30 s
        clip = FakeClip("a1", audio, declared_ms=1000)  # the container says 1 s
        script = {"a1": [("gracias", at_ms, at_ms + 800, 0.9)]}
        return _ready(tmp_path, monkeypatch, [clip], script)

    def test_transcribe_pack_real_length_silences_cover_the_30_s(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._liar(tmp_path, monkeypatch, 25_000)  # far past the declared 1 s, in silence
        assert _pack(root) == 0
        lines = _md(root)
        assert lines[HEADER_LINES].startswith("## a1 - `crudo/cam.mp4` - 30.00 s - ")
        assert lines[-1].endswith("gracias (¿alucinacion?)")
        assert _tsv(root)[1][6] == "H"

    def test_transcribe_pack_real_length_a_word_over_loud_audio_is_not_flagged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._liar(tmp_path, monkeypatch, 15_000)
        assert _pack(root) == 0
        assert "alucinacion" not in "\n".join(_md(root)[HEADER_LINES:])
        assert _tsv(root)[1][6] == ""


def test_pack_writes_nothing_outside_edit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _ready(tmp_path, monkeypatch)
    before = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert _pack(root) == 0
    after = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert after - before == {"edit/transcripcion.md", "edit/palabras.tsv"}
    assert before - after == set()
