"""Markers that help Claude read a transcript: fillers, stutters, doubtful words, hallucinations
and repeated takes. Pure: words and silence runs in, flags out."""

from collections.abc import Iterable, Sequence
from difflib import SequenceMatcher

from kcut.analysis.energy import Run, word_in_silence
from kcut.pack.phrases import Phrase
from kcut.text.normalize import norm_token, norm_tokens
from kcut.transcribe.model import Word

# One letter per marker, always written in this order: filler, repetition (stutter), doubtful
# probability, possible hallucination, corrected. `V` (the other camera heard something else) is
# added by the pack, after the votes.
FLAG_ORDER = "FR?HC"
RETAKE_MAX_GAP_MS = 60_000
RETAKE_MIN_TOKENS = 3
RETAKE_MIN_RATIO = 0.75


def filler_sequences(fillers: Iterable[str]) -> list[tuple[str, ...]]:
    """Token sequence of each filler (`"o sea"` -> `("o", "sea")`), longest first. Entries that
    normalize to nothing are dropped."""
    unique = {tuple(norm_tokens(filler)) for filler in fillers}
    return sorted((seq for seq in unique if seq), key=lambda seq: (-len(seq), seq))


def word_flags(
    words: Sequence[Word],
    fillers: Sequence[tuple[str, ...]],
    low_prob: float,
    silences: Sequence[Run],
) -> list[str]:
    """Flags of each word of one phrase, as strings of letters from `FLAG_ORDER`.

    F: the word belongs to a filler sequence (also the multi-word ones). R: its token equals the
    previous word's token in the same phrase. ?: `p < low_prob`. H: the whole word lies inside a
    silence run. C: the word was corrected.
    """
    tokens = [norm_token(word.text) for word in words]
    filler = _filler_mask(tokens, fillers)
    flags: list[str] = []
    for i, word in enumerate(words):
        marks = {
            "F": filler[i],
            "R": i > 0 and tokens[i] != "" and tokens[i] == tokens[i - 1],
            "?": word.p < low_prob,
            "H": word_in_silence(word, silences),
            "C": word.corrected,
        }
        flags.append("".join(letter for letter in FLAG_ORDER if marks[letter]))
    return flags


def retakes(phrases: Sequence[Phrase]) -> list[int | None]:
    """For each phrase, the `start_ms` of the most recent earlier phrase of the same clip that
    it repeats, or None. The earlier phrase needs 3 or more tokens, must start at most 60 s
    before this one, and `SequenceMatcher(None, earlier, this).ratio()` must be 0.75 or more."""
    tokens = [[t for t in (norm_token(w.text) for w in p.words) if t] for p in phrases]
    found: list[int | None] = []
    for j, phrase in enumerate(phrases):
        found.append(None)
        for i in range(j - 1, -1, -1):
            if phrase.start_ms - phrases[i].start_ms > RETAKE_MAX_GAP_MS:
                break
            if len(tokens[i]) < RETAKE_MIN_TOKENS:
                continue
            if SequenceMatcher(None, tokens[i], tokens[j]).ratio() >= RETAKE_MIN_RATIO:
                found[j] = phrases[i].start_ms
                break
    return found


def _filler_mask(tokens: Sequence[str], fillers: Sequence[tuple[str, ...]]) -> list[bool]:
    """True for every token inside a filler sequence; longest sequences win, no overlaps."""
    mask = [False] * len(tokens)
    i = 0
    while i < len(tokens):
        size = next((len(f) for f in fillers if tuple(tokens[i : i + len(f)]) == f), 0)
        if size:
            mask[i : i + size] = [True] * size
        i += size or 1
    return mask
