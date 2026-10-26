"""PII in addresses said aloud (spec 001.16, point 4).

"john at gmail.com", "juan arroba gmail punto mx", "john dot doe at gmail dot com": the whole
address leaves as `<first letter>***@***.<tld>`, and the words of the local part are not seen.
"""

import pytest

from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Word

__all__ = ["TestPiiEmailSpoken", "TestPiiEmailV3", "TestPiiEmailV4", "TestPiiVocabV2Email"]


def _words(*texts: str) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(texts)]


def _spoken(text: str) -> list[str]:
    """What is left on the page: the shown words, without the ones masked down to nothing."""
    return [w.text for w in mask_pii(_words(*text.split(" ")))[0] if w.text]


class TestPiiEmailSpoken:
    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("john at gmail.com", "j***@***.com"),
            ("juan arroba gmail punto mx", "j***@***.mx"),
            ("john dot doe at gmail dot com", "j***@***.com"),
            ("juan punto perez arroba gmail punto com", "j***@***.com"),
            ("maria arroba hotmail.es", "m***@***.es"),
        ],
    )
    def test_pii_email_spoken_forms_leave_as_one_masked_address(
        self, said: str, shown: str
    ) -> None:
        assert _spoken(said) == [shown]

    @pytest.mark.parametrize("name", ["doe", "perez", "gmail", "hotmail"])
    def test_pii_email_spoken_names_of_the_local_part_and_the_domain_are_not_seen(
        self, name: str
    ) -> None:
        said = "john dot doe at gmail dot com juan punto perez arroba hotmail.com"
        assert name not in " ".join(_spoken(said))

    @pytest.mark.parametrize("tld", ["mx", "es", "info", "biz", "pr", "uk", "ca"])
    def test_pii_email_spoken_the_wider_list_of_tlds(self, tld: str) -> None:
        assert _spoken(f"ana at mail dot {tld}") == [f"a***@***.{tld}"]
        assert _spoken(f"ana arroba mail.{tld}") == [f"a***@***.{tld}"]

    @pytest.mark.parametrize(
        "said",
        [
            "john underscore doe at gmail dot com",
            "juan guion bajo perez arroba gmail punto com",
            "john dot doe underscore smith at gmail dot com",
            "a dot b dot c at gmail dot com",
        ],
    )
    def test_pii_email_spoken_a_local_part_of_up_to_three_words(self, said: str) -> None:
        assert len(_spoken(said)) == 1 and _spoken(said)[0].endswith("***@***.com")

    def test_pii_email_spoken_four_words_leave_the_first_one_outside(self) -> None:
        shown = _spoken("a dot b dot c dot d at gmail dot com")
        assert shown[-1].endswith("@***.com") and "d" not in shown[-1]

    def test_pii_email_spoken_the_rest_of_the_sentence_is_untouched(self) -> None:
        said = "escribe a juan arroba gmail punto com ok gracias"
        assert _spoken(said) == ["escribe", "a", "j***@***.com", "ok", "gracias"]

    def test_pii_email_spoken_ids_are_all_the_words_of_the_address(self) -> None:
        _, ids = mask_pii(_words("mail", "john", "dot", "doe", "at", "gmail", "dot", "com", "ok"))
        assert ids == {f"a1:w{i:04d}" for i in range(1, 8)}

    def test_pii_email_spoken_case_and_punctuation_do_not_matter(self) -> None:
        assert _spoken("John, AT Gmail.COM.") == ["J***@***.com"]
        assert _spoken("Juan ARROBA gmail.com,") == ["J***@***.com"]

    @pytest.mark.parametrize(
        "said",
        [
            "john at gmail.xyz",  # 001.22: "john at gmail dot xyz" is an address now (open TLD)
            "at gmail.com",
            "john at localhost",
            "john at gmail",
            "dot at gmail.com",
            "i am at home dot",
        ],
    )
    def test_pii_email_spoken_needs_a_local_part_and_a_domain_with_a_known_tld(
        self, said: str
    ) -> None:
        assert _spoken(said) == said.split(" ")

    def test_pii_email_spoken_two_addresses_in_a_row(self) -> None:
        said = "john at gmail.com y luis arroba yahoo punto org"
        assert _spoken(said) == ["j***@***.com", "y", "l***@***.org"]

    def test_pii_email_spoken_a_domain_with_two_labels(self) -> None:
        assert _spoken("juan arroba claro punto com punto do") == ["j***@***.com.do"]
        assert _spoken("juan arroba claro punto net punto do") == ["j***@***.net.do"]
        assert _spoken("juan arroba claro punto do") == ["j***@***.do"]

    def test_pii_email_spoken_masking_twice_changes_nothing(self) -> None:
        once, _ = mask_pii(_words("john", "dot", "doe", "at", "gmail", "dot", "com"))
        assert mask_pii(once)[0] == once


