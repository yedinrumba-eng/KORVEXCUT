"""The transcript file and the index: shape, round trip, and distrust of what `.kcut/` holds."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.commands import pack as pack_cmd
from kcut.commands import transcribe as transcribe_cmd
from kcut.errors import ProjectError
from kcut.ingest.inventory import Notice
from kcut.transcribe import cache
from tests.unit.test_pack_command import _pack, _ready
from tests.unit.transcribe_fakes import (
    SHA,
    TRUNCATED_WAV,
    FakeClip,
    build_project,
    install_fake_engine,
    params_for,
    riff_bytes,
    sample_transcript,
    tone,
)


class TestFile:
    def test_the_document_has_the_documented_shape(self) -> None:
        params = params_for()
        doc = cache.to_document(sample_transcript("k" * 64, params), SHA)
        assert list(doc) == [
            "schema",
            "key",
            "wav_sha256",
            "params",
            "language",
            "language_p",
            "duration_ms",
            "elapsed_s",
            "words",
            "segments",
        ]
        assert doc["schema"] == "kcut.transcript/1" and doc["params"] == params
        assert doc["words"][0] == {"i": 0, "w": "Bueno,", "s_ms": 53_412, "e_ms": 53_780, "p": 0.91}
        assert doc["segments"] == [{"s_ms": 53_412, "e_ms": 54_300, "text": "Bueno, hola"}]

    def test_save_and_load_roundtrip_composes_the_word_ids(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1))])
        key = cache.cache_key(SHA, params_for())
        original = sample_transcript(key, params_for())
        cache.save_transcript(project, original, SHA)
        loaded = cache.load_transcript(project, "a1")
        assert loaded == replace(original, wav_sha256=SHA)  # read back, it knows its audio
        assert [w.id for w in loaded.words] == ["a1:w0000", "a1:w0001"]  # type: ignore[union-attr]

    def test_the_index_maps_clips_to_keys(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1))])
        cache.save_transcript(project, sample_transcript("a" * 64, params_for()), SHA)
        other = replace(sample_transcript("b" * 64, params_for()), clip_id="a2")
        cache.save_transcript(project, other, SHA)
        index = json.loads((project.layout.transcripts / "index.json").read_text(encoding="utf-8"))
        assert index == {"a1": "a" * 64, "a2": "b" * 64}
        assert (project.layout.transcripts / f"{'a' * 64}.json").is_file()

    def test_a_clip_without_a_transcript_loads_as_none(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1))])
        assert cache.load_transcript(project, "a1") is None

    def test_load_matching_needs_the_same_audio_and_parameters(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1))])
        params = params_for()
        key = cache.cache_key(SHA, params)
        cache.save_transcript(project, sample_transcript(key, params), SHA)
        notices: list[Notice] = []
        assert cache.load_matching(project, "a1", key, SHA, params, notices) is not None
        assert cache.load_matching(project, "a1", key, "beef" * 16, params, notices) is None
        other = {**params, "beam_size": 9}
        assert cache.load_matching(project, "a1", key, SHA, other, notices) is None
        assert cache.load_matching(project, "a1", "f" * 64, SHA, params, notices) is None

    def test_point_index_writes_only_when_it_changes(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1))])
        cache.point_index(project, "a1", "a" * 64)
        index = project.layout.transcripts / "index.json"
        before = index.stat().st_mtime_ns
        cache.point_index(project, "a1", "a" * 64)
        assert index.stat().st_mtime_ns == before
        cache.point_index(project, "a1", "b" * 64)
        assert json.loads(index.read_text(encoding="utf-8")) == {"a1": "b" * 64}


class TestDistrust:
    """Nothing in `.kcut/` is trusted: what does not validate counts as absent (spec 0.9)."""

    def _saved(self, tmp_path: Path) -> tuple[Any, str, Path]:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1))])
        key = cache.cache_key(SHA, params_for())
        cache.save_transcript(project, sample_transcript(key, params_for()), SHA)
        return project, key, cache.transcript_path(project, key)

    def _edit(self, path: Path, change: Any) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")

    @pytest.mark.parametrize(
        "change",
        [
            lambda d: d.update(schema="kcut.transcript/2"),
            lambda d: d.update(key="e" * 64),
            lambda d: d.update(extra=1),
            lambda d: d.pop("words"),
            lambda d: d.update(language="español"),
            lambda d: d.update(language_p=1.5),
            lambda d: d.update(duration_ms="largo"),
            lambda d: d.update(duration_ms=10**15),
            lambda d: d["words"][1].update(i=5),
            lambda d: d["words"][0].update(e_ms=d["words"][0]["s_ms"]),
            lambda d: d["words"][0].update(w=""),
            lambda d: d["words"][0].update(w="x" * 201),
            lambda d: d["words"][0].update(p=2),
            lambda d: d["words"][0].update(s_ms=-1),
            lambda d: d["words"][0].update(extra=1),
            lambda d: d["words"][0].update(s_ms=1.5),
            lambda d: d["segments"][0].update(text=5),
            lambda d: d["params"].update(nested={"a": 1}),
            lambda d: d.update(wav_sha256="no es un hash"),
        ],
        ids=[
            "schema", "key", "extra_key", "no_words", "language", "language_p", "duration_str",
            "duration_huge", "word_index", "word_end", "word_empty", "word_long", "word_p",
            "word_negative", "word_extra", "word_float", "segment_text", "params_nested", "sha",
        ],
    )  # fmt: skip
    def test_an_invalid_transcript_is_absent_and_reported(
        self, tmp_path: Path, change: Any
    ) -> None:
        project, key, path = self._saved(tmp_path)
        self._edit(path, change)
        notices: list[Notice] = []
        assert cache.load_matching(project, "a1", key, SHA, params_for(), notices) is None
        assert [n.code for n in notices] == ["transcript_invalid"]

    def test_garbage_is_absent_and_reported(self, tmp_path: Path) -> None:
        project, key, path = self._saved(tmp_path)
        path.write_text("{ no es json", encoding="utf-8")
        notices: list[Notice] = []
        assert cache.load_matching(project, "a1", key, SHA, params_for(), notices) is None
        assert cache.load_transcript(project, "a1", notices) is None
        assert [n.code for n in notices] == ["transcript_invalid", "transcript_invalid"]

    @pytest.mark.parametrize(
        "index",
        [{"../x": "a" * 64}, {"a1": "../../etc"}, {"a1": 5}, [], {"a1": "A" * 64}],
        ids=["bad_clip", "bad_key", "key_not_text", "not_an_object", "upper_case_key"],
    )
    def test_a_poisoned_index_is_ignored(self, tmp_path: Path, index: Any) -> None:
        project, _, _ = self._saved(tmp_path)
        (project.layout.transcripts / "index.json").write_text(json.dumps(index), encoding="utf-8")
        notices: list[Notice] = []
        assert cache.load_transcript(project, "a1", notices) is None
        assert [n.code for n in notices] == ["cache_rebuilt"]


class TestLyingHeaderThroughTheCommands:
    def test_lying_header_pack_exits_3_with_the_fixed_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        wav = root / ".kcut" / "wav16" / "a1_cam.wav"
        wav.write_bytes(riff_bytes(0xFFFFFFF0, b"\0" * 200))
        capsys.readouterr()
        assert _pack(root) == 3
        assert TRUNCATED_WAV in capsys.readouterr().err
        assert not (root / "edit" / "transcripcion.md").exists()

    def test_lying_header_transcribe_exits_3_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        (root / ".kcut" / "wav16" / "a1_cam.wav").write_bytes(riff_bytes(101, b"\0" * 101))
        capsys.readouterr()
        assert cli.main(["transcribe", "--project", str(root), "--force"]) == 3
        assert TRUNCATED_WAV in capsys.readouterr().err

    def test_lying_header_the_engine_refuses_it_before_decoding(self, tmp_path: Path) -> None:
        from kcut.transcribe.engine import _read_wav16

        path = tmp_path / "x.wav"
        path.write_bytes(riff_bytes(0xFFFFFFF0, b"\0" * 64))
        with pytest.raises(ProjectError, match="truncado"):
            _read_wav16(path)


class TestIndexReadOnce:
    """001.14 point 6: one read of `index.json` per command, and a cap on what it may hold."""

    def _count(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        calls: list[str] = []
        real = cache.read_index

        def counting(*args: Any, **kwargs: Any) -> dict[str, str]:
            calls.append("read")
            return real(*args, **kwargs)

        for module in (cache, transcribe_cmd, pack_cmd):
            monkeypatch.setattr(module, "read_index", counting, raising=False)
        return calls

    def _three(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        clips = [FakeClip(f"a{i}", tone(2.0 + i / 10), slug=f"c{i}") for i in (1, 2, 3)]
        script = {f"a{i}": [("hola", 100, 400, 0.9)] for i in (1, 2, 3)}
        install_fake_engine(monkeypatch, script)
        return build_project(tmp_path / "proyecto ñandú", clips).root

    def test_index_read_once_per_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._three(tmp_path, monkeypatch)
        calls = self._count(monkeypatch)
        assert cli.main(["transcribe", "--project", str(root)]) == 0
        assert len(calls) == 1  # three clips transcribed and indexed, one read
        assert cli.main(["transcribe", "--project", str(root)]) == 0
        assert len(calls) == 2  # all cached: again one read
        assert _pack(root) == 0
        assert len(calls) == 3
        index = json.loads((root / ".kcut/transcripts/index.json").read_text(encoding="utf-8"))
        assert sorted(index) == ["a1", "a2", "a3"]

    def test_index_read_once_a_big_index_is_ignored_with_a_fixed_notice(
        self, tmp_path: Path
    ) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        path = project.layout.transcripts / "index.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"a1": "' + "a" * 64 + '"}' + " " * (1024 * 1024), encoding="utf-8")
        notices: list[Notice] = []
        assert cache.read_index(project, notices) == {}
        assert [n.code for n in notices] == ["cache_rebuilt"] and "índice" in notices[0].detail

    @pytest.mark.parametrize(("entries", "kept"), [(10_000, True), (10_001, False)])
    def test_index_read_once_entry_cap(self, tmp_path: Path, entries: int, kept: bool) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        path = project.layout.transcripts / "index.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        index = {f"a{i}": "b" * 64 for i in range(1, entries + 1)}
        path.write_text(json.dumps(index), encoding="utf-8")
        notices: list[Notice] = []
        assert (len(cache.read_index(project, notices)) == entries) is kept
        assert bool(notices) is not kept
