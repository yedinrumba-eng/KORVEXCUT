"""E-mail addresses in what people say or write (spec 001.13 and 001.16).

Written: `john.doe@gmail.com` in one word. Said: `john at gmail dot com`, `juan arroba gmail.com`,
`juan punto perez arroba gmail punto mx`. The whole address leaves as `<first letter>***@***.<tld>`.
Scanning is linear: an `@` or an `at` is looked at once, with a bounded look around it.
"""

import re
from collections.abc import Sequence

from kcut.pack.pii_tokens import Tok

MASKED = "{first}***@***.{tld}"
AT = frozenset({"at", "arroba"})
DOT = frozenset({"dot", "punto"})
JOIN = DOT | {"underscore"}  # words that join the words of a local part (`guion bajo` is two)
TLDS = frozenset(
    {"com", "net", "org", "edu", "gov", "io", "co", "us", "do", "mx", "es", "info", "biz", "pr"}
    | {"uk", "ca", "cl", "dev", "app", "ai"}
)
COMPOUND_TLDS = ("com.do", "net.do")  # `claro.com.do` ends in `.com.do`, not in `.do`
MAX_LOCAL_WORDS = 3
MAX_LABELS = 5  # words of a domain said aloud (`claro punto com punto do` is three)
_DOMAIN = re.compile(r"[\w\-]+(?:\.[\w\-]+)+")


def masked_address(first_text: str, tld: str) -> str:
    """`<first letter or digit of the address>***@***.<tld>`."""
    return MASKED.format(first=next((ch for ch in first_text if ch.isalnum()), ""), tld=tld)


def mask_written(text: str) -> str | None:
    """`text` with each written address masked, or None if it holds none.

    An address is the local part (`\\w . + -`, maybe empty) before an `@` and a domain of two or
    more labels after it. The local part does not reach back over a previous address.
    """
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
    return "".join(out) + text[done:]


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


def _is_local(ch: str) -> bool:
    return ch.isalnum() or ch in "_.+-"


def _is_label(ch: str) -> bool:
    return ch.isalnum() or ch in "_-"


def _domain_end(text: str, start: int) -> int:
    """Where the domain that starts at `start` ends (`label(.label)+`), or `start` if there is
    none."""
    pos = start
    labels = 0
    while True:
        end = pos
        while end < len(text) and _is_label(text[end]):
            end += 1
        if end == pos:
            break
        pos = end
        labels += 1
        if pos + 1 < len(text) and text[pos] == "." and _is_label(text[pos + 1]):
            pos += 1
            continue
        break
    return pos if labels >= 2 else start


def _word(tok: Tok) -> bool:
    return bool(tok.norm) and tok.norm not in AT and tok.norm not in JOIN


def _local_start(toks: Sequence[Tok], at: int, floor: int) -> int | None:
    """The token where the local part that ends just before `at` begins: one to three words,
    joined by `dot`, `punto`, `underscore` or `guion bajo`."""
    j = at - 1
    if j < floor or not _word(toks[j]):
        return None
    for _ in range(MAX_LOCAL_WORDS - 1):
        if j - 2 >= floor and toks[j - 1].norm in JOIN and _word(toks[j - 2]):
            j -= 2
        elif (
            j - 3 >= floor
            and toks[j - 1].norm == "bajo"
            and toks[j - 2].norm == "guion"
            and _word(toks[j - 3])
        ):
            j -= 3
        else:
            break
    return j


def _domain(toks: Sequence[Tok], first: int) -> tuple[int, str] | None:
    """The domain that starts at token `first`: its last token and its TLD. Either one token that
    holds it (`gmail.com`) or labels said with `dot`/`punto` (`gmail punto com`)."""
    if first >= len(toks):
        return None
    head = toks[first]
    dotted = head.core.rstrip(".").lower()
    if "." in dotted and _DOMAIN.fullmatch(dotted):
        labels = dotted.split(".")
        return (first, _tld_of(labels)) if labels[-1] in TLDS else None
    if not _label(head):
        return None
    best: tuple[int, str] | None = None
    last = first
    for _ in range(MAX_LABELS - 1):
        if last + 2 < len(toks) and toks[last + 1].norm in DOT and _label(toks[last + 2]):
            last += 2
            if toks[last].norm in TLDS:
                best = (last, _tld_of([toks[last - 2].norm, toks[last].norm]))
        else:
            break
    return best


def _label(tok: Tok) -> bool:
    return bool(tok.norm) and tok.norm not in AT and tok.norm not in DOT
