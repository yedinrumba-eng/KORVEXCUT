"""PII in numbers, round 5 (spec 001.17, points 3, 4 and 8): bridges, loose separators, vocabulary.

Fillers of several words count as one bridge, stretched letters are the same filler, a lone `,` or
`/` or dash between two groups does not cut the number, and the words that were missing (`una`,
`O O`, hundreds, hyphenated digit words) count. Collected from `test_pii.py`.
"""

from collections.abc import Sequence

import pytest

from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Word

__all__ = ["TestPiiBridgeV2", "TestPiiLooseSeparator", "TestPiiVocabV2"]


def _words(*texts: str) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(texts)]


FILLERS_V2 = ("uh", "um", "eh", "o sea", "you know", "uh huh", "mmm")


def _shown_v2(text: str, fillers: Sequence[str] = FILLERS_V2) -> list[str]:
    return [w.text for w in mask_pii(_words(*text.split(" ")), fillers)[0]]


class TestPiiBridgeV2:
    """001.17 point 3: a filler of several words is ONE bridge, stretched letters are the same
    filler, and four bridges may sit between two groups of digits."""

    @pytest.mark.parametrize(
        "said",
        [
            "809 555 uh um eh 1234",
            "809 555 eh o sea 1234",
            "809 555 you know 1234",
            "809 555 ummm 1234",
            "809 555 uh-huh 1234",
            "809 555 mm 1234",
        ],
    )
    def test_pii_bridge_v2_these_fillers_do_not_cut_the_number(self, said: str) -> None:
        shown = _shown_v2(said)
        assert shown[0] == "***" and shown[-1] == "**34", shown

    def test_pii_bridge_v2_the_example_of_the_spec(self) -> None:
        said = "ocho cero nueve éh cinco cinco cinco ehhh uno dos tres cuatro"
        assert _shown_v2(said) == ["*", "*", "*", "éh", "*", "*", "*", "ehhh", "*", "*", "3", "4"]

    def test_pii_bridge_v2_a_filler_of_several_words_costs_one(self) -> None:
        # o sea (1) + you know (1) + eh eh (2) = four bridges: still one number
        assert _shown_v2("809 o sea you know eh eh 5551")[0] == "***"
        # one more eh makes five
        assert _shown_v2("809 o sea you know eh eh eh 5551")[0] == "809"

    def test_pii_bridge_v2_stretched_letters_collapse_before_comparing(self) -> None:
        for stretched in ("ehhh", "ehhhhh", "uhhh", "ummmm", "EHH"):
            assert _shown_v2(f"809 {stretched} 5551")[0] == "***", stretched

    def test_pii_bridge_v2_a_hyphenated_filler_is_one_bridge(self) -> None:
        shown = _shown_v2("809 eh eh eh uh-huh 5551")  # 3 + 1 = four
        assert shown[0] == "***" and shown[4] == "uh-huh"
        assert _shown_v2("809 eh eh eh eh uh-huh 5551")[0] == "809"  # five

    def test_pii_bridge_v2_a_word_that_is_no_filler_still_cuts(self) -> None:
        assert _shown_v2("809 555 hola 1234") == ["809", "555", "hola", "1234"]
        assert _shown_v2("809 555 you 1234")[0] == "809"  # half of "you know" is not a filler

    def test_pii_bridge_v2_digits_are_still_needed_on_both_sides_and_seven_in_all(self) -> None:
        assert _shown_v2("uh um eh 5551234 uh um")[3] == "*****34"
        assert _shown_v2("uh um 555 uh um eh 123") == ["uh", "um", "555", "uh", "um", "eh", "123"]

    def test_pii_bridge_v2_the_words_of_o_sea_are_not_zeros(self) -> None:
        shown = _shown_v2("809 o sea 5551")
        assert shown[1:3] == ["o", "sea"] and shown[3] == "**51"


