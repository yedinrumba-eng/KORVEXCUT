"""The faster-whisper engine: loads the model once and returns words in integer milliseconds.

Language is detected per clip and never forced; there is no VAD and no conditioning on previous
text (the settings that, in the pilot, stopped Whisper from inventing words over silence).

What the engine returns always passes `document.from_document` for the same audio (spec 001.12,
point 6): a word's text is cut to 200 characters, a word lasts 30 s at most, starts do not go
back, nothing starts after the end of the audio and there are no more words than `max_words`.
Whatever the library hands back is checked here, because it is data from outside.
"""

import math
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from kcut.audio.wavio import read_wav_s16_mono
from kcut.config.model import ProjectConfig, TranscribeSection
from kcut.console import Progress
from kcut.errors import MissingDependency
from kcut.ingest.inventory import Notice
from kcut.transcribe.cache import WAV16_RATE, wav16_length_ms
from kcut.transcribe.document import MAX_WORD_CHARS, MAX_WORD_MS, max_words
from kcut.transcribe.model import Segment

DOWNLOAD_HINT = "kcut transcribe --allow-download"
PROMPT_MAX = (
    1000  # characters of fillers + glossary + extra text; Whisper only uses the last ~223 tokens
)
SEGMENT_CHARS = 20_000


@dataclass(frozen=True)
class RawWord:
    i: int
    text: str
    s_ms: int
    e_ms: int
    p: float


@dataclass(frozen=True)
class RawResult:
    language: str
    language_p: float
    words: list[RawWord]
    segments: list[Segment]
    elapsed_s: float


def build_prompt(cfg: ProjectConfig, notices: list[Notice] | None = None) -> str:
    """Whisper's `initial_prompt`: the fillers (first one capitalized), the glossary, the extra.

    `Eh, este, o sea.` + `Higgsfield, Claude.` + `<prompt_extra>`. Showing Whisper the fillers
    makes it write them down instead of cleaning them up, which is what the editor needs.

    The whole prompt is at most 1000 characters. The extra text always stays; fillers and glossary
    terms are kept in order for as long as they fit, the rest are left out, and a
    `prompt_truncated` notice says how many.
    """
    fillers, terms = list(cfg.transcribe.fillers), list(cfg.glossary)
    extra = cfg.transcribe.prompt_extra
    total = len(fillers) + len(terms)
    for keep in range(total, -1, -1):
        kept = min(keep, len(fillers))
        prompt = _assemble(fillers[:kept], terms[: keep - kept], extra)
        if len(prompt) <= PROMPT_MAX:
            break
    if keep < total and notices is not None:
        detail = (
            f"{total - keep} de {total} términos (muletillas y glosario) no caben en el prompt de "
            f"Whisper (máximo {PROMPT_MAX} caracteres) y quedaron fuera"
        )
        notices.append(Notice("prompt_truncated", detail))
    return prompt


def _assemble(fillers: list[str], terms: list[str], extra: str) -> str:
    sentences: list[str] = []
    if fillers:
        joined = ", ".join(fillers)
        sentences.append(joined[:1].upper() + joined[1:] + ".")
    if terms:
        sentences.append(", ".join(terms) + ".")
    if extra:
        sentences.append(extra)
    return " ".join(sentences)


