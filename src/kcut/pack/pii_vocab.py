"""The words the PII detector knows (spec 001.16 and 001.17): numbers said in English and Spanish,
and the words that may sit between two groups of digits.

Everything here is already in the form `norm_token` gives: lower case, no accents, `[a-z0-9]`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from kcut.text.normalize import norm_token, norm_tokens

UNITS = {
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "cero": "0", "uno": "1", "una": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5",
    "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
}  # fmt: skip
UNITS_EN = frozenset({"one", "two", "three", "four", "five", "six", "seven", "eight", "nine"})
UNITS_ES = frozenset(
    {"uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"}
)
TENS_EN = frozenset({"twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"})
TENS_ES = frozenset(
    {"diez", "veinte", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta"}
    | {"noventa"}
)  # "treinta y cuatro" is two digits, like "thirty four"
HUNDREDS = frozenset(
    {"hundred", "cien", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos"}
    | {"seiscientos", "setecientos", "ochocientos", "novecientos"}
)  # three digits each ("two hundred" is two words of three digits in all)
TWO_DIGITS = TENS_EN | TENS_ES | frozenset({
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "once", "doce", "trece", "catorce", "quince", "dieciseis",
    "diecisiete", "dieciocho", "diecinueve",
})  # fmt: skip
VEINTI = re.compile(r"veinti(?:un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)")
MULTIPLIERS = {"double": 2, "doble": 2, "triple": 3}
FIXED_BRIDGES = ("y", "and", "dash", "guion", "o", "double", "doble", "triple")


def is_number_word(norm: str) -> bool:
    """Is this normalized word one of the pieces of a number said in words?"""
    return (
        norm in UNITS
        or norm in TWO_DIGITS
        or norm in HUNDREDS
        or norm in MULTIPLIERS
        or norm in ("y", "and")
        or VEINTI.fullmatch(norm) is not None
    )


def collapse(word: str) -> str:
    """Repeated letters count once, so a filler stretched in speech is still the filler:
    `ehhh` -> `eh`, `ummm` -> `um`."""
    out: list[str] = []
    for ch in word:
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)


@dataclass(frozen=True)
class Bridges:
    """What may sit between two groups of digits: single words, and fillers of several words
    (`o sea`, `you know`), each of which counts as ONE bridge (spec 001.17, point 3)."""

    words: frozenset[str]
    sequences: frozenset[tuple[str, ...]]
    firsts: frozenset[str]
    longest: int


def bridge_tokens(fillers: Iterable[str]) -> Bridges:
    """The bridges for these fillers (`transcribe.fillers`) plus the fixed ones."""
    words = {collapse(w) for w in FIXED_BRIDGES}
    sequences: set[tuple[str, ...]] = set()
    for filler in fillers:
        parts = tuple(collapse(t) for t in norm_tokens(filler))
        if len(parts) == 1:
            words.add(parts[0])
        elif parts:
            sequences.add(parts)
    return Bridges(
        frozenset(words),
        frozenset(sequences),
        frozenset(seq[0] for seq in sequences),
        max((len(seq) for seq in sequences), default=0),
    )


def hyphen_parts(core: str) -> tuple[str, ...]:
    """`uh-huh` -> (`uh`, `huh`): the collapsed words of a core joined with hyphens."""
    return tuple(c for c in (collapse(norm_token(p)) for p in core.split("-")) if c)