class TestPiiLooseSeparator:
    """001.17 point 4: `, / _ – — …` alone between groups are neutral: they neither cut the number
    nor count as a bridge."""

    @pytest.mark.parametrize("sep", [",", "/", "_", "–", "—", "…", "-", ".", ",,"])
    def test_pii_loose_separator_does_not_cut(self, sep: str) -> None:
        assert _shown_v2(f"809 {sep} 555 {sep} 1234") == ["***", sep, "***", sep, "**34"]

    def test_pii_loose_separator_the_cases_of_the_spec(self) -> None:
        assert _shown_v2("809 — 555 — 1234")[0] == "***"
        assert _shown_v2("809 / 555 / 1234")[0] == "***"
        assert _shown_v2("809 , 555 , 1234")[0] == "***"

    def test_pii_loose_separator_is_not_a_bridge(self) -> None:
        # four fillers and five separators: the separators do not count against the four
        said = "809 , eh , eh , eh , eh , 5551"
        assert _shown_v2(said)[0] == "***"

    def test_pii_loose_separator_outside_a_number_masks_nothing(self) -> None:
        assert _shown_v2(", / — …") == [",", "/", "—", "…"]
        assert _shown_v2("809 , 555") == ["809", ",", "555"]

    def test_pii_loose_separator_other_punctuation_still_cuts(self) -> None:
        assert _shown_v2("809 ? 555 1234")[0] == "809"
        assert _shown_v2("809 ! 5551234")[0] == "809"


class TestPiiVocabV2:
    """001.17 point 8: the words that were missing."""

    def test_pii_vocab_v2_una_is_one(self) -> None:
        assert _shown_v2("cinco cinco cinco una dos tres cuatro") == ["*"] * 5 + ["3", "4"]

    def test_pii_vocab_v2_two_o_in_a_row_are_two_zeros(self) -> None:
        # five, O, O, five, one two three: 1 + 2 + 1 + 3 = seven digits
        assert _shown_v2("five O O five one two three") == ["*"] * 5 + ["2", "3"]
        assert _shown_v2("ocho o o nueve cinco cinco cinco")[1:3] == ["*", "*"]

    def test_pii_vocab_v2_three_o_are_not_zeros(self) -> None:
        assert _shown_v2("five o o o five one two three")[0] == "five"

    def test_pii_vocab_v2_digit_words_joined_with_hyphens_are_split(self) -> None:
        assert _shown_v2("five-five-five-one-two-three-four") == ["*-*-*-*-*-3-4"]
        assert _shown_v2("(five-five-five)-one-two-three-four.") == ["(*-*-*)-*-*-3-4."]
        assert _shown_v2("cinco-cinco-cinco-uno-dos-tres-cuatro,") == ["*-*-*-*-*-3-4,"]

    def test_pii_vocab_v2_hyphenated_pieces_join_the_words_around_them(self) -> None:
        assert _shown_v2("five-five-five one-two-three-four") == ["*-*-*", "*-*-3-4"]
        assert _shown_v2("eight five-five-five-one-two-three") == ["*", "*-*-*-*-2-3"]

    def test_pii_vocab_v2_a_hyphenated_word_that_is_not_a_number_is_left_alone(self) -> None:
        assert _shown_v2("well-known five-hello-six") == ["well-known", "five-hello-six"]

    @pytest.mark.parametrize(
        ("said", "stars"),
        [
            ("two hundred", 3),
            ("hundred", 3),
            ("cien", 3),
            ("ciento", 3),
            ("doscientos", 3),
            ("novecientos", 3),
        ],
    )
    def test_pii_vocab_v2_hundreds_count_three_digits(self, said: str, stars: int) -> None:
        # three digits, plus four ones: seven in all, and the hundreds are always hidden
        shown = _shown_v2(f"{said} one one one one")
        assert shown == [
            *(["*" * stars] if len(said.split()) == 1 else ["*", "**"]),
            "*",
            "*",
            "1",
            "1",
        ]

    def test_pii_vocab_v2_hundreds_alone_are_not_enough(self) -> None:
        assert _shown_v2("two hundred") == ["two", "hundred"]
        assert _shown_v2("ochocientos") == ["ochocientos"]

    def test_pii_vocab_v2_double_and_triple_before_a_written_digit(self) -> None:
        assert _shown_v2("double 5 5 5 1 2 3") == ["double", "**", "*", "*", "*", "2", "3"]
        assert _shown_v2("triple 5 1 2 3 4") == ["triple", "***", "*", "*", "3", "4"]

    def test_pii_vocab_v2_double_before_two_digits_is_only_a_bridge(self) -> None:
        assert _shown_v2("double 55 12 3456") == ["double", "**", "**", "**56"]
