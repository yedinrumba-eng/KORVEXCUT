"""A project on disk, a fake Whisper and wav16 files, for the transcribe and pack tests.

No ffmpeg and no model: the inventory is written by hand, the wav16 are synthetic samples, and
`FakeEngine` stands in for `kcut.transcribe.engine.Engine`.
"""

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.audio.wavio import write_wav_s16_mono
from kcut.config.load import load_config, parse_config
from kcut.ingest.classify import ClipClass
from kcut.ingest.inventory import (
    Clip,
    ClipAudio,
    Inventory,
    SyncInfo,
    SyncMember,
    WorkFiles,
    save_inventory,
)
from kcut.paths import Layout
from kcut.project import Project
from kcut.transcribe import cache
from kcut.transcribe.engine import RawResult, RawWord, build_prompt
from kcut.transcribe.model import Segment, Transcript, Word

SR = 16000
SHA = "c0ff" * 16  # the sha256 of some wav16
Spoken = tuple[str, int, int, float]  # text, s_ms, e_ms, p


def tone(seconds: float, amplitude: float = 0.5) -> NDArray[np.float32]:
    """A loud square wave (or digital silence with amplitude 0) of exactly `seconds`."""
    n = round(seconds * SR)
    return np.where(np.arange(n) % 2 == 0, amplitude, -amplitude).astype(np.float32)


@dataclass(frozen=True)
class FakeClip:
    id: str
    samples: NDArray[np.float32]
    declared_ms: int | None = None  # what the container claimed; the wav16 may disagree
    clip_class: ClipClass = "video_voz"
    slug: str = "cam"
    silent: bool = False
    file: str | None = None  # path inside the project; default `crudo/<slug>.mp4`

    @property
    def wav_rel(self) -> str:
        return f".kcut/wav16/{self.id}_{self.slug}.wav"


def build_project(
    root: Path,
    clips: list[FakeClip],
    *,
    toml: str = "",
    master: str | None = None,
    offsets: dict[str, int] | None = None,
) -> Project:
    """A project in `root` with an inventory of `clips` and a wav16 for each.

    `master` and `offsets` (clip id -> offset_ms) describe the camera sync block.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "kcut.toml").write_text(toml, encoding="utf-8")
    layout = Layout(root)
    entries = []
    for clip in clips:
        write_wav_s16_mono(root / clip.wav_rel, clip.samples, SR)
        declared = (
            clip.declared_ms if clip.declared_ms is not None else len(clip.samples) * 1000 // SR
        )
        audio = ClipAudio("aac", 44100, 1, 0, 1, -3.0, clip.silent)
        work = WorkFiles(None, clip.wav_rel, None, None)
        entries.append(
            Clip(
                clip.id,
                clip.file or f"crudo/{clip.slug}.mp4",
                clip.slug,
                clip.clip_class,
                "sha256:" + clip.id.ljust(8, "0"),
                1000,
                declared,
                declared * 30 // 1000,
                None,
                audio,
                None,
                work,
            )
        )
    members = tuple(
        SyncMember(cid, offset, 0.9, 0.1, 9.0, 0, 0, "envelope+raw")
        for cid, offset in (offsets or {}).items()
    )
    highs: dict[str, int] = {}
    for clip in clips:
        highs[clip.id[0]] = max(highs.get(clip.id[0], 0), int(clip.id[1:]))
    inventory = Inventory(
        "2026-10-17T10:00:00", 30, tuple(entries), SyncInfo(master, members), id_high=highs
    )
    save_inventory(layout.inventory, inventory)
    return Project(root=root, config=load_config(root / "kcut.toml"), layout=layout)


class FakeEngine:
    """Stands in for `Engine`: it says what it was told to say and counts how it was used."""

    script: ClassVar[dict[str, list[Spoken]]] = {}
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
        spoken = cls.script.get(wav16.name.split("_")[0], [])
        words = [RawWord(i, t, s, e, p) for i, (t, s, e, p) in enumerate(spoken)]
        segments = [Segment(words[0].s_ms, words[-1].e_ms, " ".join(t for t, *_ in spoken))]
        return RawResult(cls.language, 0.97, words, segments if words else [], 1.5)


def install_fake_engine(
    monkeypatch: pytest.MonkeyPatch, script: dict[str, list[Spoken]]
) -> type[FakeEngine]:
    """Replace the engine of `kcut transcribe` with a fresh fake that says `script` (by clip id)."""
    from kcut.commands import transcribe

    class Fake(FakeEngine):
        pass

    Fake.script = script
    Fake.loaded = 0
    Fake.calls = []
    Fake.args = []
    Fake.downloads = []
    monkeypatch.setattr(transcribe, "Engine", Fake)
    return Fake


def params_for(toml: str = "") -> dict[str, object]:
    """The cache parameters a project with this `kcut.toml` would transcribe with."""
    cfg = parse_config(toml, default_name="x")
    return cache.build_params(cfg.transcribe, build_prompt(cfg), "faster-whisper 1.2.1")


def sample_transcript(key: str, params: dict[str, object]) -> Transcript:
    words = [
        Word("a1:w0000", 0, "Bueno,", 53_412, 53_780, 0.91),
        Word("a1:w0001", 1, "hola", 53_900, 54_300, 0.5),
    ]
    segments = [Segment(53_412, 54_300, "Bueno, hola")]
    return Transcript("a1", key, "es", 0.98, 131_233, words, segments, params, 96.1)


TRUNCATED_WAV = "el wav16 está truncado o su cabecera miente; corre kcut ingest"


def riff_bytes(declared: int, payload: bytes, *, extra: bytes = b"") -> bytes:
    """A 16 kHz mono 16-bit wav by hand: the `data` chunk says `declared` bytes and holds
    `payload` (they differ when the header lies). `extra` is a chunk placed before `data`."""
    fmt = struct.pack("<HHIIHH", 1, 1, SR, SR * 2, 2, 16)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + extra
    body += b"data" + struct.pack("<I", declared) + payload
    return b"RIFF" + struct.pack("<I", len(body)) + body
