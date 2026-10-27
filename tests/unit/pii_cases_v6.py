"""PII, S1.5b step 0 (spec 001.24, points 1, 2 and 13): the stretches between written addresses, the
second address of a path and `guion guion`.

Collected from `test_pii.py` (through `pii_cases_numbers.py`) and from `test_pii_pack.py` (through
`pii_cases_paths.py`): both files are at the 300-line limit.
"""

import pytest

from kcut.pack.pii import mask_pii, mask_pii_spans, mask_text
from kcut.pack.pii_written import (
    last_at_is_open,
    mask_bare_domains,
    mask_written,
    split_written,
)
from kcut.transcribe.model import Word

__all__ = [
    "TestPiiEmailGluedV3",
    "TestPiiEmailV6JoinRepeat",
    "TestPiiPathEmailV2",
    "TestPiiPathEmailV3",
    "TestPiiPathEmailV4",
]


def _words(*texts: str) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(texts)]


def _shown(text: str) -> list[str]:
    return [w.text for w in mask_pii(_words(*text.split(" ")))[0]]


def _digits(shown: list[str]) -> str:
    return "".join(ch for text in shown for ch in text if ch.isdigit())


class TestPiiEmailGluedV3:
    """001.24 point 1: `split_written` gives every stretch that is not an address, before, between
    and after, and each one goes through the numbers pass in its position."""

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("a@b.com-5551234;c@d.org", "a***@***.com-*****34;c***@***.org"),
            ("a@b.com;8095551234;c@d.org", "a***@***.com;********34;c***@***.org"),
            ("8095551234;juan@gmail.com", "********34;j***@***.com"),
            ("a@b.com;4111111111111111;c@d.org", "a***@***.com;**************11;c***@***.org"),
            ("a@b.com;(809)555-1234;c@d.org", "a***@***.com;(***)***-**34;c***@***.org"),
            ("(8095551234)juan@gmail.com", "(********34)j***@***.com"),
        ],
    )
    def test_email_glued_v3_the_number_in_every_stretch_loses_all_but_its_last_two(
        self, said: str, shown: str
    ) -> None:
        assert _shown(said) == [shown]

    def test_email_glued_v3_two_numbers_between_three_addresses_show_at_most_two_digits(
        self,
    ) -> None:
        said = "juan@gmail.com;8095551234;pedro@gmail.com;8095551111"
        (text,) = _shown(said)
        assert text.startswith("j***@***.com;") and ";p***@***.com;" in text
        assert "juan" not in text and "pedro" not in text and "gmail" not in text
        assert _digits([text]) in ("11", "3411")  # nothing but the last two of a number (or run)
        assert not any(run in text for run in ("80955", "55512", "09555"))

    def test_email_glued_v3_a_number_after_an_address_in_the_next_word_is_still_masked(
        self,
    ) -> None:
        assert _shown("a@b.com 8095551234 c@d.org") == [
            "a***@***.com",
            "********34",
            "c***@***.org",
        ]

    def test_email_glued_v3_the_stretches_join_the_words_around_the_word(self) -> None:
        shown = _shown("809 5551234;juan@gmail.com hola")
        assert shown == ["***", "*****34;j***@***.com", "hola"]
        # the address is not a wall: a number that comes after it still joins the one before
        assert _shown("809 5551234;juan@gmail.com 777") == ["***", "*******;j***@***.com", "*77"]

    def test_email_glued_v3_a_stretch_without_digits_or_with_a_short_number_stays(self) -> None:
        assert _shown("a@b.com;gracias;c@d.org") == ["a***@***.com;gracias;c***@***.org"]
        assert _shown("a@b.com;123;c@d.org") == ["a***@***.com;123;c***@***.org"]
        assert _shown("a@b.com;c@d.org") == ["a***@***.com;c***@***.org"]

    def test_email_glued_v3_a_stretch_with_letters_and_digits_is_masked_too(self) -> None:
        assert _shown("a@b.com;tel8095551234;c@d.org") == [
            "a***@***.com;tel********34;c***@***.org"
        ]

    def test_email_glued_v3_ids_and_inside_are_the_word_and_no_address_is_left_in_it(self) -> None:
        shown, ids, inside = mask_pii_spans(_words("hola", "a@b.com;8095551234;c@d.org"), ())
        assert ids == {"a1:w0001"} and inside == {"a1:w0001"}
        assert shown[1].text == "a***@***.com;********34;c***@***.org"

    def test_email_glued_v3_in_a_name_of_a_file_each_number_is_masked_too(self) -> None:
        shown = mask_text("crudo/a@b.com-5551234;c@d.org.mp4")
        assert shown == "crudo/a***@***.com-*****34;c***@***.org.mp4"
        assert "5551234" not in mask_text("crudo/8095551234;juan@gmail.com.mp4")

    def test_email_glued_v3_split_written_returns_every_stretch_in_order(self) -> None:
        split = split_written("pre;a@b.com-5551234;c@d.org;post")
        assert split is not None
        assert split.gaps == ("pre;", "-5551234;", ";post")
        assert split.addresses == ("a***@***.com", "c***@***.org")
        assert split.joined() == "pre;a***@***.com-5551234;c***@***.org;post"
        assert split_written("sin direccion") is None
        only = split_written("juan@gmail.com")
        assert only is not None and only.gaps == ("", "") and only.joined() == "j***@***.com"

    def test_email_glued_v3_mask_written_still_leaves_the_stretches_as_they_were(self) -> None:
        assert mask_written("8095551234;juan@gmail.com;x") == "8095551234;j***@***.com;x"
        assert mask_written("nada") is None