class TestPiiVocabV2Email:
    """001.17 point 8: a loose `@` is "at", and the TLDs `cl dev app ai` and `com.do` / `net.do`."""

    def test_pii_vocab_v2_a_loose_at_sign_joins_the_address(self) -> None:
        assert _spoken("john @ gmail.com") == ["j***@***.com"]
        assert _spoken("juan punto perez @ gmail punto com") == ["j***@***.com"]

    def test_pii_vocab_v2_a_loose_at_sign_without_an_address_changes_nothing(self) -> None:
        assert _spoken("a @ b") == ["a", "@", "b"]
        assert _spoken("@ gmail.com") == ["@", "gmail.com"]

    @pytest.mark.parametrize("tld", ["cl", "dev", "app", "ai"])
    def test_pii_vocab_v2_the_new_tlds(self, tld: str) -> None:
        assert _spoken(f"ana at mail dot {tld}") == [f"a***@***.{tld}"]
        assert _spoken(f"ana arroba mail.{tld}") == [f"a***@***.{tld}"]
        assert _spoken(f"ana@mail.{tld}") == [f"a***@***.{tld}"]

    def test_pii_vocab_v2_com_do_and_net_do_are_whole_tlds(self) -> None:
        assert _spoken("ana at claro.com.do") == ["a***@***.com.do"]
        assert _spoken("ana at claro.net.do") == ["a***@***.net.do"]
        assert _spoken("ana@claro.com.do") == ["a***@***.com.do"]
        assert _spoken("ana at claro punto com punto do") == ["a***@***.com.do"]
        assert _spoken("ana at claro.org.do") == ["a***@***.do"]  # only the two compounds


class TestPiiEmailV3:
    """001.18 point 5: a domain label of 1 to 3 words, spoken digits in the local part, and
    `dash` / `hyphen` joining the words of the local part."""

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("info at big apple trucking dot com", "i***@***.com"),
            ("info arroba spa bella vida punto com", "i***@***.com"),
            ("info at big apple dot com", "i***@***.com"),
            ("ana arroba la casa punto do", "a***@***.do"),
            ("ana at big apple dot net dot do", "a***@***.net.do"),
        ],
    )
    def test_pii_email_v3_a_domain_of_one_to_three_words(self, said: str, shown: str) -> None:
        assert _spoken(said) == [shown]

    def test_pii_email_v3_the_words_of_the_domain_are_not_seen(self) -> None:
        said = "escribe a info at big apple trucking dot com gracias"
        assert _spoken(said) == ["escribe", "a", "i***@***.com", "gracias"]
        assert "apple" not in " ".join(_spoken(said))

    def test_pii_email_v3_five_words_in_a_label_are_not_a_domain(self) -> None:
        said = "info at big red apple trucking company dot com"  # 001.21: four words are a domain
        assert _spoken(said) == said.split(" ")

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("juan uno dos tres arroba gmail punto com", "j***@***.com"),
            ("maria nine five at gmail dot com", "m***@***.com"),
            ("one two three john at gmail dot com", "o***@***.com"),
            ("juan 123 at gmail dot com", "j***@***.com"),
            ("john dot doe two three at gmail dot com", "j***@***.com"),
            ("cero ocho arroba gmail.com", "c***@***.com"),
        ],
    )
    def test_pii_email_v3_spoken_digits_are_part_of_the_local_part(
        self, said: str, shown: str
    ) -> None:
        assert _spoken(said) == [shown]

    @pytest.mark.parametrize(
        "said",
        [
            "john dash doe at gmail dot com",
            "ana hyphen perez arroba gmail punto com",
            "john dash doe dash smith at gmail dot com",
            "john dash doe underscore smith at gmail dot com",
        ],
    )
    def test_pii_email_v3_dash_and_hyphen_join_the_local_part(self, said: str) -> None:
        shown = _spoken(said)
        assert len(shown) == 1 and shown[0].endswith("***@***.com")

    def test_pii_email_v3_the_name_before_a_dash_is_not_seen(self) -> None:
        text = " ".join(_spoken("john dash doe at gmail dot com"))
        assert "john" not in text and "doe" not in text and text == "j***@***.com"

    def test_pii_email_v3_ordinary_words_before_the_at_stay_out(self) -> None:
        said = "mi correo es juan uno dos arroba gmail punto com ok"
        assert _spoken(said) == ["mi", "correo", "es", "j***@***.com", "ok"]

    def test_pii_email_v3_spoken_digits_before_an_open_tld_are_an_address(self) -> None:
        said = "llamame al cinco cinco cinco at the office dot xyz"
        # 001.22: any word is a TLD after `dot`; it hides more than it should, and that is accepted
        assert _spoken(said) == ["llamame", "a***@***.xyz"]  # `al cinco cinco cinco` is the name

    def test_pii_email_v3_ids_are_all_the_words_of_the_address(self) -> None:
        words = _words("mail", "info", "at", "big", "apple", "dot", "com", "ok")
        assert mask_pii(words)[1] == {f"a1:w{i:04d}" for i in range(1, 7)}


