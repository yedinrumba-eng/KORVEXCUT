"""PII in file names, S1.6b step 0 (spec 001.30, point 5, row 17): a label that carries a phone
number, 7 digits in a row, is an address even if its first stretch is a single letter
(`pedro@g-8095551234`). Everything the rows of S1.6a (18 and 25) did stays as it was.

Collected from `test_pii_pack.py` (through `pii_cases_paths.py`), which is at the 300-line limit.
"""

import pytest

from kcut.pack.pii import mask_text
from kcut.pack.pii_written import mask_bare_domains

__all__ = ["TestPiiPathEmailV7"]


class TestPiiPathEmailV7:
    """001.30 point 5: besides the labels of rows 18 and 25, a label with 7 digits or more in a
    row is masked as `<first>***@***`, whatever comes before them. `logo@2x`, `lunes@10am`,
    `foto@v2` and `pedro@y-o-2026` do not change."""

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("pedro@g-8095551234.mp4", "p***@***.mp4"),
            ("pedro@g_8095551234.mp4", "p***@***.mp4"),
            ("pedro@y-8095551234-final.mov", "p***@***.mov"),
            ("pedro@8095551234.mp4", "p***@***.mp4"),
            ("pedro@2x-8095551234.mp4", "p***@***.mp4"),
            ("pedro@a1-5551234.mp4", "p***@***.mp4"),  # exactly 7 digits
            ("crudo/pedro@g-8095551234.mp4", "crudo/p***@***.mp4"),
            ("crudo/pedro@g-8095551234/clip.mp4", "crudo/p***@***/clip.mp4"),
        ],
    )
    def test_path_email_v7_a_label_with_a_phone_number_is_masked(
        self, name: str, masked: str
    ) -> None:
        shown = mask_text(name)
        assert shown == masked

    @pytest.mark.parametrize(
        "name",
        ["pedro@g-8095551234.mp4", "pedro@g_8095551234.mp4", "pedro@8095551234.mp4"],
    )
    def test_path_email_v7_the_phone_leaves_no_digit_and_the_name_leaves_no_trace(
        self, name: str
    ) -> None:
        shown = mask_text(name)
        assert shown == "p***@***.mp4"
        assert not any(ch.isdigit() for ch in shown.removesuffix(".mp4"))
        assert "pedro" not in shown

    @pytest.mark.parametrize(
        "name",
        [
            "logo@2x.png",
            "lunes@10am.mp4",
            "foto@v2.mp4",
            "pedro@y-o-2026.mp4",  # one letter before the first hyphen, and only 4 digits
            "crudo/pedro@a-2026.mp4",
            "crudo/pedro@g-123456.mp4",  # 6 digits: not a phone number
        ],
    )
    def test_path_email_v7_what_has_no_phone_number_and_no_earlier_rule_does_not_change(
        self, name: str
    ) -> None:
        assert mask_text(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "@g-8095551234",  # no local part
            "pedro@g-123-456",  # 001.31: 6 digits through the hyphens: not a phone number
        ],
    )
    def test_path_email_v7_the_masker_leaves_a_label_with_no_local_part_or_under_7_digits(
        self, name: str
    ) -> None:
        """The numbers pass of `mask_text` still hides the digits of these: the new rule is the
        masker's, and it is the masker alone that is looked at here."""
        assert mask_bare_domains(name) == name

    @pytest.mark.parametrize(
        "name",
        [
            "pedro@g-809-555-1234",  # 001.31: this one was left (7 digits, never 7 in a row)
            "pedro@g-123-4567",  # 001.31: and this one; 7 digits through the hyphens is a phone
        ],
    )
    def test_path_email_v7_the_masker_takes_7_digits_through_separators_since_001_31(
        self, name: str
    ) -> None:
        """Before 001.31 the masker left these (a leak with separators: the digits were masked
        by the numbers pass, and `pedro` stayed). Row 25 of S1.6b round 1 masks them: 001.31,
        point 7."""
        assert mask_bare_domains(name) == "p***@***"

    def test_path_email_v7_the_cases_of_rows_18_and_25_give_what_they_gave(self) -> None:
        assert mask_text("pedrogomez@gmail_2026.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@empresa-v2.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@hotmail2.mp4") == "p***@***.mp4"
        assert mask_text("clip@take3.mp4") == "c***@***.mp4"
        assert mask_text("pedrogomez@gmail-8095551234.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@yo-8095551234.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@yo-2026.mp4") == "p***@***.mp4"
        assert mask_text("maria.lopez@ab-2026.mp4") == "m***@***.mp4"
        assert mask_text("pedrogomez@mi-empresa.mp4") == "p***@***.mp4"

    def test_path_email_v7_the_masker_alone_follows_the_same_rule(self) -> None:
        assert mask_bare_domains("pedro@g-8095551234") == "p***@***"
        assert mask_bare_domains("pedro@8095551234") == "p***@***"
        assert mask_bare_domains("pedro@g-123456") == "pedro@g-123456"
        assert mask_bare_domains("pedro@y-o-2026") == "pedro@y-o-2026"
        assert mask_bare_domains("foto@v2") == "foto@v2"
