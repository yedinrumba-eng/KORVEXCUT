"""PII in numbers, round 5 (spec 001.17, points 3, 4 and 8): bridges, loose separators, vocabulary.

Fillers of several words count as one bridge, stretched letters are the same filler, a lone `,` or
`/` or dash between two groups does not cut the number, and the words that were missing (`una`,
`O O`, hundreds, hyphenated digit words) count. Collected from `test_pii.py`.
"""

from collections.abc import Sequence

import pytest

from kcut.pack.pii import mask_pii, mask_pii_spans
from kcut.transcribe.model import Word

__all__ = [
    "TestPiiAside",
    "TestPiiBridgeV2",
    "TestPiiLooseSeparator",
    "TestPiiRestart",
    "TestPiiVocabV2",
]


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
        assert _shown_v2("809 eh eh eh eh uh-huh 5551")[0] == "***"  # 001.20: five, an aside
        assert _shown_v2("809 " + "eh " * 6 + "uh-huh 5551")[0] == "809"  # 001.20: seven words

    def test_pii_bridge_v2_a_word_that_is_no_filler_is_an_aside(self) -> None:
        assert _shown_v2("809 555 hola 1234") == ["***", "***", "hola", "**34"]  # 001.18
        assert _shown_v2("809 555 you 1234")[0] == "***"  # 001.18: an aside of one word

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


class TestPiiAside:
    """001.18 point 2: fixed fillers that bridge in any language, and an aside of 1 to 3 words
    between two groups of 3 digits or more that reach 7 together. `mil` and `thousand` count."""

    @pytest.mark.parametrize("filler", ["uh", "um", "uhm", "er", "hmm", "eh", "em", "mmm", "ah"])
    def test_pii_aside_the_fixed_fillers_bridge_without_being_in_the_config(
        self, filler: str
    ) -> None:
        assert _shown_v2(f"809 555 {filler} 1234", ()) == ["***", "***", filler, "**34"]

    def test_pii_aside_the_fixed_fillers_stretched_still_bridge(self) -> None:
        assert _shown_v2("809 555 ummm 1234", ())[0] == "***"
        assert _shown_v2("809 555 hmmmm 1234", ())[0] == "***"

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            (
                "cinco cinco cinco um uno dos tres cuatro",
                ["*", "*", "*", "um", "*", "*", "3", "4"],
            ),
            (
                "five five five like zero one nine eight",
                ["*", "*", "*", "like", "*", "*", "9", "8"],
            ),
            (
                "cinco cinco cinco a ver uno dos tres cuatro",
                ["*", "*", "*", "a", "ver", "*", "*", "3", "4"],
            ),
            (
                "five five five. And then zero one nine eight",
                ["*", "*", "*.", "And", "then", "*", "*", "9", "8"],
            ),
        ],
    )
    def test_pii_aside_the_cases_of_the_spec(self, said: str, shown: list[str]) -> None:
        assert _shown_v2(said, ()) == shown

    @pytest.mark.parametrize(
        "aside",
        ["like", "you know", "perdón", "a ver", "y luego", "and then", "the last four are"],
    )
    def test_pii_aside_the_asides_of_the_spec_do_not_cut_the_number(self, aside: str) -> None:
        shown = _shown_v2(f"five five five {aside} zero one nine eight", ())
        assert shown[:3] == ["*", "*", "*"] and shown[-2:] == ["9", "8"]
        assert all(word in shown for word in aside.split() if word != "four")

    def test_pii_aside_needs_two_digits_on_each_side(self) -> None:
        assert _shown_v2("five five like zero one nine eight", ())[0] == "five"  # 2 + 4
        # 001.22: two digits are enough on a side now (MIN_SIDE = 2), so 5 + 2 reach seven
        assert _shown_v2("five five five five five like one two", ())[0] == "*"

    def test_pii_aside_the_two_groups_must_reach_seven(self) -> None:
        said = "five five five like one two three"  # 3 + 3
        assert _shown_v2(said, ()) == said.split(" ")

    def test_pii_aside_up_to_three_words_and_not_four(self) -> None:
        assert _shown_v2("five five five you know what zero one nine eight", ())[0] == "*"
        # 001.20: the limit is six words now; four are an aside, seven cut
        assert _shown_v2("five five five you know what is zero one nine eight", ())[0] == "*"
        seven = "five five five you know what is it that i zero one nine eight"
        assert _shown_v2(seven, ())[0] == "five"

    def test_pii_aside_a_time_or_a_code_is_not_a_word_and_still_cuts(self) -> None:
        assert _shown_v2("972 5:31 3211", ()) == ["972", "5:31", "3211"]
        assert _shown_v2("123 C21 4567", ()) == ["123", "C21", "4567"]

    def test_pii_aside_punctuation_alone_is_not_a_word(self) -> None:
        assert _shown_v2("809 ? 555 1234", ())[0] == "809"

    def test_pii_aside_the_false_positives_are_accepted(self) -> None:
        assert _shown_v2("555 a ver 1234", ()) == ["***", "a", "ver", "**34"]

    def test_pii_aside_mil_and_thousand_count_as_digits(self) -> None:
        assert _shown_v2("two thousand five five five one", ()) == ["*", "***", "*", "*", "5", "1"]
        assert _shown_v2("cinco mil uno dos tres cuatro", ()) == ["*", "***", "*", "*", "3", "4"]
        assert _shown_v2("two thousand", ()) == ["two", "thousand"]  # four digits: no PII
        assert _shown_v2("mil gracias", ()) == ["mil", "gracias"]


