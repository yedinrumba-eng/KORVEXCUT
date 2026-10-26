"""Words as the PII detector reads them (spec 001.16 and 001.17): folded, cut in three, classified.

Every word is analysed once and in time linear in its length: `mask_pii` has to stay linear on a
hostile transcript (tens of thousands of words of 200 characters), so nothing here backtracks,
`norm_token` sees at most `NORM_CAP` characters of a word and NFKC at most `FOLD_CAP`.
"""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from kcut.pack.pii_vocab import (
    HUNDREDS,
    MULTIPLIERS,
    TENS_EN,
    TENS_ES,
    THOUSANDS,
    TWO_DIGITS,
    UNITS,
    UNITS_EN,
    UNITS_ES,
    VEINTI,
    Bridges,
    collapse,
    hyphen_parts,
    is_number_word,
)
from kcut.text.normalize import norm_token
from kcut.transcribe.model import Word

NORM_CAP = 40  # characters of a core that are normalized: no number said in words is longer
FOLD_CAP = 64  # characters of a word that are folded with NFKC; the rest is kept as it came
LOOSE = frozenset(",/–—…")  # a token of only these sits inside a number for free
# What stays outside a word: everything that is not a letter, a digit, `_` or one of `( ) + - . @`
_EDGE = re.compile(r"[^\w()+\-.@]*")
# The core of a number: digits (any script) and the separators that can sit between them.
# NFKC turns a NBSP into a plain space, so a space is a separator too.
_NUMERIC = re.compile(r"[\d()+\-.,/_" + chr(0x2013) + chr(0x2014) + " ]+")


@dataclass(slots=True)
class Tok:
    """A word (or a piece of a hyphenated one) cut into `pre`, `core` and `post`."""

    at: int  # position in the list of words it came from
    uid: int  # position in the list of tokens
    text: str  # the folded text of the whole word
    pre: str  # edge before the core (only on the first piece)
    core: str
    post: str  # edge after the core (only on the last piece)
    norm: str  # `norm_token` of the core
    digits: int  # characters of the core that are decimal digits
    numeric: bool  # the core is digits and separators only
    piece: int = 0  # `five-five-one` is three pieces of one word
    pieces: int = 1
    loose: bool = False  # nothing but `, / – — …`
    slots: int = 0  # digits it takes in a number (0 if it takes none)
    shows: str = ""  # the digit it shows if it is among the last two ("" = always stars)
    neutral: bool = False  # sits inside a number and counts for nothing (`-`, `double`, `y`)
    bridge: bool = False  # a word that may sit between two groups of digits (it costs one)
    joined: bool = False  # the first word of a filler of several words (`o` of `o sea`)
    cont: bool = False  # a later word of such a filler: part of the same bridge, free


def _fold(text: str) -> str:
    """NFKC on the first `FOLD_CAP` characters, without format characters (ZWSP and the like)."""
    if text.isascii():
        return text
    head = unicodedata.normalize("NFKC", text[:FOLD_CAP])
    return "".join(ch for ch in head if unicodedata.category(ch) != "Cf") + text[FOLD_CAP:]


def _edge_length(text: str) -> int:
    match = _EDGE.match(text)
    return match.end() if match else 0


def tokenize(words: Sequence[Word], positions: Sequence[int]) -> list[Tok]:
    """The words at `positions`, folded and cut into edges and core. A word of number words joined
    with hyphens (`five-five-one`) is one token per piece."""
    toks: list[Tok] = []
    for at in positions:
        text = _fold(words[at].text)
        if not text:  # all format characters: as good as deleted
            continue
        start = _edge_length(text)
        if start == len(text):
            pre, core, post = text, "", ""
        else:
            end = len(text) - _edge_length(text[::-1])
            pre, core, post = text[:start], text[start:end], text[end:]
        numeric = bool(core) and _NUMERIC.fullmatch(core) is not None
        pieces = _number_pieces(core) if not numeric and "-" in core else None
        if pieces is None:
            norm = "at" if core == "@" else norm_token(core[:NORM_CAP])  # a loose `@` is "at"
            tok = Tok(at, len(toks), text, pre, core, post, norm, 0, numeric)
            tok.digits = sum(map(str.isdecimal, core))
            tok.loose = not core and all(ch in LOOSE for ch in text)
            toks.append(tok)
            continue
        for n, piece in enumerate(pieces):
            last = n == len(pieces) - 1
            norm = norm_token(piece[:NORM_CAP])
            toks.append(
                Tok(
                    at, len(toks), text, pre if n == 0 else "", piece, post if last else "", norm,
                    0, False, piece=n, pieces=len(pieces),
                )
            )  # fmt: skip
    return toks


