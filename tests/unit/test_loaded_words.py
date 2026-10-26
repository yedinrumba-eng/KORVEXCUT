"""`load_corrected`: the corrected words every command starts from (spec 001.15 T1).

It does what `kcut pack` did between "I have the inventory" and "I have the corrected words",
without the vote and without masking, with the same messages and the same exit codes.
"""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from kcut import cli
from kcut.audio.wavio import write_wav_s16_mono
from kcut.errors import CheckFailed, ProjectError
from kcut.ingest.inventory import Clip, ClipAudio, Notice
from kcut.project import Project, load_inventory, open_project
from kcut.transcribe.loaded import LoadedWords, has_voice, load_corrected, wav16_or_none
from tests.unit.test_pack_command import LAYOUT, SPEECH, _ready
from tests.unit.transcribe_fakes import SR, FakeClip, Spoken, tone

PHONE: list[Spoken] = [
    ("llama", 1000, 1300, 0.9),
    ("972", 1300, 1600, 0.9),
    ("808", 1600, 1900, 0.9),
    ("3211", 1900, 2400, 0.9),
]

MASTER = ["mi", "numero", "972", "y", "3211", "gracias"]
HEARD = ["mi", "numero", "972", "808", "gracias", "ya"]  # a2 heard six digits: no PII on its own


