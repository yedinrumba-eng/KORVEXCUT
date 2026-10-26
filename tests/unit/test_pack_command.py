"""`kcut pack`: from cached transcripts and wav16 energy to the md and the tsv."""

import json
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut import cli
from kcut.audio.wavio import write_wav_s16_mono
from tests.unit.transcribe_fakes import (
    FakeClip,
    Spoken,
    build_project,
    install_fake_engine,
    tone,
)

HEADER_LINES = 6  # title, data notice, fps, marks, hint, blank line
TSV_HEADER = ["id", "clip", "s_f", "e_f", "s", "p", "flags", "text", "alt", "corrected"]

# 1 s quiet, 2 s loud, 1.5 s quiet, 1.5 s loud, 2 s quiet
LAYOUT: NDArray[np.float32] = np.concatenate(
    [tone(1.0, 0), tone(2.0), tone(1.5, 0), tone(1.5), tone(2.0, 0)]
)
SPEECH: list[Spoken] = [
    ("¿Te", 1000, 1300, 0.9),
    ("da", 1300, 1500, 0.9),
    ("eh", 1500, 1800, 0.9),
    ("curiosidad", 1800, 3400, 0.9),  # Whisper stretches it 400 ms into the silence
    ("bueno", 4500, 5000, 0.9),
    ("bueno", 5000, 5500, 0.9),
    ("hola", 5500, 6000, 0.2),
]


def _pack(root: Path, *flags: str) -> int:
    return cli.main(["pack", "--project", str(root), *flags])


def _md(root: Path) -> list[str]:
    return (root / "edit" / "transcripcion.md").read_text(encoding="utf-8").splitlines()


def _tsv(root: Path) -> list[list[str]]:
    text = (root / "edit" / "palabras.tsv").read_text(encoding="utf-8")
    return [line.split("\t") for line in text.splitlines()]


def _ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    clips: list[FakeClip] | None = None,
    script: dict[str, list[Spoken]] | None = None,
    *,
    toml: str = "",
    only: list[str] | None = None,
    master: str | None = "a1",
    offsets: dict[str, int] | None = None,
) -> Path:
    """A project whose clips were transcribed by the fake engine (all of them, or `only`)."""
    chosen = clips or [FakeClip("a1", LAYOUT)]
    root = build_project(
        tmp_path / "proyecto ñandú", chosen, toml=toml, master=master, offsets=offsets
    ).root
    install_fake_engine(monkeypatch, script or {"a1": SPEECH})
    assert cli.main(["transcribe", "--project", str(root), *(only or [])]) == 0
    return root


