"""Transcript cache: same key -> no new transcription; another parameter -> another key."""

import hashlib
import json
from pathlib import Path

import pytest

from kcut import cli
from kcut.config.load import parse_config
from kcut.transcribe import cache
from kcut.transcribe.engine import build_prompt
from tests.unit.transcribe_fakes import (
    SHA,
    FakeClip,
    FakeEngine,
    build_project,
    install_fake_engine,
    params_for,
    tone,
)

SAY = {"a1": [("Bueno,", 500, 900, 0.91), ("hola", 1000, 1400, 0.85)]}


class TestKey:
    def test_the_key_is_sha256_of_the_wav_hash_and_the_sorted_params(self) -> None:
        params = params_for()
        expected = hashlib.sha256((SHA + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        assert cache.cache_key(SHA, params) == expected

    def test_the_order_of_the_params_does_not_matter(self) -> None:
        params = params_for()
        shuffled = dict(reversed(list(params.items())))
        assert cache.cache_key(SHA, params) == cache.cache_key(SHA, shuffled)

    def test_the_params_are_the_documented_ones(self) -> None:
        params = params_for()
        assert list(params) == [
            "model",
            "compute_type",
            "beam_size",
            "language",
            "initial_prompt",
            "vad_filter",
            "condition_on_previous_text",
            "word_timestamps",
            "engine",
        ]
        assert params["language"] is None and params["vad_filter"] is False
        assert params["condition_on_previous_text"] is False and params["word_timestamps"] is True
        assert params["engine"] == "faster-whisper 1.2.1"

    @pytest.mark.parametrize(
        "toml",
        [
            '[transcribe]\nmodel = "small"\n',
            '[transcribe]\ncompute_type = "float32"\n',
            "[transcribe]\nbeam_size = 4\n",
            '[transcribe]\nprompt_extra = "Habla de edicion."\n',
            '[transcribe]\nfillers = ["eh"]\n',
            '[glossary]\nterms = ["Korvex"]\n',
        ],
    )
    def test_another_parameter_is_another_key(self, toml: str) -> None:
        assert cache.cache_key(SHA, params_for(toml)) != cache.cache_key(SHA, params_for())

    def test_another_audio_is_another_key(self) -> None:
        assert cache.cache_key(SHA, params_for()) != cache.cache_key("beef" * 16, params_for())

    def test_another_engine_version_is_another_key(self) -> None:
        cfg = parse_config("", default_name="x")
        other = cache.build_params(cfg.transcribe, build_prompt(cfg), "faster-whisper 9.9")
        assert cache.cache_key(SHA, other) != cache.cache_key(SHA, params_for())

    def test_threads_only_change_speed_so_they_do_not_change_the_key(self) -> None:
        assert cache.cache_key(
            SHA, params_for("[transcribe]\ncpu_threads = 2\n")
        ) == cache.cache_key(SHA, params_for())

    def test_the_engine_label_names_the_installed_library(self) -> None:
        assert cache.engine_label().startswith("faster-whisper 1.")


class TestWithTheCommand:
    """Same key -> the model is not even loaded; another parameter -> a new transcription."""

    def _run(self, root: Path, *extra: str) -> int:
        return cli.main(["transcribe", "--project", str(root), "--json", *extra])

    def _project(self, tmp_path: Path, toml: str = "") -> Path:
        clips = [FakeClip("a1", tone(2.0))]
        return build_project(tmp_path / "proyecto ñandú", clips, toml=toml).root

    def test_the_second_run_reuses_the_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = self._project(tmp_path)
        assert self._run(root) == 0
        first = json.loads(capsys.readouterr().out)["clips"][0]
        assert self._run(root) == 0
        second = json.loads(capsys.readouterr().out)["clips"][0]
        assert (first["cached"], second["cached"]) == (False, True)
        assert (fake.loaded, len(fake.calls)) == (1, 1)  # the second run never touched the model
        assert first["words"] == second["words"] == 2

    def test_force_transcribes_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = self._project(tmp_path)
        assert self._run(root) == 0
        capsys.readouterr()
        assert self._run(root, "--force") == 0
        assert json.loads(capsys.readouterr().out)["clips"][0]["cached"] is False
        assert len(fake.calls) == 2

    def test_a_changed_parameter_makes_a_new_file_and_moves_the_index(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = self._project(tmp_path)
        assert self._run(root) == 0
        old = json.loads((root / ".kcut/transcripts/index.json").read_text(encoding="utf-8"))["a1"]
        (root / "kcut.toml").write_text("[transcribe]\nbeam_size = 3\n", encoding="utf-8")
        assert self._run(root) == 0
        new = json.loads((root / ".kcut/transcripts/index.json").read_text(encoding="utf-8"))["a1"]
        assert old != new and len(fake.calls) == 2
        assert {p.stem for p in (root / ".kcut/transcripts").glob("[0-9a-f]*.json")} == {old, new}
        assert self._run(root) == 0 and len(fake.calls) == 2  # the new setting is cached too

    def test_going_back_to_an_old_setting_finds_its_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = self._project(tmp_path)
        assert self._run(root) == 0
        (root / "kcut.toml").write_text("[transcribe]\nbeam_size = 3\n", encoding="utf-8")
        assert self._run(root) == 0
        (root / "kcut.toml").write_text("", encoding="utf-8")
        assert self._run(root) == 0
        assert len(fake.calls) == 2
        index = json.loads((root / ".kcut/transcripts/index.json").read_text(encoding="utf-8"))
        assert index["a1"] == cache.cache_key(
            cache.file_sha256(root / ".kcut/wav16/a1_cam.wav"), _params_of(root)
        )

    def test_other_audio_is_transcribed_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = self._project(tmp_path)
        assert self._run(root) == 0
        build_project(root, [FakeClip("a1", tone(2.5))])  # the wav16 changed
        assert self._run(root) == 0
        assert len(fake.calls) == 2

    def test_a_broken_cache_file_is_rebuilt_with_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = self._project(tmp_path)
        assert self._run(root) == 0
        capsys.readouterr()
        for path in (root / ".kcut/transcripts").glob("[0-9a-f]*.json"):
            path.write_text("{ roto", encoding="utf-8")
        assert self._run(root) == 0
        captured = capsys.readouterr()
        assert (
            "transcript_invalid" in captured.err
            and json.loads(captured.out)["clips"][0]["cached"] is False
        )
        assert len(fake.calls) == 2

    def test_a_cached_run_needs_no_model(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_engine(monkeypatch, SAY)
        root = self._project(tmp_path)
        assert self._run(root) == 0

        class Missing(FakeEngine):
            def __init__(self, cfg: object, allow_download: bool) -> None:
                raise AssertionError("the model must not load when everything is cached")

        from kcut.commands import transcribe

        monkeypatch.setattr(transcribe, "Engine", Missing)
        assert self._run(root) == 0


def _params_of(root: Path) -> dict[str, object]:
    from kcut.config.load import load_config

    cfg = load_config(root / "kcut.toml")
    return cache.build_params(cfg.transcribe, build_prompt(cfg), cache.engine_label())
