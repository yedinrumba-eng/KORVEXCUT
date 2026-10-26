"""More caps, round 5 (spec 001.17, point 9): corrections across all the clips, and a file that
grew while it was being read."""

import json
from pathlib import Path

import pytest

from kcut import jsonio
from kcut.errors import CheckFailed, ProjectError
from kcut.jsonio import read_capped, read_json
from kcut.text import corrections
from kcut.text.corrections import Correction, apply_all
from kcut.transcribe.model import Word
from tests.unit.test_pack_command import _pack, _ready
from tests.unit.transcribe_fakes import FakeClip, Spoken, tone

MIB = 1024 * 1024


class TestCorrectionsGlobalCap:
    """001.17 point 9: the tokens the corrections produce are counted across ALL the clips."""

    @staticmethod
    def _clips(count: int, words: int = 10) -> dict[str, list[Word]]:
        return {
            f"a{k}": [
                Word(f"a{k}:w{i:04d}", i, f"w{i}", i * 200, i * 200 + 150, 0.9)
                for i in range(words)
            ]
            for k in range(1, count + 1)
        }

    @staticmethod
    def _fixes(clips: dict[str, list[Word]], tokens: int) -> dict[str, Correction]:
        text = " ".join(["t"] * tokens)
        return {w.id: Correction(w.id, w.text, text) for words in clips.values() for w in words}

    def test_corrections_global_cap_is_200000(self) -> None:
        assert corrections.MAX_TOTAL_TOKENS == 200_000

    def test_corrections_global_cap_many_clips_below_their_own_cap_still_fail(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(corrections, "MAX_TOTAL_TOKENS", 1_000)
        clips = self._clips(3)  # 500 tokens per clip: each one alone is far from its cap
        with pytest.raises(CheckFailed, match="entre todos los clips"):
            apply_all(clips, self._fixes(clips, 50))

    def test_corrections_global_cap_exactly_the_cap_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(corrections, "MAX_TOTAL_TOKENS", 1_000)
        clips = self._clips(2)
        fixed = apply_all(clips, self._fixes(clips, 50))
        assert sum(len(words) for words in fixed.values()) == 1_000

    def test_corrections_global_cap_words_without_corrections_do_not_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(corrections, "MAX_TOTAL_TOKENS", 10)
        clips = self._clips(5)
        assert apply_all(clips, {}) == clips

    def test_corrections_global_cap_through_pack_the_exit_is_1(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(corrections, "MAX_TOTAL_TOKENS", 30)
        spoken: list[Spoken] = [(f"w{i}", 500 + i * 300, 700 + i * 300, 0.9) for i in range(4)]
        clips = [FakeClip("a1", tone(4.0)), FakeClip("a2", tone(4.0, 0.4), slug="c2")]
        root = _ready(tmp_path, monkeypatch, clips, {"a1": spoken, "a2": spoken})
        text = " ".join(["t"] * 5)  # 4 words x 5 tokens x 2 clips = 40 > 30
        items = [
            {"word": f"a{k}:w000{i}", "expect": f"w{i}", "text": text}
            for k in (1, 2)
            for i in range(4)
        ]
        (root / "edit").mkdir(exist_ok=True)
        document = {"schema": "kcut.correcciones/1", "items": items}
        (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")
        capsys.readouterr()
        assert _pack(root, "--json") == 1
        assert "entre todos los clips" in json.loads(capsys.readouterr().out)["error"]["message"]


class TestReadCappedGrew:
    """001.17 point 9: a file that grew between the `stat` and the read is a ProjectError."""

    def _lie_about_the_size(self, monkeypatch: pytest.MonkeyPatch, size: int) -> None:
        class Stat:
            st_size = size

        monkeypatch.setattr(jsonio.os, "fstat", lambda fd: Stat())

    def test_read_capped_grew_after_the_stat(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "a.json"
        path.write_bytes(b'{"a": 1}' + b" " * 100)  # 108 bytes on disk
        self._lie_about_the_size(monkeypatch, 8)  # the `stat` saw only 8
        with pytest.raises(ProjectError, match="cambió mientras se leía"):
            read_capped(path, MIB)

    def test_read_capped_grew_read_json_says_the_same(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "a.json"
        path.write_bytes(b'{"a": 1}' + b" " * 100)
        self._lie_about_the_size(monkeypatch, 8)
        with pytest.raises(ProjectError, match="cambió mientras se leía"):
            read_json(path)

    def test_read_capped_grew_a_file_that_did_not_change_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / "a.json"
        path.write_bytes(b'{"a": 1}')
        assert read_capped(path, MIB) == b'{"a": 1}'
        path.write_bytes(b"")
        assert read_capped(path, MIB) == b""

    def test_read_capped_grew_past_the_cap_it_is_still_too_big(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "a.json"
        path.write_bytes(b" " * 50)
        self._lie_about_the_size(monkeypatch, 10)
        with pytest.raises(ProjectError):
            read_capped(path, 10)
