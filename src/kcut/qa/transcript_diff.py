"""What the render says against what the cut keeps (spec S1.9a, 001.15 and T2).

`diff_transcript` is pure. The expected words are ALL the words the cut keeps (`kept_words().words`,
raw: also the ones a graphic covers, because the check listens to the audio and a word under a title
is still said). The heard words are what Whisper wrote for the audio of the render. Both sides go
through `norm_token`, tokens that end up empty (a pause mark, a dash) are dropped, and each token
remembers the word it came from. `difflib.SequenceMatcher(autojunk=False)` compares them: with
`autojunk` a word said many times would be taken for noise and ignored.

T2: `match` is the ratio of that raw comparison. The texts that go in the report come from the
masked lists, never from the raw ones: `shown` (what Claude reads of each kept word) and
`heard_shown` (`mask_pii` over the WHOLE list of heard words, in the order of `heard`). A word that
is `""` there (an address swallowed it) adds nothing to the text. The heard text of a stretch that
touches a masked expected word is `HIDDEN_HEARD` (001.43).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from kcut.edl.words import KeptWord
from kcut.qa.report import Check
from kcut.text.normalize import norm_token
from kcut.timebase import fmt_tc
from kcut.transcribe.model import Word

MATCH_DECIMALS = 4
HIDDEN_HEARD = "[tapado]"  # `heard` of a stretch that touches a masked expected word (001.43)


@dataclass(frozen=True)
class DiffItem:
    """One difference: `op` is `replace`, `delete` (expected, not heard) or `insert` (heard, not
    expected); `expected` and `heard` are the MASKED texts of that stretch; `at_f` is the output
    frame of its first expected word, or where the expected word before it ends for an insert (0
    at the start)."""

    op: str
    expected: str
    heard: str
    at_f: int


@dataclass(frozen=True)
class TranscriptDiff:
    ratio: float
    expected_words: int
    heard_words: int
    items: tuple[DiffItem, ...]


def diff_transcript(
    expected: Sequence[KeptWord],
    shown: Mapping[str, str],
    heard: Sequence[Word],
    heard_shown: Sequence[str],
) -> TranscriptDiff:
    """Compare `expected` with `heard`. `shown` is the masked text of each expected word by id and
    `heard_shown` the masked text of each heard word (same length and order as `heard`)."""
    if len(heard_shown) != len(heard):
        raise ValueError("heard_shown tiene que tener un texto por cada palabra oída")
    wanted = _tokens([word.text for word in expected])
    listened = _tokens([word.text for word in heard])
    matcher = SequenceMatcher(
        None, [t for t, _ in wanted], [t for t, _ in listened], autojunk=False
    )
    items: list[DiffItem] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        words = _unique([at for _, at in wanted[i1:i2]])
        heard_at = _unique([at for _, at in listened[j1:j2]])
        near = [at for _, at in wanted[max(i1 - 1, 0) : i2 + 1]]  # the stretch and its two sides
        items.append(
            DiffItem(
                op=tag,
                expected=_join(shown.get(expected[at].id, "") for at in words),
                heard=_heard_text(tag, [heard_shown[at] for at in heard_at], expected, near, shown),
                at_f=_position(expected, words, wanted, i1),
            )
        )
    return TranscriptDiff(matcher.ratio(), len(wanted), len(listened), tuple(items))


def transcript_check(diff: TranscriptDiff, min_match: float, language: str, fps: int) -> Check:
    """The check `transcript`: it passes if the ratio reaches `min_match`. `fps` is only for the
    `at_display` of each difference."""
    listed: list[object] = [
        {
            "op": item.op,
            "expected": item.expected,
            "heard": item.heard,
            "at_f": item.at_f,
            "at_display": fmt_tc(item.at_f, fps),
        }
        for item in diff.items
    ]
    data: dict[str, object] = {
        "match": round(diff.ratio, MATCH_DECIMALS),
        "min": min_match,
        "language": language,
        "expected_words": diff.expected_words,
        "heard_words": diff.heard_words,
        "diffs": listed,
    }
    return Check("transcript", "pass" if diff.ratio >= min_match else "fail", data)


def _tokens(texts: Sequence[str]) -> list[tuple[str, int]]:
    """`(norm_token(text), index of the word)` for every word whose token is not empty."""
    found = [(norm_token(text), at) for at, text in enumerate(texts)]
    return [(token, at) for token, at in found if token]


def _heard_text(
    op: str,
    texts: Sequence[str],
    expected: Sequence[KeptWord],
    near: Sequence[int],
    shown: Mapping[str, str],
) -> str:
    """What a stretch shows as heard: `HIDDEN_HEARD` for a `replace` or an `insert` if one of the
    expected words in `near` (the stretch and the word right before and right after it) is masked
    (001.43, point 3). The masked side knows the clip's context and the heard side does not, so a
    cut that splits a number could leave a piece of it raw."""
    if op != "delete" and any(shown.get(expected[at].id, "") != expected[at].text for at in near):
        return HIDDEN_HEARD
    return _join(texts)


def _unique(indexes: Sequence[int]) -> list[int]:
    """The indexes without repeats, in order (a word is one token, but be safe)."""
    return list(dict.fromkeys(indexes))


def _join(texts: Iterable[str]) -> str:
    """The texts joined with a space, without the empty ones."""
    return " ".join(text for text in texts if text)


def _position(
    expected: Sequence[KeptWord], words: list[int], wanted: list[tuple[str, int]], i1: int
) -> int:
    """The output frame of a difference: the start of its first expected word; for an insert, the
    end of the expected word right before it (0 if it comes before every word)."""
    if words:
        return expected[words[0]].out_s_f
    if i1 > 0:
        return expected[wanted[i1 - 1][1]].out_e_f
    return 0
