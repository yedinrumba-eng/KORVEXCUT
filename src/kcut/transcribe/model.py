"""Transcript dataclasses (spec S1.3). Times are integer milliseconds of the clip's own clock."""

from dataclasses import dataclass


def word_id(clip_id: str, i: int) -> str:
    """`a1:w0031`. The id is composed at load time: the cache does not store the clip."""
    return f"{clip_id}:w{i:04d}"


@dataclass(frozen=True)
class Word:
    id: str
    i: int
    text: str
    s_ms: int
    e_ms: int
    p: float
    corrected: bool = False


@dataclass(frozen=True)
class Segment:
    s_ms: int
    e_ms: int
    text: str


@dataclass
class Transcript:
    clip_id: str
    key: str
    language: str
    language_p: float
    duration_ms: int
    words: list[Word]
    segments: list[Segment]
    params: dict[str, object]
    elapsed_s: float
    wav_sha256: str = ""  # sha256 of the wav16 it was made from (filled when read back)