class TestStaleTranscript:
    """A transcript belongs to the audio it was made from (spec 001.11, point 1): a wav16 that
    was regenerated since gives times of another audio, so `pack` refuses to use it."""

    def _wav(self, root: Path, clip_id: str = "a1", slug: str = "cam") -> Path:
        return root / ".kcut" / "wav16" / f"{clip_id}_{slug}.wav"

    def test_stale_transcript_after_the_wav16_changed_stops_pack(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        write_wav_s16_mono(self._wav(root), np.concatenate([LAYOUT, tone(0.5, 0)]), 16000)
        capsys.readouterr()
        assert _pack(root) == 1
        assert (
            "la transcripción de a1 es de otro audio; corre kcut transcribe"
            in capsys.readouterr().err
        )
        assert not (root / "edit" / "transcripcion.md").exists()
        assert not (root / "edit" / "palabras.tsv").exists()

    def test_stale_transcript_is_a_check_failed_in_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        write_wav_s16_mono(self._wav(root), tone(8.0), 16000)
        capsys.readouterr()
        assert _pack(root, "--json") == 1
        error = json.loads(capsys.readouterr().out)["error"]
        assert (error["exit_code"], error["kind"]) == (1, "CheckFailed")
        assert "a1" in error["message"] and "corre kcut transcribe" in error["message"]

    def test_stale_transcript_not_raised_when_the_same_audio_is_rewritten(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        before = self._wav(root).read_bytes()
        write_wav_s16_mono(self._wav(root), LAYOUT, 16000)  # regenerated, byte for byte the same
        assert self._wav(root).read_bytes() == before
        assert _pack(root) == 0

    def test_stale_transcript_is_cured_by_transcribing_again(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        write_wav_s16_mono(self._wav(root), np.concatenate([LAYOUT, tone(0.5, 0)]), 16000)
        assert _pack(root) == 1
        fake = install_fake_engine(monkeypatch, {"a1": SPEECH})
        assert cli.main(["transcribe", "--project", str(root)]) == 0
        assert len(fake.calls) == 1  # another audio: another key, so it really transcribed
        assert _pack(root) == 0
        assert _md(root)[HEADER_LINES].startswith("## a1 - `crudo/cam.mp4` - 8.50 s")

    def test_stale_transcript_of_a_member_names_the_member(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        member = np.concatenate([tone(0.5, 0), LAYOUT])
        clips = [FakeClip("a1", LAYOUT), FakeClip("a2", member, slug="cam2")]
        script = {"a1": SPEECH, "a2": [("te", 0, 300, 0.9)]}
        root = _ready(tmp_path, monkeypatch, clips, script, offsets={"a2": 1000})
        write_wav_s16_mono(self._wav(root, "a2", "cam2"), tone(3.0), 16000)
        capsys.readouterr()
        assert _pack(root) == 1
        err = capsys.readouterr().err
        assert "la transcripción de a2 es de otro audio" in err and "de a1" not in err

    def test_stale_and_shorter_the_hash_wins_over_the_length(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A wav16 that changed AND is now shorter than the transcript: the answer is the
        `CheckFailed` of row 16, not a silent "sin transcribir" from the length check."""
        root = _ready(tmp_path, monkeypatch)  # the words reach 6 s; the wav16 lasts 8 s
        write_wav_s16_mono(self._wav(root), tone(3.0), 16000)
        capsys.readouterr()
        assert _pack(root, "--json") == 1
        error = json.loads(capsys.readouterr().out)["error"]
        assert (error["kind"], error["message"]) == (
            "CheckFailed",
            "la transcripción de a1 es de otro audio; corre kcut transcribe",
        )
        assert not (root / "edit" / "transcripcion.md").exists()

    def test_stale_and_shorter_the_same_audio_still_packs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        assert _pack(root) == 0


def test_orphan_list_capped_pack_json_stays_small(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """50 000 corrections for words that do not exist: the error names 20 and counts the rest."""
    root = _ready(tmp_path, monkeypatch)
    items = [{"word": f"a1:w{10_000 + i:05d}", "expect": "x", "text": "y"} for i in range(50_000)]
    document = {"schema": "kcut.correcciones/1", "items": items}
    (root / "edit").mkdir(exist_ok=True)
    (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")
    capsys.readouterr()
    assert _pack(root, "--json") == 1
    out = capsys.readouterr().out
    assert len(out.encode("utf-8")) < 2048 and "(y 49980 más)" in out and "a1:w10019" in out
    assert not (root / "edit" / "transcripcion.md").exists()


class TestPiiDigits:
    """001.13: what Claude reads (md, tsv, json) has the digits masked; the cache stays raw."""

    PHONE: ClassVar[list[Spoken]] = [
        ("mi", 1000, 1200, 0.9),
        ("numero", 1200, 1600, 0.9),
        ("es", 1600, 1800, 0.9),
        ("972", 1800, 2100, 0.9),
        ("808", 2100, 2400, 0.9),
        ("3211", 2400, 2800, 0.9),
        ("tarjeta", 4500, 4700, 0.9),
        ("4111", 4700, 4850, 0.9),
        ("1111", 4850, 5000, 0.9),
        ("1111", 5000, 5150, 0.9),
        ("1111", 5150, 5300, 0.9),
        ("y", 5300, 5400, 0.9),
        ("001-1234567-8", 5400, 6000, 0.9),
    ]
    RAW: ClassVar[list[str]] = ["972", "808", "3211", "4111", "1111", "1234567"]

    def test_pii_digits_masked_in_md_tsv_and_json_but_not_in_the_cache(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": self.PHONE})
        capsys.readouterr()
        assert _pack(root, "--json") == 0
        stdout = capsys.readouterr().out
        md = (root / "edit" / "transcripcion.md").read_text(encoding="utf-8")
        tsv = (root / "edit" / "palabras.tsv").read_text(encoding="utf-8")
        # 001.20: the card is six words from the phone, so they are one number: only the
        # last two digits of the whole stay readable (the last digits of the ID number)
        assert "mi numero es *** *** ****" in md
        assert "tarjeta **** **** **** **** y ***-******7-8" in md  # "y" bridges: one number
        for raw in self.RAW:
            assert not any(raw in text for text in (md, tsv, stdout)), raw
        rows = {r[0]: r for r in _tsv(root)[1:]}
        assert [rows[f"a1:w{i:04d}"][7] for i in (3, 4, 5)] == ["***", "***", "****"]  # 001.20
        assert rows["a1:w0003"][6] == "P" and rows["a1:w0000"][6] == ""
        cache = "".join(
            p.read_text(encoding="utf-8") for p in (root / ".kcut/transcripts").glob("*.json")
        )
        assert '"3211"' in cache and '"001-1234567-8"' in cache  # the raw words stay local

    def test_pii_digits_the_corrected_and_alt_columns_are_masked_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        member = np.concatenate([LAYOUT[:8000], LAYOUT])
        clips = [FakeClip("a1", LAYOUT), FakeClip("a2", member, slug="cam2")]
        script = {
            "a1": [("sabes", 1500, 1800, 0.9), ("heat", 1800, 2100, 0.9)],
            "a2": [("9728083211", 500, 800, 0.9), ("heat", 800, 1100, 0.9)],
        }
        root = _ready(tmp_path, monkeypatch, clips, script, offsets={"a2": 1000})
        fix = {"word": "a1:w0001", "expect": "heat", "text": "(972) 808-3211", "why": "x"}
        (root / "edit").mkdir(exist_ok=True)
        document = {"schema": "kcut.correcciones/1", "items": [fix]}
        (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")
        assert _pack(root) == 0
        md = "\n".join(_md(root)[HEADER_LINES:])
        row = {r[0]: r for r in _tsv(root)[1:]}
        # 001.17: the member heard a number where the master heard "sabes", so the master's word
        # is under that mask too (text, alt, corrected), and its alternative is hidden whole
        assert row["a1:w0000"][7:] == ["*", "*", ""]
        assert row["a1:w0001"][7:] == ["heat", "", "(***) ***-**11"]
        assert "* (***) ***-**11" in md
        assert "972" not in md and "3211" not in md
