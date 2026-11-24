"""Fakes of the qa tests: a Whisper that says what it is told (and counts how it is used), and an
`ffmpeg` that writes a wav instead of decoding a video."""

from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest

from kcut import proc
from kcut.audio.wavio import write_wav_s16_mono
from kcut.errors import MissingDependency
from kcut.proc import RunResult
from kcut.transcribe.engine import RawResult, RawWord
from kcut.transcribe.model import Segment

Spoken = tuple[str, int, int]  # text, s_ms, e_ms


class FakeEar:
    """Stands in for `kcut.qa.ear.Engine`."""

    spoken: ClassVar[list[Spoken]] = []
    language: ClassVar[str] = "es"
    loaded: ClassVar[int] = 0
    calls: ClassVar[list[Path]] = []
    args: ClassVar[list[tuple[str, str | None]]] = []  # (prompt, language) of each call
    downloads: ClassVar[list[bool]] = []  # `allow_download` of each load

    def __init__(self, cfg: object, allow_download: bool) -> None:
        type(self).loaded += 1
        type(self).downloads.append(allow_download)

    def transcribe(
        self, wav16: Path, prompt: str, language: str | None, progress: object
    ) -> RawResult:
        cls = type(self)
        cls.calls.append(wav16)
        cls.args.append((prompt, language))
        words = [RawWord(i, t, s, e, 0.9) for i, (t, s, e) in enumerate(cls.spoken)]
        segments = [Segment(words[0].s_ms, words[-1].e_ms, "x")] if words else []
        return RawResult(language or cls.language, 0.97, words, segments, 1.5)


class NoModel:
    """An engine whose model is not on the machine."""

    def __init__(self, cfg: object, allow_download: bool) -> None:
        raise MissingDependency("no encuentro el modelo de Whisper")


def install_ear(
    monkeypatch: pytest.MonkeyPatch, spoken: list[Spoken], language: str = "es"
) -> type[FakeEar]:
    """Replace the engine of the ear with a fresh fake that says `spoken`."""
    from kcut.qa import ear

    class Fake(FakeEar):
        pass

    Fake.spoken = spoken
    Fake.language = language
    Fake.loaded = 0
    Fake.calls = []
    Fake.args = []
    Fake.downloads = []
    monkeypatch.setattr(ear, "Engine", Fake)
    return Fake


def square_wave(seconds: float, rate: int = 16000) -> Any:
    """A loud square wave of exactly `seconds`: the same samples every time."""
    n = round(seconds * rate)
    return np.where(np.arange(n) % 2 == 0, 0.5, -0.5).astype(np.float32)


def fake_extraction(monkeypatch: pytest.MonkeyPatch, seconds: float = 2.0) -> list[list[str]]:
    """`proc.run` writes a mono 16 kHz wav of `seconds` where the ffmpeg of the ear would, and
    remembers every command. Nothing is decoded."""
    seen: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> RunResult:
        seen.append(args)
        write_wav_s16_mono(Path(args[-1]), square_wave(seconds), 16000)
        return RunResult(0, b"", "")

    monkeypatch.setattr(proc, "run", run)
    return seen