def _number_pieces(core: str) -> list[str] | None:
    """The pieces of `core` if it is number words joined with hyphens, else None."""
    pieces = core.split("-")
    if len(pieces) > 1 and all(p and is_number_word(norm_token(p[:NORM_CAP])) for p in pieces):
        return pieces
    return None


def classify(toks: Sequence[Tok], bridges: Bridges) -> None:
    """Say, for each token, how many digits it takes in a number (`slots`) and whether it may sit
    between two groups of digits. Neighbours matter: "thirty four" is two digits, "double five"
    is two, "treinta y cuatro" is two, "two hundred" is three."""
    i = 0
    while i < len(toks):
        tok = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        after = toks[i + 2] if i + 2 < len(toks) else None
        norm = tok.norm
        if tok.numeric:
            tok.slots = tok.digits
            tok.neutral = tok.digits == 0
        elif tok.loose:
            tok.neutral = True
        elif norm in TENS_EN and nxt is not None and nxt.norm in UNITS_EN:
            tok.slots = nxt.slots = 1
            i += 2
            continue
        elif (
            norm in TENS_ES
            and nxt is not None
            and nxt.norm == "y"
            and after is not None
            and after.norm in UNITS_ES
        ):
            tok.slots = after.slots = 1
            nxt.neutral = True
            i += 3
            continue
        elif norm in UNITS_EN and nxt is not None and nxt.norm == "hundred":
            tok.slots, nxt.slots = 1, 2
            i += 2
            continue
        elif norm in HUNDREDS or norm in THOUSANDS:
            tok.slots = 3
        elif norm in TWO_DIGITS or VEINTI.fullmatch(norm):
            tok.slots = 2
        elif norm in MULTIPLIERS and nxt is not None and _one_digit(nxt):
            tok.neutral = True
            nxt.slots = MULTIPLIERS[norm]
            i += 2
            continue
        elif norm in UNITS:
            tok.slots, tok.shows = 1, UNITS[norm]
        i += 1
    _mark_bridges(toks, bridges)


def _one_digit(tok: Tok) -> bool:
    """A digit said (`five`) or written (`5`): what `double` and `triple` repeat."""
    return tok.norm in UNITS or (tok.numeric and tok.digits == 1 and len(tok.core) == 1)


def _mark_bridges(toks: Sequence[Tok], bridges: Bridges) -> None:
    """Flag the words that may sit between two groups of digits. A filler of several words counts
    as one bridge: its first word costs it, the others are free."""
    i = 0
    while i < len(toks):
        tok = toks[i]
        i += 1
        if tok.slots or tok.neutral or tok.numeric or not tok.norm:
            continue
        cnorm = collapse(tok.norm)
        length = _sequence_length(toks, i - 1, cnorm, bridges)
        if length:
            tok.bridge = tok.joined = True
            for later in toks[i : i + length - 1]:
                later.cont = True
            i += length - 1
        elif cnorm in bridges.words or (
            "-" in tok.core and hyphen_parts(tok.core) in bridges.sequences
        ):
            tok.bridge = True


def _sequence_length(toks: Sequence[Tok], at: int, first: str, bridges: Bridges) -> int:
    """How many words from `at` are a filler of several words (0 if none)."""
    if first not in bridges.firsts:
        return 0
    for length in range(min(bridges.longest, len(toks) - at), 1, -1):
        window = toks[at : at + length]
        if all(not t.slots and not t.neutral and not t.numeric for t in window) and (
            tuple(collapse(t.norm) for t in window) in bridges.sequences
        ):
            return length
    return 0
