"""PII masking for what Claude reads (spec 001.13 and 001.16). Pure: words in, words and ids out.

What a person says in a video reaches `transcripcion.md` and `palabras.tsv`, and Claude reads both,
so phone numbers, ID numbers, card numbers and e-mail addresses are masked there. The cache keeps
the raw words: subtitles and QA need what was really said. It is a heuristic on speech; its known
limits are in spec 001.16, point 11.

- A run of tokens that are digits (of any script, `( ) + - . , / _` and dashes inside), or digits
  said in words (English and Spanish, with tens, `double` and `triple`), is PII when it adds up to 7
  digits. Up to two fillers or words like `y`, `dash` may sit between two groups of digits. Every
  digit but the last two becomes `*`; separators stay and every word keeps its edges.
- A token with letters and 7 digits or more (`tel8095551234`) loses its digits too.
- An address written in one word (`john.doe@gmail.com`) or said (`john at gmail dot com`,
  `juan arroba gmail punto com`) becomes `j***@***.com`.
- `mask_pii_spans` also says which words sit inside a masked number, bridges and separators
  included (spec 001.17, point 2): what another camera heard in their place must not be shown.

Mixed letters and a few digits (`C21`), times (`5:31`) and short numbers (years) are not PII. Each
word is analysed once (see `pii_tokens`), so the cost is linear in the characters.
"""

import re
from collections.abc import Sequence
from dataclasses import replace

from kcut.pack.pii_email import mask_written, masked_address, spoken_groups
from kcut.pack.pii_numbers import compose, mask_lettered, mask_run, number_runs
from kcut.pack.pii_tokens import Tok, classify, tokenize
from kcut.pack.pii_vocab import bridge_tokens
from kcut.transcribe.model import Word

_PATH_SEPARATORS = re.compile(r"([/_.\-])")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def mask_pii(words: Sequence[Word], fillers: Sequence[str] = ()) -> tuple[list[Word], set[str]]:
    """The words as they are shown, and the ids of the ones that were masked.

    `words` are in time order; a word with no text (deleted) is skipped and does not cut a run.
    `fillers` (`transcribe.fillers`) may sit between two groups of digits. The input is not
    changed. Spoken addresses are looked for first, then written ones, then numbers over the rest.
    """
    shown, ids, _ = mask_pii_spans(words, fillers)
    return shown, ids


def mask_pii_spans(
    words: Sequence[Word], fillers: Sequence[str] = ()
) -> tuple[list[Word], set[str], set[str]]:
    """`mask_pii` plus a third set: the ids of every word inside a masked number or address,
    the masked words themselves and also the bridges (`y`, `eh`) and separators between them."""
    shown = list(words)
    present = [i for i, word in enumerate(words) if word.text]
    toks = tokenize(words, present)
    changed: dict[int, str] = {}
    taken: set[int] = set()
    for first, last, tld in spoken_groups(toks):
        group = toks[first : last + 1]
        changed[group[0].at] = masked_address(group[0].text, tld)
        changed.update({tok.at: "" for tok in group[1:]})
        taken.update(tok.at for tok in group)
    for tok in toks:
        if tok.at not in taken and tok.piece == 0 and "@" in tok.text:
            masked = mask_written(tok.text)
            if masked is not None:
                changed[tok.at] = masked
                taken.add(tok.at)
    rest = [tok for tok in toks if tok.at not in taken]
    classify(rest, bridge_tokens(fillers))
    inside: set[int] = set()
    cores: dict[int, str] = {}
    for run in number_runs(rest):
        cores.update(mask_run(run))
        inside.update(tok.at for tok in run)
    by_word: dict[int, list[Tok]] = {}
    for tok in rest:
        by_word.setdefault(tok.at, []).append(tok)
    for tok in rest:
        lettered = mask_lettered(tok)
        if lettered is not None:
            changed[tok.at] = lettered
    for at in {tok.at for tok in rest if tok.uid in cores}:
        changed[at] = compose(by_word[at], cores)
    for at, text in changed.items():
        shown[at] = replace(words[at], text=text)
    ids = {words[at].id for at in changed} | {words[at].id for at in taken}
    return shown, ids, ids | {words[at].id for at in inside}


def mask_text(text: str, fillers: Sequence[str] = (), *, parts: bool = True) -> str:
    """`text` with the PII in its words masked, spaces kept.

    With `parts` (a file name, a path) the text is cut at `/ _ . -`, the final extension is left
    out, and every part is read on its own: `GX010123.MP4` stays, `Juan 809 555 1234.mp4` does not
    (spec 001.17, point 6). Without it (a project name, an error) the words are read whole.
    """
    if not parts:
        return _mask_phrase(text, fillers)
    ext = _EXTENSION.search(text)
    body, tail = (text[: ext.start()], ext.group()) if ext else (text, "")
    pieces = _PATH_SEPARATORS.split(body)
    pieces[::2] = [_mask_phrase(piece, fillers) for piece in pieces[::2]]
    return "".join(pieces) + tail


def _mask_phrase(text: str, fillers: Sequence[str]) -> str:
    pieces = re.split(r"(\s+)", text)
    words = [Word(f"t{n}", n, piece, 0, 1, 1.0) for n, piece in enumerate(pieces[::2])]
    pieces[::2] = [word.text for word in mask_pii(words, fillers)[0]]
    return "".join(pieces)
