"""E-mail addresses in what people say or write (spec 001.13, 001.16, 001.18, 001.21, 001.22).

Written: `john.doe@gmail.com` in one word. Said: `john at gmail dot com`, `juan arroba gmail.com`,
`juan punto perez arroba gmail punto mx`, `info at big apple trucking dot com`, `juan uno dos tres
arroba gmail punto com`. The whole address leaves as `<first letter>***@***.<tld>`.
Scanning is linear: an `@` or an `at` is looked at once, with a bounded look around it.
"""

import re
from collections.abc import Sequence

from kcut.pack.pii_tokens import Tok
from kcut.pack.pii_vocab import HUNDREDS, TENS_ES, THOUSANDS, TWO_DIGITS, UNITS, VEINTI
from kcut.pack.pii_written import TLDS, tld_of

AT = frozenset({"at", "arroba"})
DOT = frozenset({"dot", "punto"})
# words that join the words of a local part; `guion` is the `-` said in Spanish (001.22, point 3)
JOIN = DOT | {"underscore", "dash", "hyphen", "guion"}
# Said aloud, a two-letter label after one of these makes a TLD of both: `com punto ar` (001.22)
SECOND_LEVEL = frozenset({"com", "net", "org", "co", "gob", "edu"})
# The last label of an address said with `dot` / `punto` may be any word of 2 to 24 letters
# (001.22, point 4). What is written keeps the closed list `TLDS`: opened, it would hide
# names like `logo@2x.png`, which Claude needs to refer to the file.
OPEN_TLD = re.compile(r"[a-z]{2,24}")
ARTICLES = frozenset({"the", "a", "an", "el", "la", "los", "las", "un", "una"})
MAX_LOCAL_WORDS = 4  # words of a local part (`guion bajo` joins two of them, it is not one)
MAX_LOCAL_DIGITS = 12  # digits said in a local part (`juan uno dos tres`)
MAX_LABEL_WORDS = 4  # words of one label of a domain (`big apple trucking company`)
MAX_LABEL_ARTICLES = 2  # articles a label may have besides those words (`the big apple...`)
MAX_LABELS = 5  # labels of a domain said aloud (`claro punto com punto do` is three)
_DOMAIN = re.compile(r"[\w\-]+(?:\.[\w\-]+)+")


def spoken_groups(toks: Sequence[Tok]) -> list[tuple[int, int, str]]:
    """Addresses said aloud, as `(first, last, tld)` positions in `toks`, left to right."""
    found: list[tuple[int, int, str]] = []
    floor = 0  # the first token an address may still use
    k = 0
    while k < len(toks):
        if toks[k].norm in AT:
            start = _local_start(toks, k, floor)
            domain = _domain(toks, k + 1)
            if start is not None and domain is not None:
                found.append((start, domain[0], domain[1]))
                floor = k = domain[0] + 1
                continue
        k += 1
    return found


def _spoken_tld(before: str, last: str) -> str:
    """The TLD an address said aloud shows: the last label, or both when it has two letters and
    the label before it is `com`, `net`, `org`, `co`, `gob` or `edu` (`com.ar`)."""
    return f"{before}.{last}" if len(last) == 2 and before in SECOND_LEVEL else last


def _word(tok: Tok) -> bool:
    return bool(tok.norm) and tok.norm not in AT and tok.norm not in JOIN


def _digit(tok: Tok) -> bool:
    """A digit said (`tres`), a tens or a teen said (`eighty`, `ochenta`, `veintiuno`), a hundred
    or a thousand said (`novecientos`, `hundred`, `mil`; 001.22) or a number written (`3`, `123`):
    part of a local part like any name."""
    return (
        tok.norm in UNITS
        or tok.norm in TWO_DIGITS
        or tok.norm in HUNDREDS
        or tok.norm in THOUSANDS
        or VEINTI.fullmatch(tok.norm) is not None
        or (tok.numeric and tok.digits > 0)
    )


