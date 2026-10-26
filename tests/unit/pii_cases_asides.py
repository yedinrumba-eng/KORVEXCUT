"""PII asides and restarts, round 2 (spec 001.20, points 1 and 2): 001.18 read by the letter.

Two groups of 3 digits or more that together reach 7 are one number when up to 6 words sit between
them, **whatever size each group has**: a number of 7 or more with a short group on either side
(`809 a ver 5551234`, `4111 1111 1111 a ver 1111`) is masked as one, and only its last two digits
stay readable. A group of 3 or more up to 6 words BEFORE a masked number is masked too (a restart).
Collected from `test_pii.py` through `pii_cases_numbers.py`.
"""

import time

import pytest

from kcut.pack import pii_numbers
from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Word

__all__ = ["TestPiiAbsorbBackwards", "TestPiiAsideV2", "TestPiiRestartV2"]


def _shown(text: str) -> list[str]:
    words = [
        Word(f"a1:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9)
        for i, t in enumerate(text.split(" "))
    ]
    return [w.text for w in mask_pii(words)[0]]


def _stars(count: int) -> list[str]:
    return ["*"] * count


class TestPiiAsideV2:
    def test_pii_aside_v2_the_limit_is_six_words(self) -> None:
        assert pii_numbers.MAX_ASIDE == 6

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            (  # 7 + aside + 3
                "ocho cero nueve cinco cinco cinco uno a ver dos tres cuatro",
                [*_stars(7), "a", "ver", "*", "3", "4"],
            ),
            ("4111 1111 1111 a ver 1111", ["****", "****", "****", "a", "ver", "**11"]),  # 12 + 4
            ("809 a ver 5551234", ["***", "a", "ver", "*****34"]),  # 3 + 7
            (
                "three oh five like five five five zero one nine eight",
                [*_stars(3), "like", *_stars(5), "9", "8"],
            ),
            (  # `cuatro` in the aside is a digit said, not a word: it is masked with the rest
                "809 555 y los ultimos cuatro son 1234",
                ["***", "***", "y", "los", "ultimos", "*", "son", "**34"],
            ),
        ],
    )
    def test_pii_aside_v2_the_cases_of_the_spec_leave_only_the_last_two_digits(
        self, said: str, shown: list[str]
    ) -> None:
        assert _shown(said) == shown

    def test_pii_aside_v2_a_long_group_on_either_side_takes_a_short_one_with_it(self) -> None:
        before = _shown("8095551 a ver 234")
        assert before[0] == "*******" and before[-1] == "*34"
        after = _shown("234 a ver 8095551")
        assert after[0] == "***" and after[-1] == "*****51"

    def test_pii_aside_v2_no_upper_bound_two_long_numbers_are_one(self) -> None:
        shown = _shown("4111 1111 1111 1111 a ver 5500 0000 0000 0004")
        assert shown[:4] == ["****"] * 4  # the first card is masked whole too
        assert shown[-1] == "**04" and shown[-2] == "****"

    def test_pii_aside_v2_up_to_six_words_and_not_seven(self) -> None:
        six = _shown("809 555 a b c d e f 1234")
        assert six[:2] == ["***", "***"] and six[-1] == "**34"
        seven = "809 555 a b c d e f g 1234"
        assert _shown(seven) == seven.split(" ")

    def test_pii_aside_v2_each_side_needs_two_digits(self) -> None:
        assert _shown("80 a ver 55512345")[0] == "**"  # 001.22: two digits take part now
        assert _shown("5551234 a ver 56")[-1] == "56"  # the last two digits stay readable
        assert _shown("8 a ver 55512345")[0] == "8"  # one digit alone does not

    def test_pii_aside_v2_numbers_that_are_too_short_together_stay_as_they_are(self) -> None:
        said = "555 a ver 123"  # 3 + 3
        assert _shown(said) == said.split(" ")

    def test_pii_aside_v2_a_time_or_a_code_still_cuts(self) -> None:
        assert _shown("972 5:31 3211") == ["972", "5:31", "3211"]
        assert _shown("123 C21 4567") == ["123", "C21", "4567"]


