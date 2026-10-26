"""The Whisper engine against a stand-in model: prompt, settings, word times, missing model."""

import json
import math
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from kcut import cli
from kcut.config.load import parse_config
from kcut.console import Progress
from kcut.errors import MissingDependency
from kcut.transcribe.engine import Engine
from tests.unit.transcribe_fakes import FakeClip, build_project, tone
from tests.unit.whisper_fakes import FakeWhisper, install_whisper, segment, word


def _cfg(toml: str = "") -> Any:
    return parse_config(toml, default_name="x")


@pytest.fixture
def whisper(monkeypatch: pytest.MonkeyPatch) -> type[FakeWhisper]:
    return install_whisper(monkeypatch)


class TestLoading:
    def test_the_model_is_loaded_for_this_cpu_and_never_downloaded_by_default(
        self, whisper: type[FakeWhisper]
    ) -> None:
        Engine(_cfg("[transcribe]\ncpu_threads = 3\n").transcribe, allow_download=False)
        ((model, kwargs),) = whisper.built
        assert model == "medium"
        assert kwargs == {
            "device": "cpu",
            "compute_type": "int8",
            "cpu_threads": 3,
            "local_files_only": True,
        }

    def test_zero_threads_means_all_the_cores(self, whisper: type[FakeWhisper]) -> None:
        Engine(_cfg().transcribe, allow_download=False)
        assert whisper.built[0][1]["cpu_threads"] == (os.cpu_count() or 0)

    def test_allow_download_lifts_local_files_only(self, whisper: type[FakeWhisper]) -> None:
        toml = '[transcribe]\nmodel = "small"\ncompute_type = "float32"\n'
        Engine(_cfg(toml).transcribe, allow_download=True)
        model, kwargs = whisper.built[0]
        assert (model, kwargs["local_files_only"], kwargs["compute_type"]) == (
            "small",
            False,
            "float32",
        )

    def test_an_absent_model_is_a_missing_dependency_with_the_command(
        self, whisper: type[FakeWhisper]
    ) -> None:
        whisper.failure = FileNotFoundError("Cannot find an appropriate cached snapshot folder")
        with pytest.raises(MissingDependency) as info:
            Engine(_cfg().transcribe, allow_download=False)
        assert info.value.exit_code == 7
        assert "kcut transcribe --allow-download" in info.value.message_es
        assert "medium" in info.value.message_es

    def test_a_failed_download_also_says_what_to_run(self, whisper: type[FakeWhisper]) -> None:
        whisper.failure = ConnectionError("sin red")
        with pytest.raises(MissingDependency) as info:
            Engine(_cfg().transcribe, allow_download=True)
        assert "sin red" in info.value.message_es
        assert "kcut transcribe --allow-download" in info.value.message_es

    def test_a_bug_in_the_library_is_not_disguised_as_a_missing_model(
        self, whisper: type[FakeWhisper]
    ) -> None:
        whisper.failure = RuntimeError("unsupported compute type")
        with pytest.raises(RuntimeError):
            Engine(_cfg().transcribe, allow_download=False)