class TestPiiEmailV6JoinRepeat:
    """001.24 point 13: several joiner words in a row (`guion guion`) count as one."""

    @pytest.mark.parametrize(
        "said",
        [
            "juan guion guion perez arroba gmail punto com",
            "juan punto punto perez arroba gmail punto com",
            "juan guion guion guion perez arroba gmail punto com",
            "juan dash dash perez at gmail dot com",
            "juan guion bajo guion bajo perez arroba gmail punto com",
            "juan guion guion bajo perez arroba gmail punto com",
            "juan guion punto perez arroba gmail punto com",
        ],
    )
    def test_pii_email_v6_join_repeat_the_run_of_joiners_is_one_joiner(self, said: str) -> None:
        shown = _shown(said)
        assert shown[0] == "j***@***.com" and set(shown[1:]) == {""}

    def test_pii_email_v6_join_repeat_one_joiner_still_works_as_before(self) -> None:
        assert _shown("juan guion perez arroba gmail punto com")[0] == "j***@***.com"
        assert _shown("juan guion bajo perez arroba gmail punto com")[0] == "j***@***.com"

    def test_pii_email_v6_join_repeat_joiners_alone_do_not_make_a_local_part(self) -> None:
        said = "guion guion arroba gmail punto com"
        assert _shown(said) == said.split(" ")

    def test_pii_email_v6_join_repeat_a_run_of_joiners_at_the_start_is_left_out(self) -> None:
        shown = _shown("hola guion guion perez arroba gmail punto com")
        assert shown[0] == "h***@***.com"  # `hola` and `perez`: the run between them is one joiner
        shown = _shown("guion guion perez arroba gmail punto com")
        assert shown[:2] == ["guion", "guion"] and shown[2] == "p***@***.com"

    def test_pii_email_v6_join_repeat_a_long_run_of_joiners_is_fast(self) -> None:
        said = "juan " + "guion " * 5000 + "perez arroba gmail punto com"
        assert _shown(said)[0] == "j***@***.com"


class TestPiiPathEmailV2:
    """001.24 point 2: in a path, if the last `@` of a part is not covered, the extension that was
    cut off is put back on and it is tried again."""

    @pytest.mark.parametrize(
        "name",
        [
            "crudo/juan@gmail.com;pedro@gmail.com",
            "crudo/juan@gmail.com_pedro@gmail.com",
            "juan@gmail.com;pedro@gmail.com",
            "crudo/cam a/juan@gmail.com;pedro@gmail.com",
        ],
    )
    def test_path_email_v2_neither_address_stays_legible(self, name: str) -> None:
        shown = mask_text(name)
        assert "juan" not in shown and "pedro" not in shown and "gmail" not in shown

    def test_path_email_v2_the_second_address_gets_its_tld_back(self) -> None:
        assert (
            mask_text("crudo/juan@gmail.com;pedro@gmail.com") == "crudo/j***@***.com;p***@***.com"
        )

    @pytest.mark.parametrize(
        "name",
        [
            "lunes@10am.mp4",
            "logo@2x.png",
            "crudo/lunes@10am.mp4",
            "assets/logo@2x.png",
        ],  # 001.25: `crudo/juan@gmail.com;pedro@gmail.mp4` moved to TestPiiPathEmailV3
    )
    def test_path_email_v2_a_file_with_an_at_and_a_media_extension_does_not_change(
        self, name: str
    ) -> None:
        shown = mask_text(name)
        assert shown == name.replace("juan@gmail.com", "j***@***.com")

    def test_path_email_v2_last_at_is_open_says_which_at_is_left_uncovered(self) -> None:
        assert last_at_is_open("juan@gmail.com;pedro@gmail")
        assert last_at_is_open("lunes@10am")
        assert not last_at_is_open("juan@gmail.com")
        assert not last_at_is_open("juan@gmail.com;pedro@gmail.com")
        assert not last_at_is_open("sin arroba")


