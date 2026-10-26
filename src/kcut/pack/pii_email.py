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

MASKED = "{first}***@***.{tld}"
AT = frozenset({"at", "arroba"})
DOT = frozenset({"dot", "punto"})
# words that join the words of a local part; `guion` is the `-` said in Spanish (001.22, point 3)
JOIN = DOT | {"underscore", "dash", "hyphen", "guion"}
TLDS = frozenset(
    {"com", "net", "org", "edu", "gov", "io", "co", "us", "do", "mx", "es", "info", "biz", "pr"}
    | {"uk", "ca", "cl", "dev", "app", "ai"}
    | {"ph", "au", "br", "jp", "de", "fr", "it", "nl"}  # 001.21
)
# `claro.com.do` ends in `.com.do`, not in `.do`; the same for the other second-level ones (001.21)
COMPOUND_TLDS = ("com.do", "net.do", "com.au", "co.uk", "com.mx", "com.br", "co.jp")
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


def masked_address(first_text: str, tld: str) -> str:
    """`<first letter or digit of the address>***@***.<tld>`."""
    return MASKED.format(first=next((ch for ch in first_text if ch.isalnum()), ""), tld=tld)


def mask_written(text: str) -> str | None:
    """`text` with each written address masked, or None if it holds none.

    An address is the local part (`\\w . + -`, maybe empty) before an `@` and a domain of two or
    more labels after it. The local part does not reach back over a previous address.
    """
    split = split_written(text)
    return None if split is None else split[0] + split[1]


def split_written(text: str) -> tuple[str, str] | None:
    """`text` cut after its last written address: the part up to and including the masked
    address, and what follows it untouched (`;8095551234` in `juan@gmail.com;8095551234`).
    None if there is no address (001.22, point 6)."""
    out: list[str] = []
    done = 0  # text before this position is already copied or masked
    at = text.find("@")
    while at != -1:
        start = at
        while start > done and _is_local(text[start - 1]):
            start -= 1
        end = _domain_end(text, at + 1)
        if end > at + 1:
            out.append(text[done:start])
            tld = _tld_of(text[at + 1 : end].lower().split("."))
            out.append(MASKED.format(first=text[start:at][:1], tld=tld))
            done = end
            at = text.find("@", end)
        else:
            at = text.find("@", at + 1)
    if not out:
        return None
    return "".join(out), text[done:]


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


def _tld_of(labels: Sequence[str]) -> str:
    """The TLD a domain ends in: the last label, or `com.do` / `net.do` for the compound ones."""
    last = labels[-1]
    if len(labels) > 1 and f"{labels[-2]}.{last}" in COMPOUND_TLDS:
        return f"{labels[-2]}.{last}"
    return last


def _spoken_tld(before: str, last: str) -> str:
    """The TLD an address said aloud shows: the last label, or both when it has two letters and
    the label before it is `com`, `net`, `org`, `co`, `gob` or `edu` (`com.ar`)."""
    return f"{before}.{last}" if len(last) == 2 and before in SECOND_LEVEL else last


def _is_local(ch: str) -> bool:
    return ch.isalnum() or ch in "_.+-"


def _is_label(ch: str) -> bool:
    return ch.isalnum() or ch in "_-"


def _domain_end(text: str, start: int) -> int:
    """Where the domain that starts at `start` ends (`label(.label)+`), or `start` if there is
    none.

    The last label, the TLD, is made only of letters (001.23, point 2): what follows is not part
    of the address. A last label that is not (`8095551234`) is left out; one that begins with
    letters (`com-8095551234`) is cut after them. What is left must still have two labels. A
    hyphen inside the domain (`mi-empresa.com`) is part of it."""
    pos = start
    spans: list[tuple[int, int]] = []  # each label, from where it begins to where it ends
    while True:
        end = pos
        while end < len(text) and _is_label(text[end]):
            end += 1
        if end == pos:
            break
        spans.append((pos, end))
        pos = end
        if pos + 1 < len(text) and text[pos] == "." and _is_label(text[pos + 1]):
            pos += 1
            continue
        break
    while spans:
        first, last = spans[-1]
        letters = _letters(text, first, last)
        if letters == last:
            break
        if letters > first:
            spans[-1] = (first, letters)
            break
        spans.pop()
    return spans[-1][1] if len(spans) >= 2 else start


def _letters(text: str, first: int, last: int) -> int:
    """Where the run of letters that begins at `first` ends (`first` if it does not begin with
    one); never past `last`."""
    pos = first
    while pos < last and text[pos].isalpha():
        pos += 1
    return pos


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
            # a joiner needs the local part to its right and a word or a digit to its left
            if right in ("", "J") or j - size < floor:
                break
            if not (_word(toks[j - size]) or _digit(toks[j - size])):
                break
            j, right = j - size, "J"
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
        return (first, _tld_of(labels)) if labels[-1] in TLDS else None
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