class TestPiiRestart:
    """001.18 point 3: a number started again. The first try (6 digits or more) that comes a few
    words before a masked number is masked too, and nothing of it stays readable."""

    def test_pii_restart_the_example_of_the_spec(self) -> None:
        said = (
            "ocho cero nueve cinco cinco cinco… no, perdón, "
            "ocho cero nueve cinco cinco cinco uno dos tres cuatro"
        )
        shown = _shown_v2(said, ())
        assert shown[:6] == ["*", "*", "*", "*", "*", "*..."]  # first try: nothing readable (NFKC)
        assert shown[6:8] == ["no,", "perdón,"]
        assert shown[8:] == ["*"] * 8 + ["3", "4"]

    def test_pii_restart_six_written_digits_before_a_complete_number(self) -> None:
        said = "809555 no perdon 8095551234"
        assert _shown_v2(said, ()) == ["******", "no", "perdon", "********34"]

    def test_pii_restart_with_a_short_group_in_between(self) -> None:
        said = "809555 no uno perdon 8095551234"
        assert _shown_v2(said, ()) == ["******", "no", "*", "perdon", "********34"]

    def test_pii_restart_four_words_away_is_another_sentence(self) -> None:
        said = "809555 no perdon de verdad 8095551234"  # 001.20: four words are an aside now
        assert _shown_v2(said, ()) == ["******", "no", "perdon", "de", "verdad", "********34"]
        seven = (
            "809555 no perdon de verdad si mira esto 8095551234"  # seven words: another sentence
        )
        assert _shown_v2(seven, ())[0] == "809555"

    def test_pii_restart_a_first_try_of_two_digits_is_masked_too(self) -> None:
        assert _shown_v2("55 no perdon 8095551234", ())[0] == "**"  # 001.22: MIN_SIDE = 2

    def test_pii_restart_three_tries_in_a_row(self) -> None:
        shown = _shown_v2("809555 no 809555 no perdon 8095551234", ())
        assert shown == ["******", "no", "******", "no", "perdon", "********34"]

    def test_pii_restart_ids_include_the_words_between_the_tries(self) -> None:
        words = _words("809555", "no", "perdon", "8095551234", "gracias")
        _, ids, inside = mask_pii_spans(words, ())
        assert ids == {"a1:w0000", "a1:w0003"}
        assert inside == {"a1:w0000", "a1:w0001", "a1:w0002", "a1:w0003"}
