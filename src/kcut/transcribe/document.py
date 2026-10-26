"""The JSON document of a cached transcript (spec S1.3): writing it, and reading it back.

Reading is strict: the file comes from `.kcut/`, which is never trusted (spec 0.9). Keys, types
and ranges are checked by hand, word ids are composed here (the file does not store the clip),
and anything wrong is a SchemaError, which the cache treats as "no transcript". Given the length
of the wav16 it was made from (spec 001.12, point 4), the words must also fit that audio: inside
it, in order, none longer than 30 s, and no more of them than speech could produce. What the
engine writes always passes these checks (point 6), so a file that does not is not ours.
"""

import re
from typing import Any

from kcut.schema_util import (
    SchemaError,
    describe_value,
    join_path,
    obj,
    only_keys,
    req_float,
    req_int,
    req_list,
    req_str,
)
from kcut.timebase import MAX_TIME_MS
from kcut.transcribe.model import Segment, Transcript, Word, word_id

SCHEMA = "kcut.transcript/1"
MAX_WORD_MS = 30_000  # no spoken word lasts longer; Whisper stretches one into a pause at most
MAX_WORD_CHARS = 200  # a longer "word" is a hallucination loop
MAX_ELAPSED_S = 10_000_000.0
WORDS_PER_SECOND = 10
WORDS_SLACK = 100
KEY = re.compile(r"[0-9a-f]{64}")
_LANGUAGE = re.compile(r"[a-z]{2,3}")
_TOP_KEYS = (
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
)


def max_words(audio_ms: int) -> int:
    """Most words a clip of `audio_ms` can hold: `10 x seconds + 100`."""
    return WORDS_PER_SECOND * (audio_ms // 1000) + WORDS_SLACK


MAX_WORDS = max_words(MAX_TIME_MS)  # the bound when the length of the audio is not known


def to_document(transcript: Transcript, wav_sha256: str) -> dict[str, Any]:
    """The JSON of a transcript file (words as `{i, w, s_ms, e_ms, p}`)."""
    return {
        "schema": SCHEMA,
        "key": transcript.key,
        "wav_sha256": wav_sha256,
        "params": transcript.params,
        "language": transcript.language,
        "language_p": transcript.language_p,
        "duration_ms": transcript.duration_ms,
        "elapsed_s": transcript.elapsed_s,
        "words": [
            {"i": w.i, "w": w.text, "s_ms": w.s_ms, "e_ms": w.e_ms, "p": w.p}
            for w in transcript.words
        ],
        "segments": [{"s_ms": s.s_ms, "e_ms": s.e_ms, "text": s.text} for s in transcript.segments],
    }


def from_document(
    data: object,
    clip_id: str,
    key: str,
    wav_sha256: str | None = None,
    wav_ms: int | None = None,
) -> Transcript:
    """Validate a decoded transcript file; word ids are composed here. Raises SchemaError.

    With `wav_sha256` the file must say it was made from that audio; with `wav_ms`, the length of
    the wav16 read from its header, every word must end inside it and the words may not outnumber
    `max_words(wav_ms)`.
    """
    d = obj(data, "")
    only_keys(d, set(_TOP_KEYS), "")
    schema = req_str(d, "schema", "")
    if schema != SCHEMA:
        raise SchemaError("schema", f"se esperaba {SCHEMA} (vino {describe_value(schema)})")
    if req_str(d, "key", "") != key:
        raise SchemaError("key", "no coincide con el nombre del archivo")
    sha = req_str(d, "wav_sha256", "")
    if KEY.fullmatch(sha) is None or (wav_sha256 is not None and sha != wav_sha256):
        raise SchemaError("wav_sha256", "no es el sha256 de este audio")
    language = req_str(d, "language", "", max_len=3, min_len=2)
    if _LANGUAGE.fullmatch(language) is None:
        raise SchemaError("language", "debe ser un código de 2 o 3 letras")
    words = req_list(d, "words", "")
    segments = req_list(d, "segments", "")
    limit = MAX_WORDS if wav_ms is None else max_words(wav_ms)
    if len(words) > limit or len(segments) > limit:
        raise SchemaError("words", f"admite como máximo {limit} elementos")
    end = MAX_TIME_MS + 1 if wav_ms is None else wav_ms
    return Transcript(
        clip_id=clip_id,
        key=key,
        language=language,
        language_p=req_float(d, "language_p", "", 0.0, 1.0),
        duration_ms=req_int(d, "duration_ms", "", 0, MAX_TIME_MS),
        words=_words(clip_id, words, end),
        segments=[_segment(i, item, end) for i, item in enumerate(segments)],
        params=_params(obj(d.get("params"), "params")),
        elapsed_s=req_float(d, "elapsed_s", "", 0.0, MAX_ELAPSED_S),
        wav_sha256=sha,
    )


def _words(clip_id: str, raw: list[Any], end: int) -> list[Word]:
    """The words in order: each starts at or after the one before and ends inside the audio."""
    words: list[Word] = []
    start = 0
    for index, item in enumerate(raw):
        word = _word(clip_id, index, item, start, end)
        words.append(word)
        start = word.s_ms
    return words


def _word(clip_id: str, index: int, raw: object, not_before: int, end: int) -> Word:
    here = join_path("words", index)
    d = obj(raw, here)
    only_keys(d, {"i", "w", "s_ms", "e_ms", "p"}, here)
    s_ms = req_int(d, "s_ms", here, not_before, MAX_TIME_MS)
    if req_int(d, "i", here) != index:
        raise SchemaError(join_path(here, "i"), f"debe ser {index}")
    return Word(
        id=word_id(clip_id, index),
        i=index,
        text=req_str(d, "w", here, max_len=MAX_WORD_CHARS, min_len=1),
        s_ms=s_ms,
        e_ms=req_int(d, "e_ms", here, s_ms + 1, min(s_ms + MAX_WORD_MS, end)),
        p=req_float(d, "p", here, 0.0, 1.0),
    )


def _segment(index: int, raw: object, end: int) -> Segment:
    here = join_path("segments", index)
    d = obj(raw, here)
    only_keys(d, {"s_ms", "e_ms", "text"}, here)
    s_ms = req_int(d, "s_ms", here, 0, MAX_TIME_MS)
    return Segment(
        s_ms=s_ms,
        e_ms=req_int(d, "e_ms", here, s_ms, end),
        text=req_str(d, "text", here, max_len=20_000),
    )


def _params(d: dict[str, Any]) -> dict[str, object]:
    """The parameters as stored: a few scalars, nothing nested."""
    if len(d) > 30:
        raise SchemaError("params", "tiene demasiadas claves")
    for key, value in d.items():
        scalar = value is None or isinstance(value, bool | int | float | str)
        if len(key) > 60 or not scalar or (isinstance(value, str) and len(value) > 4000):
            raise SchemaError(join_path("params", key), "debe ser un valor simple y corto")
    return dict(d)
