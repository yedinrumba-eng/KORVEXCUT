"""`mask_pii` stays linear on a hostile transcript (spec 001.16, security finding BAJO 8).

A transcript can hold 36 100 words of 200 characters (the cap of the cache). Each word is analysed
once, so the time grows with the characters, not with their square: no regex backtracks, no word is
normalized twice.
"""

import time

import pytest

from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Word

HOSTILE = [
    "a" + "!" * 198 + "a",
    "!" * 200,
    "a" + " " * 198 + "a",
    "1" + "!" * 198 + "1",
    "@" + "a" * 199,
    "a@" * 100,
    "a." * 99 + "@",
    "a@" + "b." * 98 + "c",
    "a@b" * 66,
    "1" * 200,
    "1-" * 100,
    "1." * 100,
    "(1)" * 66,
    "a\n" * 66 + "!" * 66,
    "(" * 98 + "nine" + ")" * 98,
    "-" * 100 + "a" + "-" * 99,
    "—" * 100 + "7" + "—" * 99,
    "tel" + "8" * 197,
    "１" * 200,
    "." * 199 + "a",
]
WORDS = 36_100


def _transcript(texts: list[str], count: int = WORDS) -> list[Word]:
    return [
        Word(f"a1:w{i:05d}", i, texts[i % len(texts)], i * 10, i * 10 + 9, 0.9)
        for i in range(count)
    ]


@pytest.mark.slow
class TestPiiHostileLinear:
    def test_pii_hostile_36100_words_of_200_characters_in_under_20_seconds(self) -> None:
        words = _transcript(HOSTILE)
        started = time.monotonic()
        shown, _ = mask_pii(words, ("eh", "o sea"))
        elapsed = time.monotonic() - started
        assert len(shown) == WORDS and elapsed < 20.0, f"{elapsed:.1f} s"

    @pytest.mark.parametrize("text", HOSTILE, ids=[f"h{i}" for i in range(len(HOSTILE))])
    def test_pii_hostile_each_shape_alone_is_fast_too(self, text: str) -> None:
        words = _transcript([text], WORDS // 10)  # a tenth of the words: 2 s is already too much
        started = time.monotonic()
        mask_pii(words)
        assert time.monotonic() - started < 2.0

    def test_pii_hostile_a_long_run_of_numbers_and_bridges_is_linear(self) -> None:
        texts = ["809", "eh", "555", "eh", "1234", "y", "double", "five"]
        words = _transcript(texts)
        started = time.monotonic()
        shown, ids = mask_pii(words, ("eh",))
        assert (
            time.monotonic() - started < 20.0 and len(ids) > WORDS * 0.45
        )  # four words of every eight
        assert shown[0].text == "***"
