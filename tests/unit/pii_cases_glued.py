"""PII, S1.5a row 26 (spec 001.23, point 2): the TLD of a written address is only letters.

Collected from `test_pii.py` through `pii_cases_numbers.py` (that file is at 300 lines).
"""

import pytest

from kcut.pack.pii import mask_pii, mask_pii_spans, mask_text
from kcut.transcribe.model import Word

__all__ = ["TestPiiEmailGluedV2"]


def _words(*texts: str) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(texts)]


def _shown(text: str) -> list[str]:
    return [w.text for w in mask_pii(_words(*text.split(" ")))[0]]


class TestPiiEmailGluedV2:
    """001.23 point 2: the TLD of a written address is only letters. What follows it, with a hyphen
    or a dot, is not part of the address and goes through the numbers pass in its place."""

    @pytest.mark.parametrize(
        ("said", "shown"),
        [
            ("juan@gmail.com-8095551234", "j***@***.com-********34"),
            ("juan@gmail.com.8095551234", "j***@***.com.********34"),
            ("juan@gmail.com_8095551234", "j***@***.com_********34"),
            ("juan@claro.com.do.8095551234", "j***@***.com.do.********34"),
            ("juan@gmail.com.mx-8095551234", "j***@***.com.mx-********34"),
            ("juan@gmail.com-(809)555-1234", "j***@***.com-(***)***-**34"),
        ],
    )
    def test_email_glued_v2_the_address_ends_at_the_last_label_of_letters(
        self, said: str, shown: str
    ) -> None:
        assert _shown(said) == [shown]

    @pytest.mark.parametrize("said", ["juan@gmail.com-8095551234", "juan@gmail.com.8095551234"])
    def test_email_glued_v2_only_the_last_two_digits_of_the_phone_are_left(self, said: str) -> None:
        (text,) = _shown(said)
        assert text.startswith("j***@***.com") and "gmail" not in text and "juan" not in text
        assert [ch for ch in text if ch.isdigit()] == ["3", "4"]

    def test_email_glued_v2_a_hyphen_inside_the_domain_is_still_one_address(self) -> None:
        assert _shown("juan@mi-empresa.com") == ["j***@***.com"]
        assert _shown("juan@mi-gran-empresa.co.uk") == ["j***@***.co.uk"]
        assert _shown("juan@mi-empresa.com;8095551234") == ["j***@***.com;********34"]

    def test_email_glued_v2_a_hyphen_between_words_after_the_tld_is_left_as_it_is(self) -> None:
        assert _shown("juan@gmail.com-abc") == ["j***@***.com-abc"]
        assert _shown("juan@gmail.com-123") == ["j***@***.com-123"]  # 3 digits: no number

    def test_email_glued_v2_the_number_joins_the_words_that_follow(self) -> None:
        shown = _shown("juan@gmail.com-809 5551234 gracias")
        assert shown == ["j***@***.com-***", "*****34", "gracias"]

    def test_email_glued_v2_a_last_label_of_digits_alone_is_no_domain(self) -> None:
        assert _shown("a@b.123") == ["a@b.123"]
        assert _shown("juan@gmail.com.123") == ["j***@***.com.123"]

    def test_email_glued_v2_ids_and_inside_words_are_the_word(self) -> None:
        _, ids, inside = mask_pii_spans(_words("hola", "juan@gmail.com-8095551234"), ())
        assert ids == {"a1:w0001"} and inside == {"a1:w0001"}

    def test_email_glued_v2_in_a_name_of_a_file_the_number_is_masked_too(self) -> None:
        shown = mask_text("crudo/juan@gmail.com-8095551234.mp4")
        assert "8095551234" not in shown and shown.startswith("crudo/j***@***.com")
