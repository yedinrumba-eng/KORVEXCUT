"""PII in numbers said in words (spec 001.16, points 2 and 3): bridges, tens and multipliers.

A number is often said with a filler in the middle ("ocho cero nueve, eh, cinco cinco cinco"), with
tens ("twelve thirty four") or with a multiplier ("double five"). Each of those has to count its
real digits, or a phone number walks past the mask.
"""

from collections.abc import Sequence

import pytest

from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Word
from tests.unit.pii_cases_asides import (
    TestPiiAbsorbBackwards,
    TestPiiAsideV2,
    TestPiiAsideV2Transcript,
    TestPiiRestartV2,
)
from tests.unit.pii_cases_glued import TestPiiEmailGluedV2
from tests.unit.pii_cases_v5 import (  # 001.22: collected here, test_pii.py is at 300 lines
    TestPiiAsideV3,
    TestPiiEmailGluedNumber,
    TestPiiEmailV5Guion,
    TestPiiEmailV5Numbers,
    TestPiiEmailV5OpenTld,
)

__all__ = [
    "TestPiiAbsorbBackwards",
    "TestPiiAsideV2",
    "TestPiiAsideV2Transcript",
    "TestPiiAsideV3",
    "TestPiiBridge",
    "TestPiiEmailGluedNumber",
    "TestPiiEmailGluedV2",
    "TestPiiEmailV5Guion",
    "TestPiiEmailV5Numbers",
    "TestPiiEmailV5OpenTld",
    "TestPiiRestartV2",
    "TestPiiTens",
]
FILLERS = ("eh", "ehh", "em", "este", "o sea", "pues")


def _words(*texts: str) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(texts)]


def _shown(text: str, fillers: Sequence[str] = FILLERS) -> list[str]:
    return [w.text for w in mask_pii(_words(*text.split(" ")), fillers)[0]]


class TestPiiBridge:
    """Up to 2 bridge tokens between two groups of digits do not cut the number."""

    def test_pii_bridge_a_filler_between_groups_of_spoken_digits(self) -> None:
        said = "ocho cero nueve, eh, cinco cinco cinco, eh, uno dos tres cuatro"
        shown = _shown(said)
        assert shown == ["*", "*", "*,", "eh,", "*", "*", "*,", "eh,", "*", "*", "3", "4"]

    def test_pii_bridge_a_filler_between_groups_of_digits(self) -> None:
        assert _shown("809 555 eh 1234") == ["***", "***", "eh", "**34"]

    def test_pii_bridge_dash_and_guion_words(self) -> None:
        said = "eight zero nine dash five five five dash one two three four"
        assert _shown(said) == ["*", "*", "*", "dash", "*", "*", "*", "dash", "*", "*", "3", "4"]
        spanish = "ocho cero nueve guion cinco cinco cinco guion uno dos tres cuatro"
        assert _shown(spanish)[3] == "guion" and _shown(spanish)[-2:] == ["3", "4"]

    def test_pii_bridge_and_y_between_groups(self) -> None:
        assert _shown("123 y 4567") == ["***", "y", "**67"]
        assert _shown("123 and 4567") == ["***", "and", "**67"]

    def test_pii_bridge_o_is_a_zero_only_with_digits_on_both_sides(self) -> None:
        said = "eight O nine five five five one two three four"
        assert _shown(said) == ["*"] * 8 + ["3", "4"]
        assert _shown("ocho o nueve cinco cinco cinco uno dos tres cuatro")[1] == "*"
        assert _shown("o ocho cinco tres uno dos tres cuatro")[0] == "o"  # no digits before it

    def test_pii_bridge_o_with_nothing_after_it_stays_as_a_word(self) -> None:
        shown = _shown("eight nine five five five one two three o")
        assert shown[-1] == "o" and shown[:2] == ["*", "*"]

    def test_pii_bridge_four_tokens_are_the_limit(self) -> None:  # 001.17: it was two
        assert _shown("809 eh eh eh eh 5551") == ["***", "eh", "eh", "eh", "eh", "**51"]
        # 001.20: five or six words are an aside now (up to 6); seven cut the number
        assert _shown("809 eh eh eh eh eh 5551") == ["***", *["eh"] * 5, "**51"]
        assert _shown("809 " + "eh " * 7 + "5551")[0] == "809"

    def test_pii_bridge_a_two_word_filler_counts_as_one_token(self) -> None:  # 001.17: it was two
        assert _shown("809 o sea 5551234") == ["***", "o", "sea", "*****34"]
        assert _shown("809 o sea eh eh eh 5551")[1:5] == ["o", "sea", "eh", "eh"]  # four in all
        assert _shown("809 o sea eh eh eh eh 5551")[0] == "***"  # 001.20: five, an aside
        assert _shown("809 o sea eh eh eh eh eh 5551")[0] == "809"  # 001.20: seven words cut

    def test_pii_bridge_both_sides_must_bring_digits(self) -> None:
        assert _shown("eh 5551234 eh") == ["eh", "*****34", "eh"]
        assert _shown("eh eh 1234 eh 12") == ["eh", "eh", "1234", "eh", "12"]  # six digits

    def test_pii_bridge_the_total_must_reach_seven(self) -> None:
        assert _shown("123 eh 456") == ["123", "eh", "456"]
        assert _shown("123 eh 4567") == ["***", "eh", "**67"]

    def test_pii_bridge_a_leading_or_trailing_bridge_is_not_part_of_the_number(self) -> None:
        assert _shown("y 5551234 y") == ["y", "*****34", "y"]

    def test_pii_bridge_a_word_that_is_not_a_bridge_is_an_aside(self) -> None:
        assert _shown("809 hola 5551234") == ["***", "hola", "*****34"]  # 001.20
        assert _shown("809 uh 555 1234") == ["***", "uh", "***", "**34"]  # 001.18: fixed bridge

    def test_pii_bridge_the_fillers_come_from_the_config(self) -> None:
        assert _shown("809 uh 555 1234", fillers=("uh",)) == ["***", "uh", "***", "**34"]
        assert _shown("809 eh 555 1234", fillers=()) == ["***", "eh", "***", "**34"]  # 001.18

    def test_pii_bridge_two_numbers_an_aside_apart_are_one(self) -> None:
        assert _shown("123 hola 4567 y 890") == ["***", "hola", "****", "y", "*90"]  # 001.20

    def test_pii_bridge_two_years_joined_by_y_are_masked_the_price_of_the_rule(self) -> None:
        assert _shown("en 1990 y 2026") == ["en", "****", "y", "**26"]  # eight digits in all

    def test_pii_bridge_ids_are_the_digit_words_only(self) -> None:
        _, ids = mask_pii(_words("809", "eh", "555", "1234"), FILLERS)
        assert ids == {"a1:w0000", "a1:w0002", "a1:w0003"}

    def test_pii_bridge_a_deleted_word_is_not_a_bridge(self) -> None:
        shown, _ = mask_pii(_words("809", "", "eh", "", "eh", "5551234"), FILLERS)
        assert [w.text for w in shown] == ["***", "", "eh", "", "eh", "*****34"]