class TestPiiPathEmailV3:
    """001.25 point 15: in a path, `<local>@<a word of two or more letters>` with no TLD of the
    list is masked as `<first>***@***`: the extension cut off the TLD, or it is a folder."""

    def test_path_email_v3_the_second_address_of_a_name_with_a_media_extension_is_masked(
        self,
    ) -> None:
        shown = mask_text("crudo/juan@gmail.com;pedro@gmail.mp4")
        assert "pedro" not in shown and "gmail" not in shown and "juan" not in shown
        assert shown == "crudo/j***@***.com;p***@***.mp4"  # 001.25: it was `...;pedro@gmail.mp4`

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("pedro@gmail.mp4", "p***@***.mp4"),
            ("crudo/pedro@gmail.mov", "crudo/p***@***.mov"),
            ("crudo/juan.perez@empresa.mp4", "crudo/j***@***.mp4"),
            ("crudo/pedro@gmail/clip.mp4", "crudo/p***@***/clip.mp4"),
            ("crudo/8095551234@gmail.mp4", "crudo/8***@***.mp4"),
        ],
    )
    def test_path_email_v3_a_word_of_letters_after_the_at_is_masked(
        self, name: str, masked: str
    ) -> None:
        assert mask_text(name) == masked

    @pytest.mark.parametrize(
        "name",
        [
            "logo@2x.png",
            "lunes@10am.mp4",
            "crudo/escena@2.mov",
            "crudo/lunes@10am.mp4",
            "assets/logo@2x.png",
            "crudo/clip@a.mp4",  # one letter is not a domain
            "crudo/@home.mp4",  # no local part
            # 001.26: `crudo/clip@mi-casa.mp4` moved to TestPiiPathEmailV4: a hyphen no longer
            # makes the label something other than a word of letters
            "crudo/clip@casa2.mp4",
        ],
    )
    def test_path_email_v3_what_is_not_an_address_does_not_change(self, name: str) -> None:
        assert mask_text(name) == name

    def test_path_email_v3_an_address_with_a_listed_tld_is_as_it_was(self) -> None:
        assert mask_text("crudo/juan@gmail.com") == "crudo/j***@***.com"
        assert mask_text("crudo/juan@gmail.com.mp4") == "crudo/j***@***.com.mp4"

    def test_path_email_v3_a_name_read_whole_is_not_read_by_parts(self) -> None:
        assert mask_text("pedro@gmail", parts=False) == "pedro@gmail"


class TestPiiPathEmailV4:
    """001.26 point 9: a label with no TLD of the list counts as a word of letters if, without its
    `-` and `_`, only letters are left (two or more). Digits still keep it out (001.25 point 15)."""

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("crudo/pedrogomez@mi-empresa.mp4", "crudo/p***@***.mp4"),
            ("pedrogomez@gmail_final.mp4", "p***@***.mp4"),
            ("crudo/clip@mi-casa.mp4", "crudo/c***@***.mp4"),  # 001.26: it was left as it was
            ("pedrogomez@mi_empresa_sa.mov", "p***@***.mov"),
            ("crudo/pedrogomez@mi-empresa/clip.mp4", "crudo/p***@***/clip.mp4"),
            ("crudo/pedrogomez@a-b.mp4", "crudo/p***@***.mp4"),  # two letters once `-` is gone
        ],
    )
    def test_path_email_v4_a_label_of_letters_with_hyphens_or_underscores_is_masked(
        self, name: str, masked: str
    ) -> None:
        shown = mask_text(name)
        assert shown == masked and "pedrogomez" not in shown

    @pytest.mark.parametrize(
        "name",
        [
            "logo@2x.png",
            "lunes@10am.mp4",
            "pedrogomez@hotmail2.mp4",
            "crudo/pedrogomez@mi-empresa2.mp4",  # a digit among the letters
            "crudo/pedrogomez@mi-2.mp4",
            "crudo/pedrogomez@a-.mp4",  # one letter is not a domain
            "crudo/pedrogomez@-_.mp4",  # no letters at all
            "crudo/@mi-empresa.mp4",  # no local part
        ],
    )
    def test_path_email_v4_what_has_a_digit_or_too_few_letters_does_not_change(
        self, name: str
    ) -> None:
        assert mask_text(name) == name

    def test_path_email_v4_the_masker_alone_takes_hyphens_and_underscores(self) -> None:
        assert mask_bare_domains("pedro@mi-empresa") == "p***@***"
        assert mask_bare_domains("pedro@gmail_final") == "p***@***"
        assert mask_bare_domains("pedro@hotmail2") == "pedro@hotmail2"
        assert mask_bare_domains("pedro@--") == "pedro@--"
