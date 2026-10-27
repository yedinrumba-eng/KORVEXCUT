"""Written e-mail addresses, `john.doe@gmail.com` in one word (spec 001.13, 001.21, 001.22, 001.23,
001.24): where they are in a text, how they are masked and what is left around them.

An address is the local part before an `@` and a domain of two or more labels after it, the last
one (the TLD) made only of letters. The whole address leaves as `<first letter>***@***.<tld>`.
What is not an address, before, between and after the addresses, goes through the numbers pass.
Scanning is linear: an `@` is looked at once, with a bounded look around it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

MASKED = "{first}***@***.{tld}"
TLDS = frozenset(
    {"com", "net", "org", "edu", "gov", "io", "co", "us", "do", "mx", "es", "info", "biz", "pr"}
    | {"uk", "ca", "cl", "dev", "app", "ai"}
    | {"ph", "au", "br", "jp", "de", "fr", "it", "nl"}  # 001.21
)
# `claro.com.do` ends in `.com.do`, not in `.do`; the same for the other second-level ones (001.21)
COMPOUND_TLDS = ("com.do", "net.do", "com.au", "co.uk", "com.mx", "com.br", "co.jp")


def masked_address(first_text: str, tld: str) -> str:
    """`<first letter or digit of the address>***@***.<tld>`."""
    return MASKED.format(first=next((ch for ch in first_text if ch.isalnum()), ""), tld=tld)


@dataclass(frozen=True)
class Written:
    """A text cut around its written addresses (001.24, point 1): `gaps` is what is not an
    address, before, between and after them (always one more than `addresses`, and a gap may be
    empty), and `addresses` is each address already masked."""

    gaps: tuple[str, ...]
    addresses: tuple[str, ...]

    def joined(self) -> str:
        """The text with each address masked and every gap as it was."""
        parts = [gap + address for gap, address in zip(self.gaps, self.addresses, strict=False)]
        return "".join(parts) + self.gaps[-1]


def mask_written(text: str) -> str | None:
    """`text` with each written address masked, or None if it holds none.

    An address is the local part (`\\w . + -`, maybe empty) before an `@` and a domain of two or
    more labels after it. The local part does not reach back over a previous address.
    """
    split = split_written(text)
    return None if split is None else split.joined()


def split_written(text: str) -> Written | None:
    """`text` cut around its written addresses: the masked addresses and every stretch that is
    not one, before, between and after them (001.22 point 6, 001.24 point 1). None if there is
    no address. Each stretch is what `mask_pii` passes through the numbers, in its position:
    `8095551234;juan@gmail.com`, `a@b.com;4111111111111111;c@d.org`."""
    found = _addresses(text)
    if not found:
        return None
    gaps: list[str] = []
    masked: list[str] = []
    done = 0  # text before this position is already in a gap or an address
    for start, at, end in found:
        gaps.append(text[done:start])
        tld = tld_of(text[at + 1 : end].lower().split("."))
        masked.append(MASKED.format(first=text[start:at][:1], tld=tld))
        done = end
    gaps.append(text[done:])
    return Written(tuple(gaps), tuple(masked))


def mask_bare_domains(text: str) -> str:
    """`text` with each `<local>@<letters>` that is left, an `@` with a local part before it and
    after it one label of two or more letters and nothing else, masked as `<first>***@***`.

    The domain has no TLD of the closed list, because a file extension cut it off
    (`pedro@gmail.mp4`) or because it is a folder (`pedro@gmail/`), and an address is an address
    anyway. A `-` or a `_` in the label does not stop it from being a word of letters
    (`pedro@mi-empresa`, `pedro@gmail_final`: 001.26, point 9). `logo@2x` and `lunes@10am` have a
    label with a digit in it: they are files, not addresses (001.25, point 15). Run it after
    `mask_written`, whose `***@***.tld` it leaves alone."""
    out: list[str] = []
    done = 0  # text before this position is already in `out`
    at = text.find("@")
    while at != -1:
        start = at
        while start > done and _is_local(text[start - 1]):
            start -= 1
        end = at + 1
        while end < len(text) and _is_label(text[end]):
            end += 1
        letters = text[at + 1 : end].replace("-", "").replace("_", "")
        if start < at and len(letters) >= 2 and letters.isalpha():
            out += [text[done:start], f"{text[start]}***@***"]
            done = end
        at = text.find("@", max(end, at + 1))
    out.append(text[done:])
    return "".join(out)


def last_at_is_open(text: str) -> bool:
    """Does `text` have an `@` that no written address in it covers, the last one? A name like
    `juan@gmail.com;pedro@gmail` has: what it lacks is the TLD that the file extension cut off
    (001.24, point 2)."""
    at = text.rfind("@")
    return at != -1 and not any(start <= at < end for start, _, end in _addresses(text))


def _addresses(text: str) -> list[tuple[int, int, int]]:
    """`(start, at, end)` of each written address of `text`, left to right: where its local part
    begins, where its `@` is and where its domain ends."""
    found: list[tuple[int, int, int]] = []
    done = 0  # text before this position belongs to a previous address or is left behind
    at = text.find("@")
    while at != -1:
        start = at
        while start > done and _is_local(text[start - 1]):
            start -= 1
        end = _domain_end(text, at + 1)
        if end > at + 1:
            found.append((start, at, end))
            done = end
            at = text.find("@", end)
        else:
            at = text.find("@", at + 1)
    return found


def tld_of(labels: Sequence[str]) -> str:
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
