"""Numbers in what people say (spec 001.13, 001.16, 001.17, 001.18): where they are and how they
are masked.

A number is a run of tokens that take digits (`Tok.slots`): digits, digits said in words, tens,
hundreds, thousands, multipliers. Up to `MAX_BRIDGE` bridge tokens (a filler, `dash`, `y`...) may
sit between two groups of digits, and one or two lone `o` between them are zeros. A run of
`MIN_DIGITS` digits or more is PII. Groups of digits that a few words cut apart are one number
(001.18 points 2 and 3, read by the letter in 001.20): two groups of `MIN_SIDE` digits or more
that together reach `MIN_DIGITS`, with up to `MAX_ASIDE` words between them, whatever size each
one has. That covers a number said again after "no, perdón," (a restart): the first try is a group
of 3 or more next to a number of 7 or more.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self

from kcut.pack.pii_tokens import Tok

MIN_DIGITS = 7  # a run this long is a phone, an ID number, a card or an account
KEEP_DIGITS = 2  # the last digits of a run that stay readable
MAX_BRIDGE = 4  # bridge tokens that may sit between two groups of digits (001.17, point 3)
MAX_ASIDE = 6  # words of an aside between two groups of digits (001.18 point 2, 001.20)
MIN_SIDE = 3  # digits each group needs to take part in an aside: "five five like..." is no number


@dataclass(slots=True)
class _Group:
    """Neighbouring tokens from one with digits to another, bridges and neutrals between them."""

    items: list[Tok]
    total: int  # digits it takes
    first: int  # position in the list of tokens of its first token
    last: int  # position of its last token

    def absorb(self, gap: Sequence[Tok], other: Self) -> None:
        """Take the `gap` and the `other` group that follows into this one."""
        self.items += gap
        self.items += other.items
        self.total += other.total
        self.last = other.last


def number_runs(toks: Sequence[Tok]) -> list[list[Tok]]:
    """Runs of neighbouring tokens that add up to `MIN_DIGITS` digits or more.

    A run starts and ends on a token with digits. Neutral tokens (a lone `-` or `,`, `double`) and
    the later words of a filler may sit inside it for free; bridge tokens cost one of the
    `MAX_BRIDGE`, and the digits on both sides count together. Deleted words are not in `toks`,
    so they neither bridge nor cut. The tokens of a run include its bridges and neutrals.

    On top of that, groups of `MIN_SIDE` digits or more that an aside of 1 to `MAX_ASIDE` words
    cuts apart (see `_aside`) are one run when together they reach `MIN_DIGITS`, with no upper
    bound on either group: `809 a ver 5551234` and `4111 1111 1111 a ver 1111` are one number each,
    and so is a number started again ("... no, perdón, ocho cero nueve..."), whose first try is
    hidden whole. A group of `MIN_SIDE` digits or more up to `MAX_ASIDE` words before a number is
    part of it as well, however many come in a row (001.21, point 1). Everything that joins keeps
    the last `KEEP_DIGITS` digits of the whole.
    """
    groups = [group for group in _groups(toks) if group.total >= MIN_SIDE]
    joined = _asides(groups, toks)
    return [group.items for group in joined if group.total >= MIN_DIGITS]


def _groups(toks: Sequence[Tok]) -> list[_Group]:
    """Every group of digits, whatever its size: tokens with digits joined by neutrals and up to
    `MAX_BRIDGE` bridges."""
    groups: list[_Group] = []
    items: list[Tok] = []
    pending: list[Tok] = []  # neutral and bridge tokens since the last token with digits
    total = bridges = first = last = 0
    for at, tok in enumerate(toks):
        if tok.slots:
            if items:
                lone = [p for p in pending if p.bridge]
                if 1 <= len(lone) <= 2 and all(p.norm == "o" and not p.joined for p in lone):
                    for zero in lone:  # "eight o nine", "five o o five": zeros
                        zero.slots, zero.shows = 1, "0"
                        total += 1
                items += pending
            else:
                first = at
            items.append(tok)
            last = at
            pending = []
            total += tok.slots
            bridges = 0
            continue
        if tok.neutral or tok.cont:
            pending.append(tok)
            continue
        if tok.bridge and items:
            bridges += 1
            if bridges <= MAX_BRIDGE:
                pending.append(tok)
                continue
        if items:  # anything else, or a fifth bridge, ends the group
            groups.append(_Group(items, total, first, last))
        items, pending, total, bridges = [], [], 0, 0
    if items:
        groups.append(_Group(items, total, first, last))
    return groups


def _aside(gap: Sequence[Tok]) -> bool:
    """Is what sits between two groups of digits an aside: 1 to `MAX_ASIDE` words?

    A word has letters and no digits. Digits said inside the aside ("the last FOUR are") and
    tokens of only punctuation are free. A token with digits that is no number (`5:31`, `C21`) is
    not an aside: it cuts, as it always did.
    """
    words = 0
    for tok in gap:
        if tok.slots:
            continue
        if tok.digits:
            return False
        if tok.norm and not tok.neutral:
            words += 1
    return 1 <= words <= MAX_ASIDE


def _asides(groups: Sequence[_Group], toks: Sequence[Tok]) -> list[_Group]:
    """Join, left to right, two groups that an aside cuts apart: each has `MIN_SIDE` digits or
    more and together they reach `MIN_DIGITS`. A group that is already a number takes part too:
    the digits next to it are part of the same number (001.20, point 1). Then the same from right
    to left (`_absorb_backwards`), because the first pass cannot go back to a group it left behind:
    "305 like 555 like 0198" reads the same as "555 like 0198 like 305" (001.21, point 1)."""
    joined: list[_Group] = []
    for group in groups:
        if joined:
            before = joined[-1]
            gap = toks[before.last + 1 : group.first]
            if (
                before.total >= MIN_SIDE
                and group.total >= MIN_SIDE
                and before.total + group.total >= MIN_DIGITS
                and _aside(gap)
            ):
                before.absorb(gap, group)
                continue
        joined.append(group)
    while True:  # 001.21, point 1: then right to left, until nothing changes
        wider = _absorb_backwards(joined, toks)
        if len(wider) == len(joined):
            return wider
        joined = wider


def _absorb_backwards(joined: list[_Group], toks: Sequence[Tok]) -> list[_Group]:
    """One sweep from right to left: a group of `MIN_SIDE` digits or more up to `MAX_ASIDE` words
    BEFORE a number of `MIN_DIGITS` or more is part of it (001.21, point 1). The number grows as
    the sweep goes, so a chain of short groups is taken whole, but it grows only next to a number
    that is already there: it never starts one. One pass over the groups and over the gaps, and the
    groups are joined once at the end, so the cost stays linear."""
    glued = [False] * len(joined)  # glued[i]: group i-1 belongs to the number group i is in
    total = joined[-1].total if joined else 0  # digits of the number the sweep stands in
    for at in range(len(joined) - 1, 0, -1):
        before = joined[at - 1]
        if total >= MIN_DIGITS and _aside(toks[before.last + 1 : joined[at].first]):
            glued[at] = True
            total += before.total
        else:
            total = before.total
    if not any(glued):
        return joined
    wider: list[_Group] = []
    for at, group in enumerate(joined):
        if glued[at]:
            wider[-1].absorb(toks[wider[-1].last + 1 : group.first], group)
        else:
            wider.append(group)
    return wider


def mask_run(run: Sequence[Tok]) -> dict[int, str]:
    """Token uid -> its masked core, for each token with digits. Every digit but the last
    `KEEP_DIGITS` of the run becomes `*`; neutral and bridge tokens are left as they are."""
    keep_from = sum(tok.slots for tok in run) - KEEP_DIGITS
    seen = 0
    masked: dict[int, str] = {}
    for tok in run:
        if tok.slots:
            masked[tok.uid] = _mask_core(tok, seen, keep_from)
            seen += tok.slots
    return masked


def compose(group: Sequence[Tok], cores: dict[int, str]) -> str:
    """The text of one word from its tokens (several if it was hyphenated), masked cores in place
    of the cores that were masked."""
    return group[0].pre + "-".join(cores.get(t.uid, t.core) for t in group) + group[-1].post


def mask_lettered(tok: Tok) -> str | None:
    """A token with letters and `MIN_DIGITS` digits or more (`tel8095551234`): its digits are
    masked on their own, all but the last two. None for any other token."""
    if tok.numeric or tok.slots or tok.digits < MIN_DIGITS or not any(map(str.isalpha, tok.core)):
        return None
    return tok.pre + mask_digits(tok.core, 0, tok.digits - KEEP_DIGITS) + tok.post


def mask_digits(core: str, seen: int, keep_from: int) -> str:
    """`core` with each decimal digit turned into `*` unless it comes at `keep_from` or after;
    `seen` digits came before the core."""
    out: list[str] = []
    for ch in core:
        if ch.isdecimal():
            out.append(ch if seen >= keep_from else "*")
            seen += 1
        else:
            out.append(ch)
    return "".join(out)


def _mask_core(tok: Tok, seen: int, keep_from: int) -> str:
    if tok.numeric and tok.slots == tok.digits:
        return mask_digits(tok.core, seen, keep_from)
    if tok.numeric:  # `double 5`: one written digit that stands for two or three
        return "*" * tok.slots
    lead = tok.core[: len(tok.core) - len(tok.core.lstrip("()+-."))]  # "(nine)" keeps its parens
    trail = tok.core[len(tok.core.rstrip("()+-.")) :]
    if tok.slots == 1 and tok.shows:
        body = tok.shows if seen >= keep_from else "*"
    else:
        body = "*" * tok.slots  # tens, teens, hundreds and multiples are always hidden
    return lead + body + trail
