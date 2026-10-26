"""PII in addresses said aloud (spec 001.16, point 4).

"john at gmail.com", "juan arroba gmail punto mx", "john dot doe at gmail dot com": the whole
address leaves as `<first letter>***@***.<tld>`, and the words of the local part are not seen.
"""

import pytest

from kcut.pack.pii import mask_pii
from kcut.transcribe.model import Word

__all__ = ["TestPiiEmailSpoken", "TestPiiVocabV2Email"]


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
            "john at gmail dot xyz",
            "john at gmail.xyz",
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
