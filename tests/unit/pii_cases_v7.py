"""PII in file names, S1.6a (spec 001.27, point 7, row 18; and 001.28, point 4, row 25): a label
that begins with 3 letters is an address, whatever follows them (`_2026`, `-v2`, `2`,
`-8095551234`); so is a label whose first stretch, up to the first `-` or `_`, is 2 letters
or more (`yo-2026`, `yo-8095551234`).

Collected from `test_pii_pack.py` (through `pii_cases_paths.py`), which is at the 300-line limit.
"""

import pytest

from kcut.pack.pii import mask_text
from kcut.pack.pii_written import mask_bare_domains

__all__ = ["TestPiiPathEmailV5", "TestPiiPathEmailV6"]


class TestPiiPathEmailV5:
    """001.27 point 7: besides a label that is only letters (001.26 point 9), a label whose first
    3 characters are letters (`str.isalpha`) is masked as `<first>***@***`. Digits at the start or
    in the first 3 characters still keep a name out (`logo@2x`, `lunes@10am`, `foto@v2`)."""

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("pedrogomez@gmail_2026.mp4", "p***@***.mp4"),
            ("pedrogomez@gmail_final_v2.mp4", "p***@***.mp4"),
            ("pedrogomez@empresa-v2.mp4", "p***@***.mp4"),
            ("pedrogomez@hotmail2.mp4", "p***@***.mp4"),  # 001.25 had left it as it was
            ("clip@take3.mp4", "c***@***.mp4"),  # the price: a false positive, cheap
            ("crudo/clip@casa2.mp4", "crudo/c***@***.mp4"),  # 001.25 had left it as it was
            ("pedrogomez@mi-empresa.mp4", "p***@***.mp4"),  # as in 001.26
            ("crudo/pedrogomez@gmail_2026.mov", "crudo/p***@***.mov"),
            ("crudo/pedrogomez@empresa-v2/clip.mp4", "crudo/p***@***/clip.mp4"),
        ],
    )
    def test_path_email_v5_a_label_that_begins_with_3_letters_is_masked(
        self, name: str, masked: str
    ) -> None:
        shown = mask_text(name)
        assert shown == masked and "pedrogomez" not in shown

    def test_path_email_v5_the_phone_glued_to_the_label_leaves_no_digit(self) -> None:
        shown = mask_text("pedrogomez@gmail-8095551234.mp4")
        assert shown == "p***@***.mp4"
        assert not any(ch.isdigit() for ch in shown.removesuffix(".mp4"))

    @pytest.mark.parametrize(
        "name",
        [
            "logo@2x.png",
            "lunes@10am.mp4",
            "foto@v2.mp4",
            # 001.28: `crudo/pedrogomez@mi-empresa2.mp4` is masked now (TestPiiPathEmailV6)
            "crudo/pedrogomez@a1.mp4",
            "crudo/pedrogomez@ab1.mp4",  # 2 letters and a digit
            "crudo/clip@a.mp4",  # one letter is not a domain
            "crudo/@home.mp4",  # no local part
        ],
    )
    def test_path_email_v5_what_does_not_begin_with_3_letters_does_not_change(
        self, name: str
    ) -> None:
        assert mask_text(name) == name

    def test_path_email_v5_the_masker_alone_follows_the_same_rule(self) -> None:
        assert mask_bare_domains("pedro@hotmail2") == "p***@***"
        assert mask_bare_domains("pedro@gmail-8095551234") == "p***@***"
        assert mask_bare_domains("foto@v2") == "foto@v2"
        assert mask_bare_domains("pedro@ab1") == "pedro@ab1"
        assert mask_bare_domains("pedro@abc") == "p***@***"  # exactly 3 letters


class TestPiiPathEmailV6:
    """001.28 point 4: besides the labels of row 18, a label whose first stretch (cut at the first
    `-` or `_`) is 2 letters or more is masked as `<first>***@***`. The labels of row 18 give what
    they gave, and `logo@2x`, `lunes@10am` and `foto@v2` do not change."""

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("pedrogomez@yo-8095551234.mp4", "p***@***.mp4"),
            ("pedrogomez@yo-2026.mp4", "p***@***.mp4"),
            ("maria.lopez@ab-2026.mp4", "m***@***.mp4"),  # as the ones of row 18
            ("pedrogomez@yo_2026.mp4", "p***@***.mp4"),  # `_` cuts the first stretch too
            ("crudo/pedrogomez@yo-2026/clip.mp4", "crudo/p***@***/clip.mp4"),
            ("crudo/pedrogomez@mi-2.mp4", "crudo/p***@***.mp4"),  # 001.28: was left as it was
            ("crudo/pedrogomez@mi-empresa2.mp4", "crudo/p***@***.mp4"),  # was left as it was
            # the cases of row 18, which give the same as before
            ("pedrogomez@gmail_2026.mp4", "p***@***.mp4"),
            ("pedrogomez@gmail_final_v2.mp4", "p***@***.mp4"),
            ("pedrogomez@empresa-v2.mp4", "p***@***.mp4"),
            ("pedrogomez@hotmail2.mp4", "p***@***.mp4"),
            ("clip@take3.mp4", "c***@***.mp4"),
            ("pedrogomez@gmail-8095551234.mp4", "p***@***.mp4"),
            ("pedrogomez@mi-empresa.mp4", "p***@***.mp4"),
        ],
    )
    def test_path_email_v6_a_label_whose_first_stretch_is_2_letters_is_masked(
        self, name: str, masked: str
    ) -> None:
        shown = mask_text(name)
        assert shown == masked and "pedrogomez" not in shown and "maria" not in shown

    @pytest.mark.parametrize("name", ["yo-8095551234", "yo_8095551234", "ab-809-555-1234"])
    def test_path_email_v6_the_phone_glued_to_a_two_letter_label_leaves_no_digit(
        self, name: str
    ) -> None:
        shown = mask_text(f"pedrogomez@{name}.mp4")
        assert shown == "p***@***.mp4"
        assert not any(ch.isdigit() for ch in shown.removesuffix(".mp4"))

    @pytest.mark.parametrize(
        "name",
        [
            "logo@2x.png",
            "lunes@10am.mp4",
            "foto@v2.mp4",
            "crudo/pedrogomez@a-2026.mp4",  # the first stretch is 1 letter
            "crudo/pedrogomez@a_2026.mp4",
            "crudo/pedrogomez@a1.mp4",
            "crudo/pedrogomez@ab1.mp4",  # no `-` or `_`: the stretch is the label, with a digit
            "crudo/pedrogomez@2a-ab.mp4",  # the first stretch begins with a digit
            "crudo/pedrogomez@a-.mp4",
            "crudo/@yo-2026.mp4",  # no local part
        ],
    )
    def test_path_email_v6_what_is_not_2_letters_before_the_hyphen_does_not_change(
        self, name: str
    ) -> None:
        assert mask_text(name) == name

    def test_path_email_v6_the_masker_alone_follows_the_same_rule(self) -> None:
        assert mask_bare_domains("pedro@yo-2026") == "p***@***"
        assert mask_bare_domains("pedro@yo_8095551234") == "p***@***"
        assert mask_bare_domains("pedro@mi-2") == "p***@***"
        assert mask_bare_domains("foto@v2") == "foto@v2"
        assert mask_bare_domains("pedro@a-2026") == "pedro@a-2026"
        assert mask_bare_domains("pedro@2x-yo") == "pedro@2x-yo"