class TestPiiTens:
    """Tens, teens and multipliers count their real digits."""

    @pytest.mark.parametrize(
        "said",
        [
            "twelve thirty four",  # 12 34: four digits
            "doce treinta y cuatro",
            "double five",
            "triple cinco",
            "twenty twenty six",  # 20 26
            "las doce",
            "fifteen minutes",
            "once doce trece",  # six digits
        ],
    )
    def test_pii_tens_under_seven_digits_stay_as_they_are(self, said: str) -> None:
        assert _shown(said) == said.split(" ")

    def test_pii_tens_each_word_counts_its_digits(self) -> None:
        # 8 0 9 5 5 5 = six digits, twelve = 2, thirty four = 2: ten digits
        shown = _shown("eight oh nine five five five twelve thirty four")
        assert shown == ["*"] * 6 + ["**", "*", "*"]

    def test_pii_tens_in_spanish_with_y(self) -> None:
        shown = _shown("ocho cero nueve cinco cinco cinco doce treinta y cuatro")
        assert shown[6:] == ["**", "*", "y", "*"]

    def test_pii_tens_a_ten_alone_is_two_digits(self) -> None:
        assert _shown("twenty thirty forty fifty") == ["**", "**", "**", "**"]
        assert _shown("diez veinte treinta cuarenta") == ["**", "**", "**", "**"]

    def test_pii_tens_veinti_words_are_two_digits(self) -> None:
        assert _shown("veintiuno veintidos veintitres veinticuatro") == ["**"] * 4
        assert _shown("veintiun veinticinco veintiseis veintisiete") == ["**"] * 4

    def test_pii_tens_teens_are_two_digits(self) -> None:
        assert _shown("eleven twelve thirteen fourteen") == ["**"] * 4
        assert _shown("once doce trece catorce quince") == ["**"] * 5
        assert _shown("dieciseis diecisiete dieciocho diecinueve") == ["**"] * 4

    def test_pii_tens_a_tens_word_and_a_unit_are_two_digits_in_total(self) -> None:
        # thirty four = 34 (two digits), then five fives: seven digits
        assert _shown("thirty four five five five five five") == ["*"] * 5 + ["5", "5"]
        # as three digits it would be seven with the four below; it is six: nothing is masked
        assert _shown("thirty four 1 2 3 4") == ["thirty", "four", "1", "2", "3", "4"]

    def test_pii_tens_double_and_triple_count_twice_and_three_times(self) -> None:
        shown = _shown("double five one two three four five")  # 2 + 5 = 7
        assert shown == ["double", "**", "*", "*", "*", "4", "5"]
        assert _shown("triple cinco uno dos tres cuatro") == ["triple", "***", "*", "*", "3", "4"]

    def test_pii_tens_a_multiplier_without_a_digit_after_it_is_just_a_bridge(self) -> None:
        shown = _shown("five five five double eh one two three four")
        assert shown == ["*", "*", "*", "double", "eh", "*", "*", "3", "4"]

    def test_pii_tens_doble_in_spanish(self) -> None:
        assert _shown("ocho cero nueve doble cinco uno dos tres")[3:5] == ["doble", "**"]

    def test_pii_tens_words_in_a_sentence_are_left_alone(self) -> None:
        said = "tengo veinte anos y vivo en el piso doce desde hace quince anos"
        assert _shown(said) == said.split(" ")
