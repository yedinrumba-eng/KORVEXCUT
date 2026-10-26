"""PII, step 0 of S1.5a (spec 001.22, points 2 to 6): what the last review of S1.4 left.

Said addresses with hundreds and thousands in the local part, `guion`, any word as the last label,
groups of 2 digits next to a number of 7 or more, and a number glued to a written address.
Collected from `test_pii.py` through `pii_cases_numbers.py`.
"""

import pytest

from kcut.pack.pii import mask_pii, mask_pii_spans
from kcut.transcribe.model import Word

__all__ = [
    "TestPiiAsideV3",
    "TestPiiEmailGluedNumber",
    "TestPiiEmailV5Guion",
    "TestPiiEmailV5Numbers",
    "TestPiiEmailV5OpenTld",
]


def _words(*texts: str) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(texts)]


def _spoken(text: str) -> list[str]:
    """What is left on the page: the shown words, without the ones masked down to nothing."""
    return [w.text for w in mask_pii(_words(*text.split(" ")))[0] if w.text]


def _shown(text: str) -> list[str]:
    return [w.text for w in mask_pii(_words(*text.split(" ")))[0]]


class TestPiiEmailV5Numbers:
    """001.22 point 2: hundreds and thousands said are numbers in the local part, like digits."""

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("juan mil novecientos ochenta y cinco arroba gmail punto com", "j***@***.com"),
            ("maria novecientos arroba gmail punto com", "m***@***.com"),
            ("john two hundred at gmail dot com", "j***@***.com"),
            ("ana doscientos arroba gmail punto com", "a***@***.com"),
            ("pedro cien arroba hotmail punto com", "p***@***.com"),
            ("lucia ciento veinte arroba gmail punto com", "l***@***.com"),
            ("bob one thousand nine hundred at gmail dot com", "b***@***.com"),
            ("sam thousand at gmail dot com", "s***@***.com"),
        ],
    )
    def test_pii_email_v5_numbers_hundreds_and_thousands_are_part_of_the_local_part(
        self, said: str, shown: str
    ) -> None:
        assert _spoken(said) == [shown]

    def test_pii_email_v5_numbers_the_name_in_front_is_not_left_behind(self) -> None:
        said = "mi correo es maria novecientos arroba gmail punto com ok"
        assert _spoken(said) == ["mi", "correo", "es", "m***@***.com", "ok"]

    def test_pii_email_v5_numbers_a_number_alone_is_the_local_part_and_a_lone_at_is_not(
        self,
    ) -> None:
        assert _spoken("novecientos arroba gmail punto com") == ["n***@***.com"]
        said = "novecientos pesos arroba gmail"  # no domain with a TLD: nothing is an address
        assert _spoken(said) == said.split(" ")

    def test_pii_email_v5_numbers_the_limit_of_twelve_digits_said_still_holds(self) -> None:
        said = "juan " + "mil " * 13 + "arroba gmail punto com"
        shown = _spoken(said)
        assert shown[-1].endswith("***@***.com") and "mil" in shown


class TestPiiEmailV5Guion:
    """001.22 point 3: `guion` (and `guión`) is the `-` said in Spanish and joins the local part."""

    @pytest.mark.parametrize(
        "said",
        [
            "maria guion gonzalez arroba hotmail punto com",
            "maria guión gonzalez arroba hotmail punto com",
            "Maria GUION Gonzalez arroba hotmail punto com",
        ],
    )
    def test_pii_email_v5_guion_joins_the_words_of_the_local_part(self, said: str) -> None:
        assert _spoken(said) == [said[0] + "***@***.com"]

    def test_pii_email_v5_guion_bajo_still_works_and_is_looked_at_first(self) -> None:
        said = "juan guion bajo perez arroba gmail punto com"
        assert _spoken(said) == ["j***@***.com"]
        assert _spoken("ana guion bajo luna guion diaz arroba gmail punto com") == ["a***@***.com"]

    def test_pii_email_v5_guion_the_words_around_it_are_not_seen(self) -> None:
        text = " ".join(_spoken("maria guion gonzalez arroba hotmail punto com"))
        assert "maria" not in text and "gonzalez" not in text and "hotmail" not in text

    def test_pii_email_v5_guion_alone_is_no_local_part(self) -> None:
        said = "guion arroba gmail punto com"
        assert _spoken(said) == said.split(" ")


