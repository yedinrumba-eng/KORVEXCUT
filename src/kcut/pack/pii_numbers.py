"""Numbers in what people say (spec 001.13, 001.16, 001.17): where they are and how they are masked.

A number is a run of tokens that take digits (`Tok.slots`): digits, digits said in words, tens,
hundreds, multipliers. Up to `MAX_BRIDGE` bridge tokens (a filler, `dash`, `y`...) may sit between
two groups of digits, and one or two lone `o` between them are zeros. A run of `MIN_DIGITS` digits
or more is PII.
"""

from collections.abc import Sequence

from kcut.pack.pii_tokens import Tok

MIN_DIGITS = 7  # a run this long is a phone, an ID number, a card or an account
KEEP_DIGITS = 2  # the last digits of a run that stay readable
MAX_BRIDGE = 4  # bridge tokens that may sit between two groups of digits (001.17, point 3)


def number_runs(toks: Sequence[Tok]) -> list[list[Tok]]:
    """Runs of neighbouring tokens that add up to `MIN_DIGITS` digits or more.

    A run starts and ends on a token with digits. Neutral tokens (a lone `-` or `,`, `double`) and
    the later words of a filler may sit inside it for free; bridge tokens cost one of the
    `MAX_BRIDGE`, and the digits on both sides count together. Deleted words are not in `toks`, so
    they neither bridge nor cut. The tokens of a run include its bridges and neutrals.
    """
    runs: list[list[Tok]] = []
    items: list[Tok] = []
    pending: list[Tok] = []  # neutral and bridge tokens since the last token with digits
    total = bridges = 0
    for tok in toks:
        if tok.slots:
            if items:
                lone = [p for p in pending if p.bridge]
                if 1 <= len(lone) <= 2 and all(p.norm == "o" and not p.joined for p in lone):
                    for zero in lone:  # "eight o nine", "five o o five": zeros
                        zero.slots, zero.shows = 1, "0"
                        total += 1
                items += pending
            items.append(tok)
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
        if total >= MIN_DIGITS:  # anything else, or a fifth bridge, ends the number
            runs.append(items)
        items, pending, total, bridges = [], [], 0, 0
    if total >= MIN_DIGITS:
        runs.append(items)
    return runs


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
