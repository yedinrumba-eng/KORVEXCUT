"""PII hidden behind Unicode digits and separators (spec 001.16, point 5).

Every token is folded with NFKC; a digit is anything `str.isdecimal()` calls one; `, / _ – —` and
NBSP inside a token do not cut a number; a token with letters and 7 digits or more loses its digits.
"""

import unicodedata

import pytest

from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Word

__all__ = ["TestPiiUnicode", "TestPiiVocabV2Format"]
NBSP = " "


def _words(*texts: str) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(texts)]


def _shown(text: str) -> list[str]:
    return [w.text for w in mask_pii(_words(*text.split(" ")))[0]]


class TestPiiUnicode:
    @pytest.mark.parametrize(
        ("raw", "shown"),
        [
            ("٨٠٩٥٥٥١٢٣٤", "*" * 8 + "٣٤"),
            ("८०९५५५१२३४", "*" * 8 + "३४"),
            ("８０９５５５１２３４", "*" * 8 + "34"),
            ("⁸⁰⁹⁵⁵⁵¹²³⁴", "*" * 8 + "34"),
        ],
        ids=["arabic_indic", "devanagari", "fullwidth", "superscript"],
    )  # fmt: skip
    def test_pii_unicode_digits_count_and_are_folded(self, raw: str, shown: str) -> None:
        assert _shown(raw) == [shown]

    def test_pii_unicode_digits_split_in_words_join_like_ascii_ones(self) -> None:
        assert _shown("８０９ ٥٥٥ 1234") == ["***", "***", "**34"]

    def test_pii_unicode_fullwidth_letters_are_folded_before_they_are_read(self) -> None:
        words = "ｎｉｎｅ ｓｅｖｅｎ ｔｗｏ ｅｉｇｈｔ ｚｅｒｏ ｅｉｇｈｔ ｔｈｒｅｅ"
        assert _shown(words) == ["*", "*", "*", "*", "*", "8", "3"]

    @pytest.mark.parametrize(
        ("raw", "shown"),
        [
            ("809,555,1234", "***,***,**34"),
            ("809/555/1234", "***/***/**34"),
            ("809_555_1234", "***_***_**34"),
            ("809–555–1234", "***–***–**34"),
            ("809—555—1234", "***—***—**34"),
            (f"809{NBSP}555{NBSP}1234", "*** *** **34"),  # NFKC: a NBSP becomes a plain space
            ("1,234,567", "*,***,*67"),
        ],
        ids=["comma", "slash", "underscore", "en_dash", "em_dash", "nbsp", "thousands"],
    )
    def test_pii_unicode_separators_inside_a_token_do_not_cut_the_number(
        self, raw: str, shown: str
    ) -> None:
        assert _shown(raw) == [shown]

    def test_pii_unicode_separators_at_the_edges_stay_where_they_are(self) -> None:
        assert _shown("¿8095551234?") == ["¿********34?"]
        assert _shown("8095551234,") == ["********34,"]
        assert _shown("8095551234—") == ["********34—"]

    @pytest.mark.parametrize(
        ("raw", "shown"),
        [
            ("tel8095551234", "tel********34"),
            ("tel:8095551234", "tel:********34"),
            ("Ext8095551234x", "Ext********34x"),
            ("B1234567", "B*****67"),
            ("abc1234567def", "abc*****67def"),
        ],
    )
    def test_pii_unicode_a_token_with_letters_and_seven_digits_loses_its_digits(
        self, raw: str, shown: str
    ) -> None:
        assert _shown(raw) == [shown]

    @pytest.mark.parametrize(
        "raw", ["C21", "A123456", "tel809", "5:31", "12:54", "v1.2.3", "ISO9001", "a1b2c3d"]
    )
    def test_pii_unicode_a_token_with_letters_and_fewer_than_seven_digits_is_left_alone(
        self, raw: str
    ) -> None:
        assert _shown(raw) == [raw]

    def test_pii_unicode_a_token_with_letters_does_not_join_the_numbers_around_it(self) -> None:
        assert _shown("123 C21 4567") == ["123", "C21", "4567"]

    def test_pii_unicode_a_written_address_with_a_fullwidth_at(self) -> None:
        assert _shown("john＠gmail.com") == ["j***@***.com"]

    def test_pii_unicode_ids_include_the_lettered_token(self) -> None:
        _, ids = mask_pii(_words("llama", "tel8095551234", "ya"))
        assert ids == {"a1:w0001"}

    def test_pii_unicode_masking_twice_changes_nothing(self) -> None:
        once, _ = mask_pii(_words("tel8095551234", "８０９５５５１２"))
        assert mask_pii(once)[0] == once


class TestPiiVocabV2Format:
    """001.17 point 8: format characters (Cf: ZWSP, joiners, bidi marks) are dropped before reading,
    and NFKC looks at no more than 64 characters of a word (point 9)."""

    @pytest.mark.parametrize("cf", ["​", "‍", "⁠", "﻿", "‮", "­"])
    def test_pii_vocab_v2_a_format_character_inside_a_number_does_not_hide_it(
        self, cf: str
    ) -> None:
        assert _shown(f"809{cf}5551234") == ["********34"]
        assert _shown(f"8{cf}0{cf}9{cf}5{cf}5{cf}5{cf}1{cf}2{cf}3{cf}4") == ["********34"]

    def test_pii_vocab_v2_a_word_of_only_format_characters_does_not_cut(self) -> None:
        assert _shown("809 ​ 5551234") == ["***", "​", "*****34"]

    def test_pii_vocab_v2_a_format_character_inside_a_spoken_digit_does_not_hide_it(self) -> None:
        said = "ni​ne se​ven two eight zero eight three"
        assert _shown(said) == ["*", "*", "*", "*", "*", "8", "3"]

    def test_pii_nfkc_capped_only_the_first_64_characters_are_folded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[int] = []
        real = unicodedata.normalize

        def spy(form: str, text: str) -> str:
            seen.append(len(text))
            return real(form, text)  # type: ignore[arg-type]

        monkeypatch.setattr(unicodedata, "normalize", spy)
        shown, ids = mask_pii(_words("１" * 200, "ﷺ" * 200))
        assert seen and max(seen) <= 64
        assert ids == {"a1:w0000"}  # a long fullwidth number is still a number
        # the digits after the 64th are not folded, so the two that stay are still fullwidth
        assert shown[0].text[:198] == "*" * 198 and shown[0].text[198:] == "１１"