def _local_start(toks: Sequence[Tok], at: int, floor: int) -> int | None:
    """The token where the local part that ends just before `at` begins.

    Up to `MAX_LOCAL_WORDS` words joined by `dot`, `punto`, `underscore`, `dash`, `hyphen` or
    `guion bajo`, and the digits said or written in it (`juan uno dos tres`, `john two three`):
    digits need no joiner, two words in a row do (`es juan arroba` is just `juan`).
    """
    j = at - 1
    start: int | None = None
    right = ""  # what the token to the right of `j` is: "W" word, "D" digit, "J" joiner
    words = digits = 0
    while j >= floor:
        tok = toks[j]
        size = 1  # tokens the joiner takes: `guion bajo` is two
        if tok.norm == "bajo" and j > floor and toks[j - 1].norm == "guion" and right in ("W", "D"):
            size = 2
        if size == 2 or tok.norm in JOIN:
            # a joiner needs the local part to its right and a word or a digit to its left;
            # several in a row (`guion guion`) count as one (001.24, point 13)
            if right in ("", "J"):
                break
            left = _past_joiners(toks, j - size, floor)
            if left < floor or not (_word(toks[left]) or _digit(toks[left])):
                break
            j, right = left, "J"
        elif tok.norm == "y" and right == "D" and j > floor and toks[j - 1].norm in TENS_ES:
            digits, start, right = digits + 1, j, "D"  # `ochenta y cinco`: the `y` goes with them
            j -= 1
        elif _digit(tok):
            if digits >= MAX_LOCAL_DIGITS:
                break
            digits, start, right = digits + 1, j, "D"
            j -= 1
        elif _word(tok) and right != "W" and words < MAX_LOCAL_WORDS:
            words, start, right = words + 1, j, "W"
            j -= 1
        else:
            break
    return start


def _past_joiners(toks: Sequence[Tok], k: int, floor: int) -> int:
    """`k` moved left over the joiners that sit in a row there, `guion bajo` being one of them:
    the position of the first token that is not one (below `floor` if there is none)."""
    while k >= floor:
        if toks[k].norm in JOIN:
            k -= 1
        elif toks[k].norm == "bajo" and k > floor and toks[k - 1].norm == "guion":
            k -= 2
        else:
            break
    return k


def _until_dot(toks: Sequence[Tok], pos: int) -> int | None:
    """How many tokens the label that starts at `pos` has before the `dot` / `punto` that closes
    it: up to `MAX_LABEL_WORDS` words, and up to `MAX_LABEL_ARTICLES` articles that do not count
    as words (`the big apple trucking company`); None if there is no such label."""
    words = articles = 0
    for size in range(MAX_LABEL_WORDS + MAX_LABEL_ARTICLES + 1):
        if pos + size >= len(toks):
            return None
        tok = toks[pos + size]
        if tok.norm in DOT:
            return size or None
        if not _label(tok):
            return None
        if tok.norm in ARTICLES:
            articles += 1
        else:
            words += 1
        if words > MAX_LABEL_WORDS or articles > MAX_LABEL_ARTICLES:
            return None
    return None


def _domain(toks: Sequence[Tok], first: int) -> tuple[int, str] | None:
    """The domain that starts at token `first`: its last token and its TLD. Either one token that
    holds it (`gmail.com`) or labels said with `dot`/`punto` (`gmail punto com`), each label of
    one to `MAX_LABEL_WORDS` words (`big apple trucking punto com`). The last label is a TLD of
    `TLDS` or, when every label after the first is one word, any word of 2 to 24 letters
    (`ops at fleet dot xyz`; 001.22): a longer label before it is more likely the next sentence
    (`... gmail dot com juan punto perez ...`) than part of the domain."""
    if first >= len(toks):
        return None
    head = toks[first]
    dotted = head.core.rstrip(".").lower()
    if "." in dotted and _DOMAIN.fullmatch(dotted):
        labels = dotted.split(".")
        return (first, tld_of(labels)) if labels[-1] in TLDS else None
    best: tuple[int, str] | None = None
    pos = first  # first word of the label being read
    before = ""  # the label before it, for `com.do`
    plain = True  # every label after the first is one word: only then may the TLD be any word
    for _ in range(MAX_LABELS):
        word = toks[pos].norm
        if pos > first and _label(toks[pos]) and (word in TLDS or (plain and _open_tld(word))):
            best = (pos, _spoken_tld(before, word))
        size = _until_dot(toks, pos)
        if size is None or pos + size + 1 >= len(toks) or not _label(toks[pos + size + 1]):
            break
        plain = plain and (pos == first or size == 1)
        before = " ".join(tok.norm for tok in toks[pos : pos + size])
        pos += size + 1
    return best


def _open_tld(norm: str) -> bool:
    """Is this normalized word one the last label of an address said aloud may be (001.22)?"""
    return OPEN_TLD.fullmatch(norm) is not None


def _label(tok: Tok) -> bool:
    return bool(tok.norm) and tok.norm not in AT and tok.norm not in DOT