class TestPiiRestartV2:
    def test_pii_restart_v2_a_short_first_try_before_the_number_is_masked_too(self) -> None:
        said = (
            "ocho cero nueve cinco cinco no perdon "
            "ocho cero nueve cinco cinco cinco uno dos tres cuatro"
        )
        shown = _shown(said)
        assert shown[:5] == _stars(5) and shown[5:7] == ["no", "perdon"]
        assert "80955" not in "".join(shown) and shown[-2:] == ["3", "4"]

    def test_pii_restart_v2_with_the_commas_of_the_transcript(self) -> None:
        said = (
            "ocho cero nueve cinco cinco, no, perdon, "
            "ocho cero nueve cinco cinco cinco uno dos tres cuatro"
        )
        shown = _shown(said)
        assert shown[:5] == ["*", "*", "*", "*", "*,"]  # the first try: nothing readable

    @pytest.mark.parametrize("digits", ["809", "8095", "80955", "809555", "8095551"])
    def test_pii_restart_v2_three_digits_or_more_are_masked(self, digits: str) -> None:
        shown = _shown(f"{digits} no perdon 8095551234")
        assert shown[0] == "*" * len(digits)

    def test_pii_restart_v2_two_digits_are_enough(self) -> None:
        assert _shown("80 no perdon 8095551234")[0] == "**"  # 001.22: MIN_SIDE = 2
        assert _shown("8 no perdon 8095551234")[0] == "8"  # one digit is not

    def test_pii_restart_v2_six_words_between_and_not_seven(self) -> None:
        assert _shown("809 no no no no no no 8095551234")[0] == "***"
        assert _shown("809 no no no no no no no 8095551234")[0] == "809"

    def test_pii_restart_v2_three_tries_in_a_row(self) -> None:
        shown = _shown("809 no 8095 no perdon 80955 no 8095551234")
        assert shown[0] == "***" and shown[2] == "****" and shown[5] == "*****"
        assert shown[-1] == "********34"


class TestPiiAsideV2Transcript:
    def test_pii_aside_v2_numbers_two_words_apart_are_one_number_in_a_long_transcript(self) -> None:
        """The numbers of `test_pii_digits_a_long_transcript_is_masked_in_linear_time` are two
        words apart, so (001.20) the whole transcript is one number: the last two digits of the
        LAST one are all that stays readable."""
        said = "hola 972 808 3211 adios " * 40
        shown = _shown(said.strip())
        assert shown[:5] == ["hola", "***", "***", "****", "adios"]
        assert shown[-5:] == ["hola", "***", "***", "**11", "adios"]
        digits = [ch for token in shown for ch in token if ch.isdigit()]
        assert digits == ["1", "1"]


class TestPiiAbsorbBackwards:
    """001.21, point 1: a group of 3 digits or more up to 6 words BEFORE a masked number is part of
    it, whatever the order the groups were read in. The pass goes right to left, repeats until
    nothing changes, grows only next to a number that is already masked and never starts one."""

    def test_pii_absorb_backwards_a_restart_after_a_short_number_leaves_no_809(self) -> None:
        said = (
            "ocho cero nueve a ver cinco cinco cinco no perdon "
            "ocho cero nueve cinco cinco cinco uno dos tres cuatro"
        )
        shown = _shown(said)
        expected = [*_stars(3), "a", "ver", *_stars(3), "no", "perdon", *_stars(8), "3", "4"]
        assert shown == expected

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("305 like 555 like 0198", ["***", "like", "***", "like", "**98"]),
            ("555 like 0198 like 305", ["***", "like", "****", "like", "*05"]),
            (
                "three oh five um five five five um zero one nine eight",
                [*_stars(3), "um", *_stars(3), "um", *_stars(2), "9", "8"],
            ),
        ],
    )
    def test_pii_absorb_backwards_the_cases_of_the_verifier_keep_two_digits(
        self, said: str, shown: list[str]
    ) -> None:
        assert _shown(said) == shown

    def test_pii_absorb_backwards_repeats_until_nothing_changes(self) -> None:
        said = "100 a 200 a 300 a 400 a 5551234"
        shown = _shown(said)
        assert shown == ["***", "a", "***", "a", "***", "a", "***", "a", "*****34"]

    def test_pii_absorb_backwards_the_limit_is_six_words_between_each_pair(self) -> None:
        six = _shown("123 a b c d e f 123 a b c d e f 8095551234")
        assert six[0] == "***" and six[7] == "***" and six[-1] == "********34"
        seven = _shown("123 a b c d e f g 123 a b c d e f 8095551234")
        assert seven[0] == "123" and seven[8] == "***"

    def test_pii_absorb_backwards_never_starts_a_number(self) -> None:
        said = "305 like 555 like 019"  # 3 + 3 + 3: no pair reaches 7, nothing is masked
        assert _shown(said) == said.split(" ")

    def test_pii_absorb_backwards_a_group_of_two_digits_is_absorbed_too(self) -> None:
        assert _shown("80 like 555 like 0198")[0] == "**"  # 001.22: the same minimum as going right
        assert _shown("8 like 555 like 0198")[0] == "8"  # one digit alone is not a group

    def test_pii_absorb_backwards_a_time_or_a_code_still_cuts(self) -> None:
        assert _shown("305 5:31 5551234") == ["305", "5:31", "*****34"]

    def test_pii_absorb_backwards_a_chain_of_36100_words_is_fast_and_all_masked(self) -> None:
        texts = ["123", "pues", "bueno", "ya", "ves", "mira", "eso"] * 5150
        said = " ".join([*texts, "8095551234"])
        started = time.monotonic()
        shown = _shown(said)
        assert time.monotonic() - started < 2.0
        assert all(w == "***" for w in shown[0 : len(texts) : 7])
        assert shown[-1] == "********34"
