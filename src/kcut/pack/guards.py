"""What `pack` refuses to do with corrections when PII is masked (spec 001.13 and 001.17).

A correction may not touch a masked word (Claude would have seen what the mask hides), and a
correction elsewhere may not break a masked number open: changing the `eh` between two groups of
digits would leave each group short of seven digits and in plain sight.
"""

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from kcut.errors import CheckFailed
from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Transcript, Word


def refuse_masked(
    transcripts: Mapping[str, Transcript],
    corrections: Mapping[str, Any],
    fillers: Sequence[str],
    covered: Mapping[str, Collection[str]] | None = None,
) -> None:
    """CheckFailed if a correction points at a word that is masked (spec 001.13, point 5), by its
    own camera or because it sits under the mask of another one (`covered`, 001.17).

    The message names only the id: the text behind a mask is never quoted, and the answer is the
    same whatever `expect` says.
    """
    for clip_id, transcript in transcripts.items():
        _, masked = mask_pii(transcript.words, fillers)
        masked = masked | set((covered or {}).get(clip_id, ()))
        hit = sorted(word_id for word_id in corrections if word_id in masked)
        if hit:
            raise CheckFailed(
                f"la palabra {hit[0]} está enmascarada por privacidad; no se corrige desde aquí"
            )


def refuse_unmasked(
    raw: Mapping[str, Sequence[Word]],
    corrected: Mapping[str, Sequence[Word]],
    fillers: Sequence[str],
) -> None:
    """CheckFailed if, after the corrections, a word that was masked in the raw text is not.

    Deleting a word is fine; what is not is showing a digit that was hidden. The message names the
    correction nearest to the word that came to light, and nothing else (spec 001.17, point 5).
    """
    for clip_id, words in raw.items():
        fixed = corrected[clip_id]
        if not any(word.corrected for word in fixed):
            continue
        _, masked_before = mask_pii(words, fillers)
        if not masked_before:
            continue
        _, masked_now = mask_pii(fixed, fillers)
        pieces: dict[str, list[Word]] = {}
        for word in fixed:
            pieces.setdefault(word.id.partition(".")[0], []).append(word)
        touched = [i for i, word in enumerate(words) if pieces[word.id][0].corrected]
        for index, word in enumerate(words):
            shown = [p for p in pieces[word.id] if p.text]
            if word.id in masked_before and any(p.id not in masked_now for p in shown):
                blamed = min(touched, key=lambda i: abs(i - index))
                raise CheckFailed(
                    f"la corrección de {words[blamed].id} dejaría ver un dato privado; no se aplica"
                )