class TestPiiEmailV5OpenTld:
    """001.22 point 4: after `at` and a domain said with `dot`, the last label is any word of 2 to
    24 letters. What is written keeps the closed list."""

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("maria arroba empresa punto store", "m***@***.store"),
            ("john at gmail dot me", "j***@***.me"),
            ("ops at fleet dot xyz", "o***@***.xyz"),
            ("info arroba miweb punto cr", "i***@***.cr"),
            ("ana arroba tienda punto com punto ar", "a***@***.com.ar"),
            ("ana at shop dot net dot nz", "a***@***.net.nz"),
            ("ana at uni dot edu dot co", "a***@***.edu.co"),
            ("ana arroba gobierno punto gob punto do", "a***@***.gob.do"),
            ("ana at mail dot Ñandú", "a***@***.nandu"),
            ("info at big apple trucking dot store", "i***@***.store"),
        ],
    )
    def test_pii_email_v5_open_tld_any_word_ends_the_address(self, said: str, shown: str) -> None:
        assert _spoken(said) == [shown]

    @pytest.mark.parametrize("tld", ["a", "x2", "abcdefghijklmnopqrstuvwxy", "2x", "1234"])
    def test_pii_email_v5_open_tld_it_has_to_be_two_to_twenty_four_letters(self, tld: str) -> None:
        said = f"ana at mail dot {tld}"
        assert _spoken(said) == said.split(" ")

    def test_pii_email_v5_open_tld_twenty_four_letters_are_the_most(self) -> None:
        assert _spoken("ana at mail dot " + "a" * 24) == ["a***@***." + "a" * 24]

    def test_pii_email_v5_open_tld_a_second_level_label_makes_both_show(self) -> None:
        assert _spoken("x at y dot com dot es") == ["x***@***.com.es"]  # two letters after `com`
        assert _spoken("x at y dot com dot abc") == ["x***@***.abc"]  # three do not

    def test_pii_email_v5_open_tld_written_domains_keep_the_closed_list(self) -> None:
        assert _spoken("john at gmail.xyz") == ["john", "at", "gmail.xyz"]
        assert _spoken("logo at 2x.png") == ["logo", "at", "2x.png"]
        assert _spoken("john at gmail.com") == ["j***@***.com"]

    def test_pii_email_v5_open_tld_the_next_sentence_is_not_swallowed(self) -> None:
        said = "john dot doe at gmail dot com juan punto perez arroba hotmail.com"
        assert _spoken(said) == ["j***@***.com", "j***@***.com"]

    def test_pii_email_v5_open_tld_the_words_of_the_address_are_all_hidden(self) -> None:
        words = _words("mail", "ops", "at", "fleet", "dot", "xyz", "ok")
        assert mask_pii(words)[1] == {f"a1:w{i:04d}" for i in range(1, 6)}
        assert mask_pii(words)[0][5].text == ""