def _fix(root: Path, word: str, expect: str, text: str) -> None:
    item = {"word": word, "expect": expect, "text": text, "why": "x"}
    document = {"schema": "kcut.correcciones/1", "items": [item]}
    (root / "edit").mkdir(exist_ok=True)
    (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")


def _load(root: Path) -> tuple[LoadedWords, list[Notice], Project]:
    project = open_project(str(root))
    notices: list[Notice] = []
    loaded = load_corrected(project, load_inventory(project), notices, None)
    return loaded, notices, project


class TestLoaded:
    def test_loaded_gives_the_transcripts_and_the_corrected_words_by_clip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _fix(root, "a1:w0001", "da", "dá")
        loaded, notices, _ = _load(root)
        assert set(loaded.transcripts) == {"a1"} and set(loaded.words) == {"a1"}
        assert [w.text for w in loaded.transcripts["a1"].words][:3] == ["¿Te", "da", "eh"]
        corrected = loaded.words["a1"]
        assert [w.text for w in corrected][:3] == ["¿Te", "dá", "eh"]
        assert [w.corrected for w in corrected][:3] == [False, True, False]
        assert notices == []

    def test_loaded_without_corrections_the_words_are_the_transcripts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        loaded, _, _ = _load(_ready(tmp_path, monkeypatch))
        assert loaded.words["a1"] == loaded.transcripts["a1"].words
        assert len(loaded.words["a1"]) == len(SPEECH)

    def test_loaded_does_not_mask_that_is_for_the_one_who_shows(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": PHONE})
        loaded, _, _ = _load(root)
        assert [w.text for w in loaded.words["a1"]] == ["llama", "972", "808", "3211"]

    def test_loaded_a_clip_without_a_transcript_is_simply_not_there(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clips = [FakeClip("a1", LAYOUT), FakeClip("a2", LAYOUT, slug="cam2")]
        root = _ready(tmp_path, monkeypatch, clips, only=["a1"], master=None)
        loaded, _, _ = _load(root)
        assert set(loaded.transcripts) == {"a1"} and set(loaded.words) == {"a1"}

    def test_loaded_a_correction_that_names_another_word_is_check_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _fix(root, "a1:w0001", "otra cosa", "x")
        with pytest.raises(CheckFailed, match="la corrección apunta a otra palabra"):
            _load(root)

    def test_loaded_a_correction_on_a_masked_word_is_check_failed_with_the_fixed_text(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": PHONE})
        _fix(root, "a1:w0002", "808", "ochocientos")
        with pytest.raises(CheckFailed) as info:
            _load(root)
        assert info.value.message_es == (
            "la palabra a1:w0002 está enmascarada por privacidad; no se corrige desde aquí"
        )

    def test_loaded_with_masking_off_that_same_correction_goes_through(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(
            tmp_path, monkeypatch, script={"a1": PHONE}, toml="[privacy]\nmask_pii = false\n"
        )
        _fix(root, "a1:w0002", "808", "ochocientos")
        loaded, _, _ = _load(root)
        assert loaded.words["a1"][2].text == "ochocientos"

    def test_loaded_a_correction_that_would_open_a_masked_number_is_check_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        said = [
            "ocho",
            "cero",
            "nueve",
            "eh",
            "cinco",
            "cinco",
            "cinco",
            "uno",
            "dos",
            "tres",
            "cuatro",
        ]
        spoken: list[Spoken] = [
            (w, 1000 + k * 300, 1300 + k * 300, 0.9) for k, w in enumerate(said)
        ]
        root = _ready(tmp_path, monkeypatch, [FakeClip("a1", tone(8.0))], {"a1": spoken})
        _fix(root, "a1:w0003", "eh", "a b c d e f g")  # 001.20: one word is an aside
        with pytest.raises(CheckFailed) as info:
            _load(root)
        assert info.value.message_es == (
            "la corrección de a1:w0003 dejaría ver un dato privado; no se aplica"
        )

    def test_loaded_a_wav16_that_changed_after_transcribe_is_check_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        other = np.concatenate([LAYOUT, tone(0.5)])
        write_wav_s16_mono(root / ".kcut" / "wav16" / "a1_cam.wav", other, SR)
        with pytest.raises(CheckFailed, match="es de otro audio; corre kcut transcribe"):
            _load(root)


class TestHelpers:
    def test_loaded_has_voice_is_a_voice_class_that_is_not_silent(self) -> None:
        audio = ClipAudio("aac", 44100, 1, 0, 1, -3.0, False)
        voice = Clip(
            "a1", "crudo/a.mp4", "a", "video_voz", "sha256:aaaaaaaa", 1, 1000, 30, None, audio
        )
        only_audio = replace(voice, id="s1", clip_class="audio")
        silent = replace(voice, audio=replace(audio, silent=True))
        no_sound = replace(voice, audio=None)
        picture = Clip("i1", "crudo/a.png", "a", "imagen", "sha256:bbbbbbbb", 1)
        assert has_voice(voice) and has_voice(only_audio)
        assert not (has_voice(silent) or has_voice(no_sound) or has_voice(picture))

    def test_loaded_wav16_or_none_is_the_file_or_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        project = open_project(str(root))
        clip = load_inventory(project).clips[0]
        found = wav16_or_none(project, clip)
        assert found is not None and found.name == "a1_cam.wav"
        found.unlink()
        assert wav16_or_none(project, clip) is None
        assert wav16_or_none(project, replace(clip, work=None)) is None


class TestLoadedCovered:
    def test_loaded_covered_has_the_ids_another_camera_masks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        said = {
            "a1": [(t, 1000 + k * 330, 1300 + k * 330, 0.9) for k, t in enumerate(MASTER)],
            "a2": [(t, 1000 + k * 330, 1300 + k * 330, 0.9) for k, t in enumerate(HEARD)],
        }
        clips = [FakeClip("a1", LAYOUT), FakeClip("a2", LAYOUT * np.float32(0.9), slug="cam2")]
        root = _ready(tmp_path, monkeypatch, clips, said, offsets={"a2": 0})
        loaded, _, _ = _load(root)
        assert loaded.covered == {"a2": {"a2:w0002", "a2:w0003", "a2:w0004"}}

    def test_loaded_covered_is_empty_with_one_camera_or_with_masking_off(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert _load(_ready(tmp_path / "uno", monkeypatch))[0].covered == {}
        said = {"a1": [(t, 1000 + k * 330, 1300 + k * 330, 0.9) for k, t in enumerate(MASTER)]}
        off = "[privacy]\nmask_pii = false\n"
        root = _ready(tmp_path / "off", monkeypatch, script=said, toml=off)
        assert _load(root)[0].covered == {}


class TestOnlyNeededClips:
    """001.20 point 11: `view` asks for one clip and its sync group; no other wav16 is read."""

    def _three(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        say = lambda texts: [(t, 1000 + k * 330, 1300 + k * 330, 0.9) for k, t in enumerate(texts)]  # noqa: E731
        clips = [
            FakeClip("a1", LAYOUT),
            FakeClip("a2", LAYOUT * np.float32(0.9), slug="cam2"),
            FakeClip("a3", LAYOUT * np.float32(0.8), slug="cam3"),
        ]
        script = {"a1": say(MASTER), "a2": say(HEARD), "a3": say(["hola", "que", "tal"])}
        return _ready(tmp_path, monkeypatch, clips, script, offsets={"a2": 0})

    def _hashed(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        from kcut.transcribe import cache

        seen: list[str] = []
        real = cache.file_sha256

        def spy(path: Path) -> str:
            seen.append(path.name)
            return real(path)

        monkeypatch.setattr(cache, "file_sha256", spy)
        return seen

    def _load_for(self, root: Path, ids: list[str] | None) -> LoadedWords:
        project = open_project(str(root))
        return load_corrected(project, load_inventory(project), [], None, ids)

    def test_only_needed_clips_a_clip_alone_hashes_only_its_own_wav16(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._three(tmp_path, monkeypatch)
        seen = self._hashed(monkeypatch)
        loaded = self._load_for(root, ["a3"])
        assert seen == ["a3_cam3.wav"] and set(loaded.transcripts) == {"a3"}

    def test_only_needed_clips_a_member_brings_its_master_and_not_the_rest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._three(tmp_path, monkeypatch)
        seen = self._hashed(monkeypatch)
        loaded = self._load_for(root, ["a2"])
        assert sorted(seen) == ["a1_cam.wav", "a2_cam2.wav"]
        assert set(loaded.transcripts) == set(loaded.words) == {"a1", "a2"}
        assert loaded.covered == {"a2": {"a2:w0002", "a2:w0003", "a2:w0004"}}  # same as with all

    def test_only_needed_clips_the_master_brings_its_members(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._three(tmp_path, monkeypatch)
        seen = self._hashed(monkeypatch)
        assert set(self._load_for(root, ["a1"]).transcripts) == {"a1", "a2"}
        assert sorted(seen) == ["a1_cam.wav", "a2_cam2.wav"]

    def test_only_needed_clips_without_ids_it_is_every_clip_as_pack_does(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._three(tmp_path, monkeypatch)
        seen = self._hashed(monkeypatch)
        assert set(self._load_for(root, None).transcripts) == {"a1", "a2", "a3"}
        assert len(seen) == 3

    def test_only_needed_clips_a_broken_wav16_of_a_clip_nobody_asked_for_does_not_matter(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._three(tmp_path, monkeypatch)
        (root / ".kcut" / "wav16" / "a3_cam3.wav").write_bytes(b"RIFF....WAVE broken")
        assert set(self._load_for(root, ["a1"]).transcripts) == {"a1", "a2"}
        with pytest.raises(ProjectError):
            self._load_for(root, None)

    def test_only_needed_clips_view_does_not_hash_the_rest_of_the_project(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._three(tmp_path, monkeypatch)
        seen = self._hashed(monkeypatch)
        assert cli.main(["view", "a3", "0", "3s", "--project", str(root), "--json"]) == 0
        assert seen == ["a3_cam3.wav"]

    def test_only_needed_clips_a_correction_of_a_clip_left_out_is_not_judged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._three(tmp_path, monkeypatch)
        _fix(root, "a3:w0001", "otra cosa", "x")  # it would be CheckFailed if a3 were loaded
        assert set(self._load_for(root, ["a1"]).transcripts) == {"a1", "a2"}
        with pytest.raises(CheckFailed):
            self._load_for(root, ["a3"])
