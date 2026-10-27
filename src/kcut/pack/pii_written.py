"""Written e-mail addresses, `john.doe@gmail.com` in one word (spec 001.13, 001.21, 001.22, 001.23,
001.24): where they are in a text, how they are masked and what is left around them.

An address is the local part before an `@` and a domain of two or more labels after it, the last
one (the TLD) made only of letters. The whole address leaves as `<first letter>***@***.<tld>`.
What is not an address, before, between and after the addresses, goes through the numbers pass.
Scanning is linear: an `@` is looked at once, with a bounded look around it, and what follows it in
its stretch of a path is read once for all the `@` of that stretch (`mask_bare_domains`, 001.31).
"""

import re
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

MASKED = "{first}***@***.{tld}"
_PHONE_RUN = re.compile(r"\d{7}")  # the shortest run of digits that is taken for a phone number
_PHONE_DIGITS = 7
# a file extension: a dot and up to 5 letters or digits, one of them a letter (`.mp4`, not `.5551`)
_FILE_EXT = re.compile(r"\.(?=[A-Za-z0-9]{0,4}[A-Za-z])[A-Za-z0-9]{1,5}$")
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
    (`pedro@mi-empresa`, `pedro@gmail_final`: 001.26, point 9). So is a label whose first 3
    characters are letters, whatever follows: `pedro@gmail_2026`, `pedro@empresa-v2`,
    `pedro@hotmail2` and `pedro@gmail-8095551234` are addresses with the suffix of a file name
    (001.27, point 7). So is a label whose first stretch, up to the first `-` or `_`, is 2 letters
    or more: `pedro@yo-2026` and `pedro@yo-8095551234` (001.28, point 4). So is a label with 7
    digits in a row, a phone number, even after one letter: `pedro@g-8095551234` (001.30, point
    5). So is anything that has 7 digits in a row from the `@` to the end of that stretch of the
    path (without the extension, if it is the file name), where only a letter or an `@` cuts the
    run and any other character, a hyphen or a `~` or a parenthesis, sits between the digits:
    `pedro@g-809-555-1234`, `pedro@g.8095551234`, `pedro@g-809~555~1234` and the date
    `foto@2026-10-27` (001.31, point 7; 001.32, point 3); all of it up to there is masked.
    `logo@2x`, `lunes@10am` and `foto@v2` do not: they are files, not addresses (001.25, point
    15). The price is a `clip@take3` that is masked too; Claude still sees the id of the clip.
    Run it after `mask_written`, whose `***@***.tld` it leaves alone."""
    out: list[str] = []
    done = 0  # text before this position is already in `out`
    stretch: _Stretch | None = None
    at = text.find("@")
    while at != -1:
        start = at
        while start > done and _is_local(text[start - 1]):
            start -= 1
        end = at + 1
        while end < len(text) and _is_label(text[end]):
            end += 1
        if start < at:
            stop = end if _looks_like_domain(text[at + 1 : end]) else -1
            if stop == -1:
                if stretch is None or at >= stretch.limit:
                    stretch = _stretch(text, at + 1)  # once for each stretch: it stays linear
                if stretch.phone_from > at:
                    stop = stretch.name_end
            if stop != -1:
                out += [text[done:start], f"{text[start]}***@***"]
                done = end = stop
        at = text.find("@", max(end, at + 1))
    out.append(text[done:])
    return "".join(out)


@dataclass(frozen=True)
class _Stretch:
    """What follows an `@` in its stretch of the path: `limit` is where the stretch ends (a `/` or
    the end of the text), `name_end` where the name ends (`limit`, less the extension if it is the
    file name) and `phone_from` the last position that 7 digits in a row, through the separators,
    still follow (-1 if none): there is a phone number after an `@` if `phone_from` is after it."""

    limit: int
    name_end: int
    phone_from: int


def _stretch(text: str, begin: int) -> _Stretch:
    """The `_Stretch` that begins at `begin`, the position after an `@`. One pass over it.

    A run of digits is broken only by a letter or an `@` (so it never goes across an `@`): any
    other character does not break it (001.32, point 3), because a name can put anything between
    the digits of a phone number. `phone_from` is where the first of the last 7 digits of the
    longest run is, because that is the farthest right an `@` can be and still have 7 digits
    after it."""
    found = text.find("/", begin)
    limit = len(text) if found == -1 else found
    name_end = limit
    if found == -1:  # the last stretch is the file name: its extension is not counted
        ext = _FILE_EXT.search(text, begin, limit)
        name_end = limit if ext is None else ext.start()
    run: deque[int] = deque(maxlen=_PHONE_DIGITS)
    phone_from = -1
    for i in range(begin, name_end):
        ch = text[i]
        if ch.isdecimal():
            run.append(i)
            if len(run) == _PHONE_DIGITS:
                phone_from = run[0]
        elif ch.isalpha() or ch == "@":
            run.clear()
    return _Stretch(limit, name_end, phone_from)


def _looks_like_domain(label: str) -> bool:
    """Is `label`, what follows an `@` in a file name, the start of a domain and not of a file?
    Yes if it is only letters besides `-` and `_` (`mi-empresa`), if its first 3 characters are
    letters (`gmail_2026`, `hotmail2`: 001.27, point 7), if its first stretch, up to the first
    `-` or `_`, is 2 letters or more (`yo-2026`: 001.28, point 4) or if it carries a phone number,
    7 digits in a row, even after a single letter (`g-8095551234`: 001.30, point 5)."""
    letters = label.replace("-", "").replace("_", "")
    head = label.replace("_", "-").split("-", 1)[0]
    return (
        (len(letters) >= 2 and letters.isalpha())
        or (len(label) >= 3 and label[:3].isalpha())
        or (len(head) >= 2 and head.isalpha())
        or _PHONE_RUN.search(label) is not None
    )


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