class Engine:
    """A loaded Whisper model. Create it once and reuse it for every clip."""

    def __init__(self, cfg: TranscribeSection, allow_download: bool) -> None:
        # imported here: ctranslate2 is heavy and `kcut --version` must stay instant
        from faster_whisper import WhisperModel

        self._beam_size = cfg.beam_size
        try:
            self._model = WhisperModel(
                cfg.model,
                device="cpu",
                compute_type=cfg.compute_type,
                cpu_threads=cfg.cpu_threads or os.cpu_count() or 0,
                local_files_only=not allow_download,
            )
        except OSError as exc:
            raise MissingDependency(_missing_text(cfg.model, allow_download, exc)) from None

    def transcribe(
        self, wav16: Path, prompt: str, language: str | None, progress: Progress | None
    ) -> RawResult:
        """Transcribe a wav16 word by word. `language=None` detects it for this clip.

        The samples go to Whisper as an array, so faster-whisper's own decoder (PyAV) is never
        involved: its `decode_audio` calls `av.open(metadata_errors=...)`, which PyAV 19 no
        longer accepts. A wav16 is already what Whisper wants (mono, 16 kHz), so nothing is lost.
        """
        samples = _read_wav16(wav16)
        total_ms = len(samples) * 1000 // WAV16_RATE  # the audio's own length, not the declared
        if progress is not None:
            progress.total = max(1, math.ceil(total_ms / 1000))
        started = time.monotonic()
        segments_iter, info = self._model.transcribe(
            samples,
            language=language,
            initial_prompt=prompt,
            word_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
            beam_size=self._beam_size,
        )
        words: list[RawWord] = []
        segments: list[Segment] = []
        for segment in segments_iter:
            start_ms = _ms(getattr(segment, "start", None), total_ms)
            end_ms = max(_ms(getattr(segment, "end", None), total_ms), start_ms)
            if len(segments) < max_words(total_ms):
                text = str(getattr(segment, "text", "")).strip()[:SEGMENT_CHARS]
                segments.append(Segment(start_ms, end_ms, text))
            _add_words(words, getattr(segment, "words", None), total_ms)
            if progress is not None:
                progress.update(min(progress.total, math.ceil(end_ms / 1000)))
        return RawResult(
            language=_language(getattr(info, "language", None)),
            language_p=round(_unit(getattr(info, "language_probability", 0.0)), 2),
            words=words,
            segments=segments,
            elapsed_s=round(time.monotonic() - started, 1),
        )


def _read_wav16(path: Path) -> NDArray[np.float32]:
    """The samples of a wav16 as float32 in [-1, 1). The format is checked first."""
    wav16_length_ms(path)  # mono, 16-bit, 16 kHz, or ProjectError
    samples, _rate = read_wav_s16_mono(path)
    return samples


def _add_words(words: list[RawWord], raw: Iterable[Any] | None, total_ms: int) -> None:
    """Append the words of one segment, validated, to `words`.

    A word with no text or a time that is not a number is dropped, and so is one that starts after
    the audio ends. Text is cut to 200 characters, a start never goes back, `e_ms` is cut at the
    audio's length and at 30 s after the start, and it is at least `s_ms + 1`.
    """
    for item in raw or []:
        if len(words) >= max_words(total_ms):
            return
        text = getattr(item, "word", None)
        span = _span(getattr(item, "start", None), getattr(item, "end", None))
        clean = text.strip()[:MAX_WORD_CHARS].strip() if isinstance(text, str) else ""
        if not clean or span is None:
            continue
        s_ms = max(0, round(span[0] * 1000), words[-1].s_ms if words else 0)
        if s_ms >= total_ms:
            continue
        e_ms = min(round(span[1] * 1000), total_ms, s_ms + MAX_WORD_MS)
        probability = round(_unit(getattr(item, "probability", 0.0)), 3)
        words.append(RawWord(len(words), clean, s_ms, max(e_ms, s_ms + 1), probability))


def _span(start: object, end: object) -> tuple[float, float] | None:
    """`(start, end)` in seconds if both are finite numbers, else None."""
    if not isinstance(start, int | float) or not isinstance(end, int | float):
        return None
    if not (math.isfinite(start) and math.isfinite(end)):
        return None
    return float(start), float(end)


def _ms(value: object, total_ms: int) -> int:
    """A segment time in ms, clamped into the audio; garbage becomes 0."""
    if not isinstance(value, int | float) or not math.isfinite(value):
        return 0
    return min(max(0, round(value * 1000)), total_ms)


def _unit(value: object) -> float:
    """A probability clamped to 0..1; anything that is not a number is 0."""
    if not isinstance(value, int | float) or not math.isfinite(value):
        return 0.0
    return min(max(float(value), 0.0), 1.0)


def _language(value: object) -> str:
    """The detected language code, or `und` (undetermined) if the library gave none."""
    if isinstance(value, str) and 2 <= len(value) <= 3 and value.isascii() and value.isalpha():
        return value.lower()
    return "und"


def _missing_text(model: str, allow_download: bool, exc: OSError) -> str:
    if allow_download:
        return (
            f"no pude bajar ni cargar el modelo de Whisper '{model}' ({exc}); revisa tu conexión "
            f"y repite: {DOWNLOAD_HINT}"
        )
    return (
        f"no encuentro el modelo de Whisper '{model}' en esta máquina. Para bajarlo una vez "
        f"(necesita internet) corre: {DOWNLOAD_HINT}"
    )
