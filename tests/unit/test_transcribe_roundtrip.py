"""What the engine writes can always be read back (spec 001.12, point 6), and the Whisper prompt
stays inside 1000 characters, saying so when it leaves terms out."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.config.load import parse_config
from kcut.errors import InternalError
from kcut.ingest.inventory import Notice
from kcut.transcribe import cache
from kcut.transcribe.engine import Engine, build_prompt
from tests.unit.transcribe_fakes import (
    SHA,
    FakeClip,
    build_project,
    install_fake_engine,
    params_for,
    sample_transcript,
    tone,
)
from tests.unit.whisper_fakes import FakeWhisper, install_whisper, segment, word


@pytest.fixture
def whisper(monkeypatch: pytest.MonkeyPatch) -> type[FakeWhisper]:
    return install_whisper(monkeypatch)


def _long_clip(tmp_path: Path) -> Path:
    return build_project(tmp_path / "proyecto ñandú", [FakeClip("a1", tone(60.0))]).root


class TestEngineOutputRoundtrip:
    def test_engine_output_roundtrip_a_word_of_500_characters_is_cut_to_200(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        whisper.segments = [segment(0, 2, "x", word(" " + "a" * 500, 0.5, 1.0))]
        root = _long_clip(tmp_path)
        engine = Engine(parse_config("", default_name="x").transcribe, allow_download=False)
        wav = root / ".kcut" / "wav16" / "a1_cam.wav"
        assert engine.transcribe(wav, "", None, None).words[0].text == "a" * 200

    def test_engine_output_roundtrip_a_word_of_40_s_ends_at_30_s(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        whisper.segments = [
            segment(0, 45, "x", word(" largo", 1.0, 41.0), word(" fin", 50.0, 59.0))
        ]
        root = _long_clip(tmp_path)
        engine = Engine(parse_config("", default_name="x").transcribe, allow_download=False)
        words = engine.transcribe(root / ".kcut/wav16/a1_cam.wav", "", None, None).words
        assert [(w.s_ms, w.e_ms) for w in words] == [(1000, 31_000), (50_000, 59_000)]

    def test_engine_output_roundtrip_the_second_run_is_cached(
        self, tmp_path: Path, whisper: type[FakeWhisper], capsys: pytest.CaptureFixture[str]
    ) -> None:
        whisper.segments = [
            segment(
                0,
                45,
                "x",
                word(" " + "a" * 500, 0.5, 1.0),
                word(" largo", 2.0, 42.0),
                word(" fin", 59.5, 70.0),
            )
        ]
        root = _long_clip(tmp_path)
        args = ["transcribe", "--project", str(root), "--json"]
        assert cli.main(args) == 0
        assert json.loads(capsys.readouterr().out)["clips"][0]["cached"] is False
        assert cli.main(args) == 0
        captured = capsys.readouterr()
        assert json.loads(captured.out)["clips"][0]["cached"] is True
        assert "transcript_invalid" not in captured.err
        key = json.loads((root / ".kcut/transcripts/index.json").read_text(encoding="utf-8"))["a1"]
        stored = json.loads((root / f".kcut/transcripts/{key}.json").read_text(encoding="utf-8"))
        assert [len(w["w"]) for w in stored["words"]] == [200, 5, 3]
        assert stored["words"][1]["e_ms"] - stored["words"][1]["s_ms"] == 30_000
        assert stored["words"][2]["e_ms"] == 60_000  # cut at the wav16's own end

    def test_engine_output_roundtrip_save_transcript_checks_before_writing(
        self, tmp_path: Path
    ) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        key = cache.cache_key(SHA, params_for())
        good = sample_transcript(key, params_for())
        words = [replace(w, e_ms=w.s_ms + 31_000) for w in good.words]
        bad = replace(good, words=words, duration_ms=100_000)  # a word of 31 s cannot be read back
        with pytest.raises(InternalError):
            cache.save_transcript(project, bad, SHA)
        assert not cache.transcript_path(project, key).exists()
        cache.save_transcript(project, replace(good, duration_ms=100_000), SHA)  # the good one
        assert cache.transcript_path(project, key).is_file()


class TestEngineKeepsWhatItWritesReadable:
    """Whatever the library returns, the engine hands back words that `from_document` accepts."""

    def _words(
        self, tmp_path: Path, whisper: type[FakeWhisper], seconds: float, *words: Any
    ) -> Any:
        whisper.segments = [segment(0, seconds, "x", *words)]
        root = build_project(tmp_path / "p", [FakeClip("a1", tone(seconds))]).root
        engine = Engine(parse_config("", default_name="x").transcribe, allow_download=False)
        return engine.transcribe(root / ".kcut/wav16/a1_cam.wav", "", None, None).words

    def test_engine_output_roundtrip_a_word_after_the_end_of_the_audio_is_dropped(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        words = self._words(tmp_path, whisper, 2.0, word(" a", 0.5, 1.0), word(" b", 2.0, 2.5),
                            word(" c", 3.0, 3.5))  # fmt: skip
        assert [w.text for w in words] == ["a"]

    def test_engine_output_roundtrip_starts_never_go_back(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        words = self._words(tmp_path, whisper, 3.0, word(" a", 1.0, 1.5), word(" b", 0.8, 1.2),
                            word(" c", 2.0, 2.5))  # fmt: skip
        assert [(w.i, w.s_ms) for w in words] == [(0, 1000), (1, 1000), (2, 2000)]
        assert all(w.e_ms > w.s_ms for w in words)

    def test_engine_output_roundtrip_there_are_no_more_words_than_the_audio_can_hold(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        loop = [word(" la", 0.5 + i * 0.001, 0.6 + i * 0.001) for i in range(500)]
        words = self._words(tmp_path, whisper, 2.0, *loop)  # 10 * 2 + 100 = 120 words at most
        assert len(words) == 120 and words[-1].i == 119

    def test_engine_output_roundtrip_an_inverted_segment_is_made_whole(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        whisper.segments = [segment(1.5, 1.0, "x" * 30_000)]
        root = build_project(tmp_path / "p", [FakeClip("a1", tone(2.0))]).root
        engine = Engine(parse_config("", default_name="x").transcribe, allow_download=False)
        (made,) = engine.transcribe(root / ".kcut/wav16/a1_cam.wav", "", None, None).segments
        assert (made.s_ms, made.e_ms, len(made.text)) == (1500, 1500, 20_000)

    def test_engine_output_roundtrip_a_hostile_run_is_saved_and_cached(
        self, tmp_path: Path, whisper: type[FakeWhisper], capsys: pytest.CaptureFixture[str]
    ) -> None:
        nasty = [
            word(" " + "z" * 900, 0.2, 0.4),
            word(" largo", 0.5, 90.0),
            word(" atras", 0.1, 0.2),
            word(" fuera", 70.0, 71.0),
        ] + [word(" x", 1.0 + i * 0.001, 1.001 + i * 0.001) for i in range(900)]
        whisper.segments = [segment(0, 60, "x", *nasty)]
        root = _long_clip(tmp_path)
        args = ["transcribe", "--project", str(root), "--json"]
        assert cli.main(args) == 0 and cli.main(args) == 0
        documents = capsys.readouterr().out.split("\n}\n")
        assert '"cached": false' in documents[0] and '"cached": true' in documents[1]


def _terms(count: int) -> list[str]:
    return [f"t{i:03d}" + "x" * 35 for i in range(count)]  # 40 characters each


def _config(terms: list[str], extra: str = "") -> Any:
    toml = f"[glossary]\nterms = {json.dumps(terms)}\n"
    toml += f"[transcribe]\nprompt_extra = {json.dumps(extra)}\n"
    return parse_config(toml, default_name="x")


class TestPromptTruncated:
    def test_prompt_truncated_a_full_glossary_stays_under_1000_and_says_how_many(self) -> None:
        terms = _terms(200)
        notices: list[Notice] = []
        prompt = build_prompt(_config(terms), notices)
        kept = [t for t in terms if t in prompt]
        assert len(prompt) <= 1000 and kept == terms[: len(kept)] and 0 < len(kept) < 200
        left_out = 200 - len(kept)
        assert [n.code for n in notices] == ["prompt_truncated"]
        assert str(left_out) in notices[0].detail and "1000" in notices[0].detail
        assert prompt.startswith("Eh, ehh, em")  # the fillers come first and all fit

    def test_prompt_truncated_the_extra_text_is_kept_and_counted(self) -> None:
        extra = "Habla un dominicano. " * 19  # 399 characters
        notices: list[Notice] = []
        prompt = build_prompt(_config(_terms(200), extra), notices)
        assert len(prompt) <= 1000 and prompt.endswith(extra)
        assert [n.code for n in notices] == ["prompt_truncated"]

    def test_prompt_truncated_fillers_that_do_not_fit_are_left_out_too(self) -> None:
        fillers = [f"f{i:02d}" + "y" * 35 for i in range(50)]
        toml = f"[transcribe]\nfillers = {json.dumps(fillers)}\n[glossary]\nterms = ['Korvex']\n"
        notices: list[Notice] = []
        prompt = build_prompt(parse_config(toml, default_name="x"), notices)
        assert len(prompt) <= 1000 and "Korvex" not in prompt and prompt.endswith(".")
        left_out = 51 - sum(
            1 for f in fillers if f.lower() in prompt.lower()
        )  # 50 fillers and one term
        assert notices[0].code == "prompt_truncated" and str(left_out) in notices[0].detail

    def test_prompt_truncated_a_short_prompt_has_no_notice(self) -> None:
        notices: list[Notice] = []
        prompt = build_prompt(_config(["Korvex", "Claude"]), notices)
        assert prompt.endswith("Korvex, Claude.") and notices == []

    def test_prompt_truncated_the_prompt_is_the_same_with_or_without_a_notices_list(self) -> None:
        config = _config(_terms(200))
        assert build_prompt(config) == build_prompt(config, [])

    def test_prompt_truncated_reaches_the_user_and_the_cache_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake = install_fake_engine(monkeypatch, {"a1": [("hola", 100, 400, 0.9)]})
        root = build_project(tmp_path / "p", [FakeClip("a1", tone(2.0))]).root
        toml = f"[glossary]\nterms = {json.dumps(_terms(200))}\n"
        (root / "kcut.toml").write_text(toml, encoding="utf-8")
        assert cli.main(["transcribe", "--project", str(root), "--json"]) == 0
        assert "prompt_truncated" in capsys.readouterr().err
        assert len(fake.args[0][0]) <= 1000
