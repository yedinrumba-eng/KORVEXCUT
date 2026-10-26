"""PII masking (spec 001.13): digits, numbers said in words, and e-mail addresses.

`mask_pii` is pure: words in, displayed words and the ids it masked out. A run of 7 or more digits
is PII; every digit but the last two becomes `*`; separators stay and each word keeps its edges.
"""

import random
import time
from dataclasses import replace

import pytest

from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Word

# The classes of spec 001.16 live in `pii_cases_*.py` (300-line rule) and are collected here, which
# is the file the criteria of the spec run.
from tests.unit.pii_cases_bridges import *  # noqa: F403
from tests.unit.pii_cases_email import *  # noqa: F403
from tests.unit.pii_cases_numbers import *  # noqa: F403
from tests.unit.pii_cases_unicode import *  # noqa: F403


def _words(*texts: str, clip: str = "a1") -> list[Word]:
    return [
        Word(f"{clip}:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(texts)
    ]


def _shown(text: str) -> list[str]:
    return [w.text for w in mask_pii(_words(*text.split(" ")))[0]]


def _ids(text: str) -> set[str]:
    return mask_pii(_words(*text.split(" ")))[1]


class TestPiiDigits:
    def test_pii_digits_a_phone_split_in_words(self) -> None:
        shown, ids = mask_pii(_words("mi", "numero", "972", "808", "3211", "gracias"))
        assert [w.text for w in shown] == ["mi", "numero", "***", "***", "**11", "gracias"]
        assert ids == {"a1:w0002", "a1:w0003", "a1:w0004"}

    def test_pii_digits_a_cedula_in_one_word_keeps_its_dashes(self) -> None:
        assert _shown("001-1234567-8") == ["***-******7-8"]

    def test_pii_digits_a_card_in_four_words(self) -> None:
        assert _shown("4111 1111 1111 1111") == ["****", "****", "****", "**11"]

    def test_pii_digits_country_code_parentheses_and_plus_stay(self) -> None:
        assert _shown("+1 (972) 808-3211") == ["+*", "(***)", "***-**11"]

    def test_pii_digits_words_between_the_numbers_cut_the_run(self) -> None:
        assert _shown("972 uh 808 3211") == ["972", "uh", "***", "**11"]

    def test_pii_digits_the_punctuation_around_a_word_stays(self) -> None:
        assert _shown("¿972, 808 3211?") == ["¿***,", "***", "**11?"]
        assert _shown("es 972 808 3211.") == ["es", "***", "***", "**11."]

    def test_pii_digits_seven_is_the_threshold_and_six_is_not(self) -> None:
        assert _shown("123 4567") == ["***", "**67"]
        assert _shown("123 456") == ["123", "456"]

    def test_pii_digits_only_the_last_two_digits_of_the_whole_run_survive(self) -> None:
        assert _shown("1 2 3 4 5 6 7 8") == ["*", "*", "*", "*", "*", "*", "7", "8"]
        assert _shown("12345678901234567890") == ["*" * 18 + "90"]

    def test_pii_digits_a_lone_separator_word_does_not_cut_a_run(self) -> None:
        assert _shown("972 - 808 3211") == ["***", "-", "***", "**11"]

    def test_pii_digits_a_separator_alone_is_never_a_number(self) -> None:
        assert _shown("- . ( )") == ["-", ".", "(", ")"]
        assert _ids("- . ( )") == set()

    def test_pii_digits_two_runs_are_judged_one_by_one(self) -> None:
        assert _shown("123 456 luego 4567890") == ["123", "456", "luego", "*****90"]

    def test_pii_digits_ids_are_those_of_the_masked_words_only(self) -> None:
        _, ids = mask_pii(_words("hola", "972", "808", "3211", "adios", "5551234"))
        assert ids == {"a1:w0001", "a1:w0002", "a1:w0003", "a1:w0005"}

    def test_pii_digits_the_other_fields_of_a_word_are_kept(self) -> None:
        word = Word("a1:w0007", 7, "9728083211", 1000, 1500, 0.31, True)
        (shown,), ids = mask_pii([word])
        assert shown == replace(word, text="********11") and ids == {"a1:w0007"}

    def test_pii_digits_deleted_words_are_skipped_and_do_not_cut_a_run(self) -> None:
        words = _words("972", "", "808", "3211")
        shown, ids = mask_pii(words)
        assert [w.text for w in shown] == ["***", "", "***", "**11"]
        assert ids == {"a1:w0000", "a1:w0002", "a1:w0003"}

    def test_pii_digits_the_input_is_not_changed_and_masking_twice_changes_nothing(self) -> None:
        words = _words("972", "808", "3211")
        once, _ = mask_pii(words)
        assert [w.text for w in words] == ["972", "808", "3211"]
        assert mask_pii(once)[0] == once

    def test_pii_digits_nothing_in_nothing_out(self) -> None:
        assert mask_pii([]) == ([], set())


class TestPiiSpoken:
    def test_pii_spoken_english_digits(self) -> None:
        shown = _shown("nine seven two eight zero eight three")
        assert shown == ["*", "*", "*", "*", "*", "8", "3"]

    def test_pii_spoken_spanish_digits(self) -> None:
        shown = _shown("nueve siete dos ocho cero ocho tres")
        assert shown == ["*", "*", "*", "*", "*", "8", "3"]

    def test_pii_spoken_oh_is_a_zero(self) -> None:
        assert _shown("five five five oh one two three") == ["*"] * 5 + ["2", "3"]

    def test_pii_spoken_case_accents_and_punctuation_do_not_matter(self) -> None:
        shown = _shown("Nueve, SIETE dos. ocho cero Ocho tres!")
        assert shown == ["*,", "*", "*.", "*", "*", "8", "3!"]

    def test_pii_spoken_mixed_with_digits(self) -> None:
        assert _shown("972 eight zero eight 3211") == ["***", "*", "*", "*", "**11"]

    def test_pii_spoken_the_last_two_digits_can_be_words_or_numbers(self) -> None:
        assert _shown("9728083 one one") == ["*******", "1", "1"]

    def test_pii_spoken_ids(self) -> None:
        words = _words("call", "nine", "seven", "two", "eight", "zero", "eight", "three", "now")
        assert mask_pii(words)[1] == {f"a1:w{i:04d}" for i in range(1, 8)}

    def test_pii_spoken_six_words_are_not_enough(self) -> None:
        assert _shown("nine seven two eight zero eight") == [
            "nine",
            "seven",
            "two",
            "eight",
            "zero",
            "eight",
        ]


class TestPiiNotMasked:
    @pytest.mark.parametrize(
        "text",
        [
            "2026",
            "15 minutes",
            "Terminal C21",
            "flight 1234",
            "5:31",
            "12:54",
            "a las 12:54 y 5:31",
            "one two three",
            "I have two cats and nine dogs",
            "tengo dos gatos y nueve perros",
            "version 3.14",
            "C21 123",
            "hola mundo",
            "-",
        ],
    )
    def test_pii_not_masked_stays_as_it_is(self, text: str) -> None:
        shown, ids = mask_pii(_words(*text.split(" ")))
        assert [w.text for w in shown] == text.split(" ") and ids == set()

    def test_pii_not_masked_letters_and_digits_in_one_word_cut_the_run(self) -> None:
        assert _shown("123 C21 4567") == ["123", "C21", "4567"]

    def test_pii_not_masked_a_time_in_the_middle_of_a_number_cuts_it(self) -> None:
        assert _shown("972 5:31 3211") == ["972", "5:31", "3211"]

    def test_pii_not_masked_words_that_only_sound_like_digits(self) -> None:
        said = "once doce trece catorce quince diez"  # 001.16 point 3: each one is two digits
        assert _shown(said) == ["**"] * 6
        assert _shown("catorce quince diez") == ["catorce", "quince", "diez"]  # six digits


class TestPiiEmail:
    def test_pii_email_written(self) -> None:
        shown, ids = mask_pii(_words("escribe", "a", "john.doe@gmail.com", "gracias"))
        assert [w.text for w in shown] == ["escribe", "a", "j***@***.com", "gracias"]
        assert ids == {"a1:w0002"}

    def test_pii_email_written_with_punctuation_around(self) -> None:
        assert _shown("(john.doe@gmail.com),") == ["(j***@***.com),"]
        assert _shown("john.doe@gmail.com.") == ["j***@***.com."]
        assert _shown("<Maria_1+x@mail.co.uk>") == ["<M***@***.uk>"]

    def test_pii_email_written_two_in_one_word(self) -> None:
        assert _shown("a@b.com,c@d.org") == ["a***@***.com,c***@***.org"]

    @pytest.mark.parametrize("text", ["@usuario", "usuario@localhost", "user@", "a @ b", "arroba"])
    def test_pii_email_written_needs_an_at_and_a_dot_after_it(self, text: str) -> None:
        assert _shown(text) == text.split(" ")

    def test_pii_email_spoken_english(self) -> None:
        shown, ids = mask_pii(_words("mail", "john", "at", "gmail", "dot", "com", "ok"))
        assert [w.text for w in shown] == ["mail", "j***@***.com", "", "", "", "", "ok"]
        assert ids == {f"a1:w{i:04d}" for i in range(1, 6)}

    def test_pii_email_spoken_spanish(self) -> None:
        shown, _ = mask_pii(_words("juan", "arroba", "gmail", "punto", "com"))
        assert [w.text for w in shown] == ["j***@***.com", "", "", "", ""]

    @pytest.mark.parametrize("tld", ["com", "net", "org", "edu", "gov", "io", "co", "us", "do"])
    def test_pii_email_spoken_every_tld(self, tld: str) -> None:
        shown, _ = mask_pii(_words("ana", "at", "mail", "dot", tld))
        assert shown[0].text == f"a***@***.{tld}"

    def test_pii_email_spoken_case_and_accents_do_not_matter(self) -> None:
        shown, _ = mask_pii(_words("Juan", "ARROBA", "Gmail", "Punto", "COM"))
        assert shown[0].text == "J***@***.com"

    @pytest.mark.parametrize(
        "text",
        ["john at gmail dot xyz", "john at gmail com", "at gmail dot com", "john at gmail dot"],
    )
    def test_pii_email_spoken_needs_the_whole_shape(self, text: str) -> None:
        assert "@" not in "".join(_shown(text))

    def test_pii_email_spoken_two_addresses(self) -> None:
        text = "ana at x dot com y luis arroba y punto org"
        assert [w for w in _shown(text) if w] == ["a***@***.com", "y", "l***@***.org"]

    def test_pii_email_and_a_number_next_to_each_other(self) -> None:
        shown = _shown("ana@x.com 972 808 3211")
        assert shown == ["a***@***.com", "***", "***", "**11"]


class TestPiiHard:
    """Digit runs cut every way, and hostile input."""

    def test_pii_digits_random_splits_keep_exactly_the_last_two_digits(self) -> None:
        rng = random.Random(25)
        for _ in range(300):
            digits = "".join(rng.choice("0123456789") for _ in range(rng.randint(7, 24)))
            words, at = [], 0
            while at < len(digits):
                step = rng.randint(1, 5)
                chunk = digits[at : at + step]
                words.append(
                    rng.choice(["", "(", "+"]) * (at == 0) + chunk + rng.choice(["", "-", ","])
                )
                at += step
            shown = "".join(w.text for w in mask_pii(_words(*words))[0])
            kept = [ch for ch in shown if ch.isdigit()]
            assert kept == list(digits[-2:]), (words, shown)
            assert shown.count("*") == len(digits) - 2

    def test_pii_digits_random_splits_of_six_or_fewer_are_never_masked(self) -> None:
        rng = random.Random(7)
        for _ in range(200):
            words = [
                "".join(rng.choice("0123456789") for _ in range(rng.randint(1, 3)))
                for _ in range(2)
            ]
            if sum(map(len, words)) <= 6:
                assert _shown(" ".join(words)) == words

    def test_pii_spoken_random_digit_words_in_both_languages(self) -> None:
        rng = random.Random(11)
        names = [
            "cero",
            "uno",
            "dos",
            "tres",
            "cuatro",
            "cinco",
            "seis",
            "siete",
            "ocho",
            "nueve",
            "zero",
            "oh",
            "one",
            "two",
            "three",
            "four",
        ]
        for _ in range(100):
            said = [rng.choice(names) for _ in range(rng.randint(7, 15))]
            shown = [w.text for w in mask_pii(_words(*said))[0]]
            assert shown[:-2] == ["*"] * (len(said) - 2) and all(d.isdigit() for d in shown[-2:])

    def test_pii_not_masked_hostile_200_character_words_are_fast_and_untouched(self) -> None:
        started = time.monotonic()
        texts = ["a" + "!" * 198 + "b", "-" * 200, "@" * 200, "a@" * 100, "1" + "." * 198 + "2"]
        for text in texts * 50:
            mask_pii(_words(text, text))
        assert time.monotonic() - started < 2.0
        assert _shown("a" + "!" * 198 + "b") == ["a" + "!" * 198 + "b"]

    def test_pii_digits_a_long_transcript_is_masked_in_linear_time(self) -> None:
        words = _words(*(["hola", "972", "808", "3211", "adios"] * 4000))
        started = time.monotonic()
        shown, ids = mask_pii(words)
        assert time.monotonic() - started < 2.0 and len(ids) == 12_000
        assert [w.text for w in shown[:5]] == ["hola", "***", "***", "**11", "adios"]

    def test_pii_email_hostile_addresses_are_still_masked_once(self) -> None:
        assert _shown("x" * 60 + "@" + "y" * 60 + ".com") == ["x***@***.com"]
        assert _shown("a@b.c@d.e") == ["a***@***.c***@***.e"]  # each address, domain hidden