class TestPiiEmailV4:
    """001.21 point 5: second-level TLDs, more TLDs, a local part of up to 4 words with the numbers
    said in it, and a domain of up to 4 words with its articles."""

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("john at bigpond dot com dot au", "j***@***.com.au"),
            ("john at bbc dot co dot uk", "j***@***.co.uk"),
            ("juan arroba telmex punto com punto mx", "j***@***.com.mx"),
            ("ana at uol dot com dot br", "a***@***.com.br"),
            ("ken at yahoo dot co dot jp", "k***@***.co.jp"),
            ("john at bigpond.com.au", "j***@***.com.au"),
            ("john@bbc.co.uk", "j***@***.co.uk"),
            ("ana arroba telmex.com.mx", "a***@***.com.mx"),
        ],
    )
    def test_pii_email_v4_second_level_tlds_leave_with_the_address(
        self, said: str, shown: str
    ) -> None:
        assert _spoken(said) == [shown]

    @pytest.mark.parametrize("tld", ["ph", "au", "br", "jp", "de", "fr", "it", "nl"])
    def test_pii_email_v4_the_new_tlds(self, tld: str) -> None:
        assert _spoken(f"ana at mail dot {tld}") == [f"a***@***.{tld}"]
        assert _spoken(f"ana arroba mail.{tld}") == [f"a***@***.{tld}"]
        assert _spoken(f"ana@mail.{tld}") == [f"a***@***.{tld}"]

    @pytest.mark.parametrize(
        "said",
        [
            "my email is john dot smith eighty five at gmail dot com",
            "my email is john dot smith eight five at gmail dot com",
            "my email is john dot a dot b dot smith at gmail dot com",
            "my email is john dot smith dot twenty one at gmail dot com",
        ],
    )
    def test_pii_email_v4_a_local_part_of_four_words_and_the_numbers_said(self, said: str) -> None:
        assert _spoken(said) == ["my", "email", "is", "j***@***.com"]

    @pytest.mark.parametrize(
        "said",
        [
            "mi correo es juan punto perez ochenta y cinco arroba gmail punto com",
            "mi correo es juan guion bajo perez treinta y cuatro arroba gmail punto com",
        ],
    )
    def test_pii_email_v4_a_number_said_in_spanish_is_part_of_the_local_part(
        self, said: str
    ) -> None:
        assert _spoken(said) == ["mi", "correo", "es", "j***@***.com"]

    def test_pii_email_v4_two_names_in_a_row_still_leave_the_first_one_out(self) -> None:
        said = "mi correo es juan perez ochenta y cinco arroba gmail punto com"
        shown = _spoken(said)
        assert shown == ["mi", "correo", "es", "juan", "p***@***.com"]
        assert not {"perez", "ochenta", "cinco"} & set(shown)

    def test_pii_email_v4_five_words_are_more_than_a_local_part_has(self) -> None:
        assert _spoken("a dot b dot c dot d dot e at gmail dot com") == ["a", "dot", "b***@***.com"]

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            (
                "write to info at the big apple trucking company dot com",
                ["write", "to", "i***@***.com"],
            ),
            ("info arroba el gran hotel palace punto com", ["i***@***.com"]),
            ("info at big red apple trucking dot com", ["i***@***.com"]),
        ],
    )
    def test_pii_email_v4_a_domain_of_four_words_with_its_articles(
        self, said: str, shown: list[str]
    ) -> None:
        assert _spoken(said) == shown

    def test_pii_email_v4_five_words_in_a_label_are_not_a_domain(self) -> None:
        said = "info at big red apple trucking company dot com"
        assert _spoken(said) == said.split(" ")

    def test_pii_email_v4_the_words_of_the_domain_are_not_seen(self) -> None:
        said = "write to info at the big apple trucking company dot com"
        text = " ".join(_spoken(said))
        assert "apple" not in text and "trucking" not in text and "company" not in text