class TestPiiAsideV3:
    """001.22 point 5: `MIN_SIDE` is 2. A group of 2 digits takes part in an aside, both going
    right and absorbing backwards; a group of 1 digit does not; 7 digits in all are still needed."""

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            (  # 3 + 4 reach seven; the 2 after them are part of the number
                "ocho cero nueve ya cinco cinco cinco uno ya dos tres",
                ["*", "*", "*", "ya", "*", "*", "*", "*", "ya", "2", "3"],
            ),
            ("809 ya 5551 ya 23", ["***", "ya", "****", "ya", "23"]),
            ("23 ya 5551 ya 809", ["**", "ya", "****", "ya", "*09"]),
            ("12 ya 345 ya 6789", ["**", "ya", "***", "ya", "**89"]),
            ("12 ya 34 ya 5551234", ["**", "ya", "**", "ya", "*****34"]),
        ],
    )
    def test_pii_aside_v3_a_group_of_two_digits_joins_a_number_of_seven(
        self, said: str, shown: list[str]
    ) -> None:
        assert _shown(said) == shown  # only the last two digits of the whole stay readable

    def test_pii_aside_v3_a_group_of_one_digit_still_stays_out(self) -> None:
        said = "seis, los otros son, cero nueve ocho cinco cinco cinco uno dos tres"
        shown = _shown(said)
        assert shown[0] == "seis," and shown[1:4] == ["los", "otros", "son,"]
        assert sum(ch.isdigit() for word in shown[4:] for ch in word) == 2

    def test_pii_aside_v3_a_chain_where_no_pair_reaches_seven_stays_visible_accepted_limit(
        self,
    ) -> None:
        """001.23 point 1: 3+2+3+2 with an aside between each piece has no pair that reaches 7, so
        the pair rule has nothing to hold on to. An accepted limit (debt 30), pinned here so that
        any change to it is noticed: without asides the pieces are joined as digits in a row."""
        for said in (
            "809 ya 55 ya 512 ya 34",
            "ocho cero nueve, ya, cinco cinco, ya, cinco uno dos, ya, tres cuatro",
            "199 ya 299 ya 399",  # a list of prices is no number
        ):
            assert _shown(said) == said.split(" "), said
        joined = _shown("809 55 512 34")
        assert sum(ch.isdigit() for word in joined for ch in word) == 2

    def test_pii_aside_v3_one_digit_next_to_a_number_does_not_join_it(self) -> None:
        assert _shown("8 ya 5551234")[0] == "8"
        assert _shown("5551234 ya 8")[-1] == "8"

    def test_pii_aside_v3_seven_digits_in_all_are_still_needed(self) -> None:
        for said in ("12 ya 345 ya 67", "80 ya 555 ya 12", "12 ya 3456"):
            assert _shown(said) == said.split(" "), said

    def test_pii_aside_v3_going_back_uses_the_same_minimum(self) -> None:
        shown = _shown("12 ya 34 ya 5551234")
        assert shown[0] == "**" and shown[2] == "**" and shown[-1] == "*****34"

    def test_pii_aside_v3_the_limit_of_six_words_holds_for_two_digits_too(self) -> None:
        six = _shown("12 a b c d e f 5551234")
        assert six[0] == "**"
        seven = "12 a b c d e f g 5551234"
        assert _shown(seven)[0] == "12"

    def test_pii_aside_v3_the_ids_of_a_two_digit_group_are_the_ones_of_the_number(self) -> None:
        _, ids, inside = mask_pii_spans(_words("12", "ya", "5551234"), ())
        assert ids == {"a1:w0000", "a1:w0002"} and inside == ids | {"a1:w0001"}


class TestPiiEmailGluedNumber:
    """001.22 point 6: what follows a written address in the same word goes through the numbers."""

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("juan@gmail.com;8095551234", "j***@***.com;********34"),
            ("juan@gmail.com/8095551234", "j***@***.com/********34"),
            ("juan@gmail.com;(809)555-1234", "j***@***.com;(***)***-**34"),
            ("juan@gmail.com,8095551234.", "j***@***.com,********34."),
        ],
    )
    def test_pii_email_glued_number_keeps_only_the_last_two_digits(
        self, said: str, shown: str
    ) -> None:
        assert _shown(said) == [shown]

    def test_pii_email_glued_number_no_digit_but_the_last_two_is_left_in_the_word(self) -> None:
        for said in ("juan@gmail.com;8095551234", "juan@gmail.com/8095551234"):
            text = _shown(said)[0]
            assert sum(ch.isdigit() for ch in text) == 2 and text.startswith("j***@***.com")

    def test_pii_email_glued_number_it_joins_the_words_that_follow(self) -> None:
        shown = _shown("juan@gmail.com;809 5551234 gracias")
        assert shown == ["j***@***.com;***", "*****34", "gracias"]

    def test_pii_email_glued_number_a_short_number_or_a_word_is_left_as_it_was(self) -> None:
        assert _shown("juan@gmail.com;123") == ["j***@***.com;123"]
        assert _shown("juan@gmail.com;gracias") == ["j***@***.com;gracias"]
        assert _shown("juan@gmail.com") == ["j***@***.com"]

    def test_pii_email_glued_number_letters_and_digits_after_the_address_are_masked(self) -> None:
        assert _shown("juan@gmail.com;tel8095551234") == ["j***@***.com;tel********34"]

    def test_pii_email_glued_number_ids_include_the_word_and_the_inside_set_too(self) -> None:
        shown, ids, inside = mask_pii_spans(_words("hola", "juan@gmail.com;8095551234"), ())
        assert ids == {"a1:w0001"} and inside == {"a1:w0001"}
        assert shown[1].text == "j***@***.com;********34"

    def test_pii_email_glued_number_two_addresses_and_a_number_in_one_word(self) -> None:
        text = _shown("a@b.com;c@d.org;8095551234")[0]
        assert text == "a***@***.com;c***@***.org;********34"
