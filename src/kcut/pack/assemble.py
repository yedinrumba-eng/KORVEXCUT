"""Puts the pieces of one clip together: phrases, markers and votes become the `MdClip` body and
the rows of `palabras.tsv` (spec S1.3). Pure: no files, no console.

This is where PII is masked (spec 001.13), once, after the corrections and the vote and before the
writer: everything Claude reads comes out of here.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

from kcut.analysis.energy import silence_runs, voiced_without_words
from kcut.config.model import AnalysisSection
from kcut.pack.markers import FLAG_ORDER, filler_sequences, retakes, word_flags
from kcut.pack.phrases import split_phrases
from kcut.pack.pii import mask_pii, mask_pii_spans
from kcut.pack.votes import Tally
from kcut.pack.writer import MdPhrase, MdWord, TsvRow
from kcut.text.normalize import norm_token
from kcut.transcribe.model import Word

HOP_MS = 10  # energy resolution
PII_FLAG = "P"
VOTE_FLAG = "V"
ROW_FLAGS = FLAG_ORDER + PII_FLAG + VOTE_FLAG  # F R ? H C P, then V


@dataclass(frozen=True)
class ClipParts:
    phrases: list[MdPhrase]
    sounds: list[tuple[int, int]]
    rows: list[TsvRow]


def assemble_clip(
    clip_id: str,
    raw: Sequence[Word],
    words: Sequence[Word],
    db: NDArray[np.float32],
    analysis: AnalysisSection,
    fillers: Sequence[str],
    alts: Mapping[str, str],
    mask: bool = True,
    covered: Collection[str] = (),
) -> ClipParts:
    """Phrases, voice-without-words and tsv rows of a clip.

    `raw` are the transcript's words; `words` are the same after the corrections (a deleted word
    has no text and a split one has extra `<id>.N` tokens). `db` is the energy of the clip's wav16
    in 10 ms blocks, `alts` the votes of the other cameras by RAW word id (001.12, point 3):
    the tsv keeps every vote, the md shows `[≠x]` only while the corrected text still differs.
    With `mask`, PII is masked in `words` (md and the `corrected` column) and in `raw` (the `text`
    column); the rows get the `P` flag. `covered` are the raw ids that sit under the mask of
    another camera (`crosscam`): they are masked too. `alts` come already masked (`displayed_alts`:
    a member is masked with its whole transcript around the word, 001.16 point 1); here the votes
    on every master word inside a masked number are hidden, bridges and separators included
    (001.17, point 2).
    """
    silences = silence_runs(db, HOP_MS, analysis.silence_db, analysis.min_silence_ms)
    nothing = set[str]()
    words, hidden, inside = (
        mask_pii_spans(words, fillers) if mask else (list(words), nothing, nothing)
    )
    raw, raw_hidden, raw_inside = (
        mask_pii_spans(raw, fillers) if mask else (list(raw), nothing, nothing)
    )
    words, extra = _cover(words, covered)  # words under another camera's mask (001.17, point 2)
    raw, raw_extra = _cover(raw, covered)
    hidden, raw_hidden = hidden | extra, raw_hidden | raw_extra
    inside, raw_inside = inside | extra, raw_inside | raw_extra
    alts = _masked_alts(alts, words, inside | raw_inside) if mask else alts
    # a word masked down to nothing (a spoken address) still takes its time in the phrase
    kept = [w for w in words if w.text or w.id in hidden]
    sequences = filler_sequences(fillers)
    phrases = split_phrases(kept, silences, analysis.phrase_pause_ms)
    flags: dict[str, str] = {}
    shown = _shown_alts(words, alts, hidden | raw_hidden)
    md_phrases: list[MdPhrase] = []
    for phrase, retake in zip(phrases, retakes(phrases), strict=True):
        marks = word_flags(phrase.words, sequences, analysis.low_prob, silences)
        flags.update((w.id, f) for w, f in zip(phrase.words, marks, strict=True))
        md_words = [
            MdWord(w.text, f, shown.get(w.id))
            for w, f in zip(phrase.words, marks, strict=True)
            if w.text
        ]
        md_phrases.append(
            MdPhrase(phrase.start_ms, phrase.end_ms, phrase.pause_before_ms, md_words, retake)
        )
    for word in words:
        if word.id not in flags:  # a deleted word: no phrase, but its flags still go to the tsv
            flags[word.id] = word_flags([word], sequences, analysis.low_prob, silences)[0]
    sounds = voiced_without_words(db, HOP_MS, analysis.silence_db, kept)
    rows = _rows(clip_id, raw, words, flags, alts, hidden | raw_hidden)
    return ClipParts(md_phrases, sounds, rows)


def _cover(words: Sequence[Word], covered: Collection[str]) -> tuple[list[Word], set[str]]:
    """The words whose raw id is in `covered` with their letters and digits turned into `*`, and
    their ids. They count as masked: `P` flag, no alternative, no correction shown."""
    shown = list(words)
    ids: set[str] = set()
    for i, word in enumerate(words):
        if word.text and word.id.partition(".")[0] in covered:
            shown[i] = replace(word, text="*")
            ids.add(word.id)
    return shown, ids


def _pieces(words: Sequence[Word]) -> dict[str, list[Word]]:
    """The corrected words grouped by the raw word they came from (`a1:w0031` and `.1`, `.2`...)."""
    pieces: dict[str, list[Word]] = {}
    for word in words:
        pieces.setdefault(word.id.partition(".")[0], []).append(word)
    return pieces


def displayed_alts(
    tally: Tally, members: Sequence[Sequence[Word]], fillers: Sequence[str], mask: bool
) -> dict[str, str]:
    """The text of each alternative as it is shown (spec 001.16, point 1).

    The vote runs on raw words, but what is shown is the masked text of the member's word, with
    the member's WHOLE transcript masked first: a digit heard alone is part of a number only in
    its context. A word masked down to nothing (a piece of a spoken address) shows `*`.
    `members` are the transcripts, in the order they were given to the vote.
    """
    if not mask:
        return dict(tally.alternatives)
    texts = [{w.id: w.text for w in mask_pii(words, fillers)[0]} for words in members]
    return {
        master_id: texts[member].get(word_id) or "*"
        for master_id, (member, word_id) in tally.sources.items()
    }


def _masked_alts(
    alts: Mapping[str, str], words: Sequence[Word], hidden: Collection[str]
) -> dict[str, str]:
    """The votes on a master word inside a masked number (`inside`: the masked words, the bridges
    and the separators between them) are hidden whole, whichever camera they came from; the others
    are already masked."""
    pieces = _pieces(words)
    return {
        raw_id: "*"
        if raw_id in hidden or any(t.id in hidden for t in pieces.get(raw_id, []))
        else alt
        for raw_id, alt in alts.items()
    }


def _shown_alts(
    words: Sequence[Word], alts: Mapping[str, str], hidden: Collection[str] = ()
) -> dict[str, str]:
    """Token id -> the other camera's text, for the votes the md still shows.

    A vote is on the raw word. Once the word is corrected, `[≠x]` is only noise if the corrected
    text (all its tokens together) now says what the other camera heard, after `norm_token`.
    The first token of the word carries the mark. A masked word shows no variant at all.
    """
    pieces = _pieces(words)
    shown: dict[str, str] = {}
    for raw_id, alt in alts.items():
        tokens = pieces.get(raw_id)
        if not tokens or raw_id in hidden or any(t.id in hidden for t in tokens):
            continue
        displayed = " ".join(t.text for t in tokens if t.text)
        if displayed and norm_token(displayed) != norm_token(alt):
            shown[tokens[0].id] = alt
    return shown


def _rows(
    clip_id: str,
    raw: Sequence[Word],
    words: Sequence[Word],
    flags: Mapping[str, str],
    alts: Mapping[str, str],
    hidden: Collection[str] = (),
) -> list[TsvRow]:
    """One row per raw word. Its flags are those of the word and of any tokens it was split
    into, `P` if it was masked, and `V` if another camera heard something else."""
    pieces = _pieces(words)
    rows: list[TsvRow] = []
    for word in raw:
        tokens = pieces.get(word.id, [word])
        alt = alts.get(word.id, "")
        letters = {c for t in tokens for c in flags.get(t.id, "")}
        if word.id in hidden or any(t.id in hidden for t in tokens):
            letters.add(PII_FLAG)
        if alt:
            letters.add(VOTE_FLAG)
        corrected = " ".join(t.text for t in tokens) if tokens[0].corrected else ""
        rows.append(
            TsvRow(
                id=word.id,
                clip=clip_id,
                s_ms=word.s_ms,
                e_ms=word.e_ms,
                p=word.p,
                flags="".join(c for c in ROW_FLAGS if c in letters),
                text=word.text,
                alt=alt,
                corrected=corrected,
            )
        )
    return rows