class TestTranscribe:
    def _engine(self, whisper: type[FakeWhisper], seconds: float = 3.0, toml: str = "") -> Engine:
        return Engine(_cfg(toml).transcribe, allow_download=False)

    def _wav(self, tmp_path: Path, seconds: float) -> Path:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(seconds))])
        return project.root / ".kcut" / "wav16" / "a1_cam.wav"

    def test_the_settings_of_the_spec_reach_the_model(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        wav = self._wav(tmp_path, 3.0)
        self._engine(whisper, toml="[transcribe]\nbeam_size = 7\n").transcribe(
            wav, "Eh. Korvex.", None, None
        )
        ((audio, kwargs),) = whisper.asked
        # the samples themselves go in (PyAV's decoder is not used), as float32 in [-1, 1)
        assert isinstance(audio, np.ndarray) and audio.dtype == np.float32
        assert len(audio) == 3 * 16000 and float(np.max(np.abs(audio))) == pytest.approx(
            0.5, abs=1e-3
        )
        assert kwargs == {
            "language": None,
            "initial_prompt": "Eh. Korvex.",
            "word_timestamps": True,
            "vad_filter": False,
            "condition_on_previous_text": False,
            "beam_size": 7,
        }

    def test_words_are_stripped_rounded_to_ms_and_indexed(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        whisper.segments = [
            segment(
                0.1,
                1.0,
                " Bueno, hola.",
                word(" Bueno,", 0.1234, 0.5006, 0.9124),
                word(" hola.", 0.6, 1.0, 0.5),
            ),
            segment(1.2, 2.0, " dos", word(" dos", 1.2, 2.0, 1.0)),
        ]
        result = self._engine(whisper).transcribe(self._wav(tmp_path, 3.0), "", None, None)
        assert [(w.i, w.text, w.s_ms, w.e_ms, w.p) for w in result.words] == [
            (0, "Bueno,", 123, 501, 0.912),
            (1, "hola.", 600, 1000, 0.5),
            (2, "dos", 1200, 2000, 1.0),
        ]
        assert [(s.s_ms, s.e_ms, s.text) for s in result.segments] == [
            (100, 1000, "Bueno, hola."),
            (1200, 2000, "dos"),
        ]

    def test_transcribe_real_length_engine_clamps_words_to_the_wav16(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        """The end of a word never goes past the audio's own length (30 s here), whatever the
        inventory says the clip lasts."""
        whisper.segments = [segment(29.0, 31.0, "x", word(" fin", 29.5, 31.2))]
        result = self._engine(whisper).transcribe(self._wav(tmp_path, 30.0), "", None, None)
        assert (result.words[0].s_ms, result.words[0].e_ms) == (29_500, 30_000)
        assert result.segments[0].e_ms == 30_000

    def test_a_word_is_never_shorter_than_one_ms(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        whisper.segments = [
            segment(0, 1, "x", word(" a", 0.5, 0.5), word(" b", 0.7, 0.6), word(" c", 2.999, 3.4))
        ]
        words = self._engine(whisper).transcribe(self._wav(tmp_path, 3.0), "", None, None).words
        # the last one is cut at the end of the 3 s audio, and still lasts its 1 ms
        assert [(w.s_ms, w.e_ms) for w in words] == [(500, 501), (700, 701), (2999, 3000)]

    def test_what_the_library_returns_is_checked_before_use(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        whisper.segments = [
            segment(
                0.0,
                2.0,
                "x",
                word("  ", 0.1, 0.2),  # no text
                word(" ok", 0.3, 0.4),
                SimpleNamespace(word=None, start=0.5, end=0.6, probability=0.9),
                SimpleNamespace(word=" nan", start=math.nan, end=0.9, probability=0.9),
                SimpleNamespace(word=" inf", start=1.0, end=math.inf, probability=0.9),
                SimpleNamespace(word=" sin", start=None, end=1.2, probability=0.9),
                SimpleNamespace(word=" p", start=1.3, end=1.4, probability=7.0),
                SimpleNamespace(word=" q", start=1.5, end=1.6, probability=None),
            ),
            SimpleNamespace(start=2.0, end=3.0, text="y"),  # a segment with no `words` at all
        ]
        words = self._engine(whisper).transcribe(self._wav(tmp_path, 3.0), "", None, None).words
        assert [(w.i, w.text, w.p) for w in words] == [(0, "ok", 0.9), (1, "p", 1.0), (2, "q", 0.0)]

    @pytest.mark.parametrize(
        ("language", "p", "expected"),
        [("es", 0.9766, ("es", 0.98)), ("en", 1.0, ("en", 1.0)), (None, None, ("und", 0.0)),
         ("español", 2.0, ("und", 1.0)), ("zz", math.nan, ("zz", 0.0))],
    )  # fmt: skip
    def test_the_detected_language(
        self, tmp_path: Path, whisper: type[FakeWhisper], language: Any, p: Any, expected: Any
    ) -> None:
        whisper.info = SimpleNamespace(language=language, language_probability=p)
        result = self._engine(whisper).transcribe(self._wav(tmp_path, 1.0), "", None, None)
        assert (result.language, result.language_p) == expected

    def test_a_language_can_be_passed_but_the_command_never_does(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        self._engine(whisper).transcribe(self._wav(tmp_path, 1.0), "", "en", None)
        assert whisper.asked[0][1]["language"] == "en"

    def test_progress_follows_the_segments(
        self, tmp_path: Path, whisper: type[FakeWhisper], capsys: pytest.CaptureFixture[str]
    ) -> None:
        whisper.segments = [segment(0, 10.2, "a", word(" a", 1, 2)), segment(10.2, 30, "b")]
        progress = Progress("transcribe a1", 0, "s")
        self._engine(whisper).transcribe(self._wav(tmp_path, 30.0), "", None, progress)
        progress.close()
        assert progress.total == 30
        assert "transcribe a1: 30/30 s (100%)" in capsys.readouterr().err

    def test_elapsed_time_is_measured(self, tmp_path: Path, whisper: type[FakeWhisper]) -> None:
        result = self._engine(whisper).transcribe(self._wav(tmp_path, 1.0), "", None, None)
        assert 0.0 <= result.elapsed_s < 5.0 and result.words == []

    def test_a_wav_that_is_not_a_wav16_is_refused(
        self, tmp_path: Path, whisper: type[FakeWhisper]
    ) -> None:
        from kcut.audio.wavio import write_wav_s16_mono
        from kcut.errors import ProjectError

        wav = tmp_path / "x.wav"
        write_wav_s16_mono(wav, tone(1.0), 44100)
        with pytest.raises(ProjectError, match="16 kHz"):
            self._engine(whisper).transcribe(wav, "", None, None)


def test_missing_model_exit7(
    tmp_path: Path, whisper: type[FakeWhisper], capsys: pytest.CaptureFixture[str]
) -> None:
    """No model here and no `--allow-download`: exit 7, and the message names the command."""
    whisper.failure = FileNotFoundError("Cannot find an appropriate cached snapshot folder")
    root = build_project(tmp_path / "proyecto ñandú", [FakeClip("a1", tone(1.0))]).root

    assert cli.main(["transcribe", "--project", str(root)]) == 7

    assert "kcut transcribe --allow-download" in capsys.readouterr().err
    assert not (root / ".kcut" / "transcripts").exists() or not list(
        (root / ".kcut" / "transcripts").glob("*.json")
    )


def test_missing_model_exit7_in_json(
    tmp_path: Path, whisper: type[FakeWhisper], capsys: pytest.CaptureFixture[str]
) -> None:
    whisper.failure = FileNotFoundError("nada")
    root = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))]).root
    assert cli.main(["transcribe", "--project", str(root), "--json"]) == 7
    error = json.loads(capsys.readouterr().out)["error"]
    assert (error["exit_code"], error["kind"]) == (7, "MissingDependency")
    assert "kcut transcribe --allow-download" in error["message"]
