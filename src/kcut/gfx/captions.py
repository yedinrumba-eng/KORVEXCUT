"""Subtitle chunks: the kept words grouped in short lines (spec S1.6a; from `piloto/cues.py`). Pure.

A chunk is up to `captions.max_words` words and `captions.max_chars` characters that are on screen
together, from the first word to a moment after the last one. The chunks are made once, from the
raw text of the words and the times of the MP4. `shown_chunks` then gives the same chunks with the
text Claude may read (001.13 and 001.15 T2): same frames, other letters.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from kcut.config.model import CaptionsSection
from kcut.edl.words import KeptWord
from kcut.errors import InternalError
from kcut.timebase import ms_to_f_ceil

BORDER = " \t\r\n,.;:!?¿¡\"'«»()"  # what is cut off the edges of a word to show it
PAUSE_MS = 350  # a longer pause than this between two words starts a new chunk
PHRASE_MS = 400  # a chunk that ended a phrase and is this long (or longer) is closed
PHRASE_ENDS = (",", ".", "?", "!", ";", ":")
TAIL_MS = 150  # a chunk stays on screen this long after its last word
HIDE_LEAD_MS = 60  # a big graphic hides the subtitles this long before it starts


@dataclass(frozen=True)
class ChunkWord:
    """A word of a chunk: the id of its `KeptWord`, the text shown and its output frame."""

    id: str
    text: str
    s_f: int


@dataclass(frozen=True)
class Chunk:
    """Subtitles on screen from `s_f` to `e_f` (exclusive), in output frames."""

    s_f: int
    e_f: int
    words: list[ChunkWord]


def display_text(text: str, cfg: CaptionsSection) -> str:
    """The text of a word as it is shown: without the punctuation of its edges, in capitals if
    `captions.uppercase`. The empty string means the word is not shown."""
    cut = text.strip(BORDER)
    return cut.upper() if cfg.uppercase else cut


def hide_window(start_f: int, end_f: int, fps: int) -> tuple[int, int]:
    """The frames in which the subtitles are hidden for a graphic that is on `[start_f, end_f)`:
    from `HIDE_LEAD_MS` before it begins."""
    return start_f - ms_to_f_ceil(HIDE_LEAD_MS, fps), end_f


def build_chunks(
    kept: Sequence[KeptWord], cfg: CaptionsSection, hide: Sequence[tuple[int, int]], fps: int
) -> list[Chunk]:
    """The chunks of the kept words (in order), with the raw text of the transcript.

    `hide` are the windows `[start, end)` in which no subtitle is shown (`captions.hide` and the
    cues that hide them). A word that starts inside one is left out and closes the chunk it was
    in. A chunk is closed before a word that comes from another voice clip of the EDL, that would
    be its `max_words`-th plus one, that would pass `max_chars`, that starts more than 350 ms after
    the last word ends, or after a word that ends in `, . ? ! ; :` once the chunk is 400 ms long.
    A chunk ends 150 ms after its last word, but not after the start of the next chunk or of a
    window that begins inside it. A chunk left with no frames is dropped."""
    groups: list[list[tuple[KeptWord, str]]] = []
    current: list[tuple[KeptWord, str]] = []
    for word in kept:
        if any(a <= word.out_s_f < b for a, b in hide):
            if current:
                groups.append(current)
                current = []
            continue
        shown = display_text(word.text, cfg)
        if not shown:
            continue
        if current and _closes(current, word, shown, cfg, fps):
            groups.append(current)
            current = []
        current.append((word, shown))
    if current:
        groups.append(current)
    return _timed(groups, hide, fps)


def _closes(
    current: list[tuple[KeptWord, str]], word: KeptWord, shown: str, cfg: CaptionsSection, fps: int
) -> bool:
    """Must the chunk being made be closed before `word`?"""
    first, last = current[0][0], current[-1][0]
    chars = sum(len(text) + 1 for _, text in current) + len(shown)
    return (
        last.clip_index != word.clip_index
        or len(current) >= cfg.max_words
        or chars > cfg.max_chars
        or (word.out_s_f - last.out_e_f) * 1000 > PAUSE_MS * fps
        or (
            last.text.endswith(PHRASE_ENDS)
            and (last.out_e_f - first.out_s_f) * 1000 >= PHRASE_MS * fps
        )
    )


def _timed(
    groups: list[list[tuple[KeptWord, str]]], hide: Sequence[tuple[int, int]], fps: int
) -> list[Chunk]:
    tail = ms_to_f_ceil(TAIL_MS, fps)
    chunks: list[Chunk] = []
    for i, group in enumerate(groups):
        start = group[0][0].out_s_f
        end = group[-1][0].out_e_f + tail
        if i + 1 < len(groups):
            end = min(end, groups[i + 1][0][0].out_s_f)
        for a, _ in hide:
            if start < a < end:
                end = a
        if end > start:
            words = [ChunkWord(w.id, text, w.out_s_f) for w, text in group]
            chunks.append(Chunk(start, end, words))
    return chunks


def shown_chunks(
    chunks: Sequence[Chunk], shown: Mapping[str, str], cfg: CaptionsSection
) -> list[Chunk]:
    """The same chunks (same `s_f` and `e_f`) with the text of `shown` (id -> the text Claude may
    read) in place of the raw text, under the same rule of what is shown. A word that is left
    empty is no longer in its chunk. A word that `shown` does not have is an `InternalError`: this
    is the door between the raw text and what Claude reads, and it never falls back to the raw
    text (001.28, point 5)."""
    out: list[Chunk] = []
    for chunk in chunks:
        words = []
        for word in chunk.words:
            if word.id not in shown:  # a bug of kcut: `kept_words` gives a text to every kept word
                raise InternalError(
                    f"a la palabra {word.id} le falta su texto para Claude: "
                    "no se muestra el texto crudo de los subtítulos"
                )
            text = display_text(shown[word.id], cfg)
            if text:
                words.append(ChunkWord(word.id, text, word.s_f))
        out.append(Chunk(chunk.s_f, chunk.e_f, words))
    return out
