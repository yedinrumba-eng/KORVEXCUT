"""`kcut transcribe`: which clips, what it prints, what it stores, how it uses the model."""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.config.load import load_config
from kcut.transcribe import cache
from kcut.transcribe.engine import build_prompt
from tests.unit.transcribe_fakes import FakeClip, build_project, install_fake_engine, tone

SAY = {
    "a1": [("hola", 100, 400, 0.9), ("mundo", 500, 900, 0.8)],
    "s1": [("hello", 200, 600, 0.99)],
}


def _run(root: Path, *args: str) -> int:
    return cli.main(["transcribe", "--project", str(root), *args])


def _json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)  # type: ignore[no-any-return]


def _project(tmp_path: Path, *clips: FakeClip) -> Path:
    return build_project(
        tmp_path / "proyecto ñandú", list(clips) or [FakeClip("a1", tone(2.0))]
    ).root


class TestOutput:
    def test_json_has_the_documented_shape(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        install_fake_engine(monkeypatch, SAY)
        assert _run(_project(tmp_path), "--json") == 0
        assert _json(capsys) == {
            "ok": True,
            "clips": [
                {
                    "id": "a1",
                    "cached": False,
                    "language": "es",
                    "language_p": 0.97,
                    "words": 2,
                    "rtf": 0.75,  # 1.5 s of work for 2 s of audio
                }
            ],
        }

    def test_human_output_is_one_line_per_clip_and_nothing_is_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        install_fake_engine(monkeypatch, SAY)
        root = _project(tmp_path)
        assert _run(root) == 0
        assert (
            capsys.readouterr().out
            == "[OK] a1: 2 palabras - idioma es (0.97) - 0.75x el tiempo real\n"
        )
        assert _run(root) == 0
        assert capsys.readouterr().out == "[INFO] a1: ya estaba transcrito (caché)\n"

    def test_the_stored_transcript_has_ids_and_the_language(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        install_fake_engine(monkeypatch, SAY)
        root = _project(tmp_path)
        assert _run(root) == 0
        key = json.loads((root / ".kcut/transcripts/index.json").read_text(encoding="utf-8"))["a1"]
        stored = json.loads((root / f".kcut/transcripts/{key}.json").read_text(encoding="utf-8"))
        assert stored["language"] == "es" and stored["duration_ms"] == 2000
        assert [w["w"] for w in stored["words"]] == ["hola", "mundo"]
        loaded = cache.load_transcript(build_project(root, [FakeClip("a1", tone(2.0))]), "a1")
        assert loaded is not None and [w.id for w in loaded.words] == ["a1:w0000", "a1:w0001"]


class TestWhichClips:
    def _four(self, tmp_path: Path) -> Path:
        return _project(
            tmp_path,
            FakeClip("a1", tone(2.0)),
            FakeClip("b1", tone(2.0), slug="muda", clip_class="video_mudo"),
            FakeClip("s1", tone(2.0), slug="voz", clip_class="audio"),
            FakeClip("s2", tone(2.0), slug="silencio", clip_class="audio", silent=True),
        )

    def test_by_default_every_clip_with_voice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        assert _run(self._four(tmp_path), "--json") == 0
        assert [c["id"] for c in _json(capsys)["clips"]] == ["a1", "s1"]
        assert fake.loaded == 1  # one model for both clips

    def test_the_named_clips_only(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        assert _run(self._four(tmp_path), "s1", "s1", "--json") == 0
        assert [c["id"] for c in _json(capsys)["clips"]] == ["s1"]
        assert [p.name for p in fake.calls] == ["s1_voz.wav"]

    @pytest.mark.parametrize("wrong", ["a9", "b1", "s2"], ids=["unknown", "no_audio", "silent"])
    def test_a_named_clip_that_cannot_be_transcribed_is_a_usage_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        wrong: str,
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        assert _run(self._four(tmp_path), "a1", wrong) == 2
        assert wrong in capsys.readouterr().err and fake.loaded == 0

    def test_a_project_without_voice_says_so_and_loads_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = _project(tmp_path, FakeClip("b1", tone(1.0), clip_class="video_mudo"))
        assert _run(root) == 0
        assert capsys.readouterr().out == "[INFO] no hay clips con voz para transcribir\n"
        assert fake.loaded == 0

    def test_without_an_inventory_it_asks_for_ingest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = tmp_path / "p"
        root.mkdir()
        (root / "kcut.toml").write_text("", encoding="utf-8")
        assert _run(root) == 3
        assert "kcut ingest" in capsys.readouterr().err

    def test_a_clip_without_wav16_is_skipped_by_default_and_an_error_when_named(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        install_fake_engine(monkeypatch, SAY)
        root = _project(
            tmp_path,
            FakeClip("a1", tone(1.0)),
            FakeClip("s1", tone(1.0), clip_class="audio", slug="voz"),
        )
        path = root / ".kcut" / "inventory.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["clips"][0]["work"]["wav16"] = None
        path.write_text(json.dumps(data), encoding="utf-8")
        assert _run(root, "--json") == 0
        captured = capsys.readouterr()
        assert [c["id"] for c in json.loads(captured.out)["clips"]] == ["s1"]
        assert "[AVISO] a1: no tiene wav16" in captured.err
        assert _run(root, "a1") == 3

    def test_a_missing_wav16_file_is_a_project_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        install_fake_engine(monkeypatch, SAY)
        root = _project(tmp_path)
        (root / ".kcut/wav16/a1_cam.wav").unlink()
        assert _run(root) == 3
        assert "falta el wav16 de a1" in capsys.readouterr().err


class TestHowTheModelIsUsed:
    def test_the_language_is_detected_never_forced_and_the_prompt_comes_from_the_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = _project(tmp_path)
        (root / "kcut.toml").write_text('[glossary]\nterms = ["Korvex"]\n', encoding="utf-8")
        assert _run(root) == 0
        assert fake.args == [(build_prompt(load_config(root / "kcut.toml")), None)]
        assert "Korvex." in fake.args[0][0]

    @pytest.mark.parametrize(("flag", "expected"), [([], False), (["--allow-download"], True)])
    def test_allow_download_reaches_the_engine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: list[str], expected: bool
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        assert _run(_project(tmp_path), *flag) == 0
        assert fake.downloads == [expected]

    def test_the_audio_goes_to_the_engine_as_the_wav16_of_the_clip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = install_fake_engine(monkeypatch, SAY)
        root = _project(tmp_path)
        assert _run(root) == 0
        assert fake.calls == [(root / ".kcut" / "wav16" / "a1_cam.wav").resolve()]


class TestRealLength:
    """The length of reference of a clip is its wav16's (spec 001.7, point 10)."""

    def _liar(self, tmp_path: Path) -> Path:
        """A clip that declares 1 s in the inventory but whose wav16 lasts 30 s."""
        return _project(tmp_path, FakeClip("a1", tone(30.0), declared_ms=1000))

    def test_transcribe_real_length_is_stored_in_the_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = install_fake_engine(monkeypatch, {"a1": [("tarde", 25_000, 26_000, 0.9)]})
        root = self._liar(tmp_path)
        assert _run(root) == 0
        key = json.loads((root / ".kcut/transcripts/index.json").read_text(encoding="utf-8"))["a1"]
        stored = json.loads((root / f".kcut/transcripts/{key}.json").read_text(encoding="utf-8"))
        assert stored["duration_ms"] == 30_000  # not the declared 1000
        assert [w["s_ms"] for w in stored["words"]] == [25_000]  # past the declared end, kept
        assert len(fake.calls) == 1

    def test_transcribe_real_length_sets_the_speed_ratio(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        install_fake_engine(monkeypatch, {"a1": [("x", 100, 200, 0.9)]})
        assert _run(self._liar(tmp_path), "--json") == 0
        assert _json(capsys)["clips"][0]["rtf"] == 0.05  # 1.5 s of work over 30 s of audio
