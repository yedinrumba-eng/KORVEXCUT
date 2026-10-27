"""PII in file names, S1.6b round 2 (spec 001.32, point 3, row 34): only a letter or an `@` cuts the
run of digits of a phone number after an `@`; any other character does not. `~ # ; & = ! ' ,`, the
backslash and the parentheses sit between the digits like a hyphen does, so the phone is masked as
`<first>***@***` and the name goes with it. What the rows of S1.6b (17 and 25) and of S1.6a (18 and
25) did stays as it was.

Collected from `test_pii_pack.py` (through `pii_cases_paths.py`), which is at the 300-line limit.
"""

import pytest

from kcut.pack.pii import mask_text
from kcut.pack.pii_written import mask_bare_domains

__all__ = ["TestPiiPathEmailV9"]


class TestPiiPathEmailV9:
    @pytest.mark.parametrize(
        "separator", ["~", "#", ";", "&", "=", "!", "'", ",", "\\", "$", "%", "^", "|", "{", "}"]
    )
    def test_path_email_v9_a_character_between_the_digits_does_not_cut_the_run(
        self, separator: str
    ) -> None:
        name = f"pedro@g-809{separator}555{separator}1234.mp4"
        assert mask_text(name) == "p***@***.mp4"

    def test_path_email_v9_the_parentheses_do_not_cut_it_either(self) -> None:
        assert mask_text("pedro@g-(809)(555)(1234).mp4") == "p***@***.mp4"
        assert mask_text("pedro@g-(809) (555)-(1234).mov") == "p***@***.mov"

    @pytest.mark.parametrize(
        "name",
        [
            "pedro@g-809~555~1234.mp4",
            "pedro@g-809#555#1234.mp4",
            "pedro@g-809;555;1234.mp4",
            "pedro@g-809&555&1234.mp4",
            "pedro@g-809=555=1234.mp4",
            "pedro@g-809!555!1234.mp4",
            "pedro@g-809'555'1234.mp4",
            "pedro@g-809,555,1234.mp4",
            "pedro@g-809\\555\\1234.mp4",
            "pedro@g-(809)(555)(1234).mp4",
        ],
    )
    def test_path_email_v9_no_digit_and_no_name_is_left(self, name: str) -> None:
        shown = mask_text(name)
        assert shown == "p***@***.mp4"
        assert not any(ch.isdigit() for ch in shown.rsplit(".", 1)[0])
        assert "pedro" not in shown

    @pytest.mark.parametrize(
        "name",
        [
            "logo@2x.png",
            "lunes@10am.mp4",
            "foto@v2.mp4",
            "pedro@y-o-2026.mp4",
            "pedro@g-123-456.mp4",
            "pedro@g-123~456.mp4",  # 6 digits with a character that does not cut: still 6
            "pedro@g-(123)(456).mp4",
        ],
    )
    def test_path_email_v9_what_has_no_run_of_7_digits_does_not_change(self, name: str) -> None:
        assert mask_text(name) == name

    def test_path_email_v9_a_letter_cuts_the_run_for_the_masker_alone(self) -> None:
        assert mask_bare_domains("pedro@g-809a555a1234") == "pedro@g-809a555a1234"
        assert mask_bare_domains("pedro@g-809-555x1234") == "pedro@g-809-555x1234"
        # an `@` cuts it too: 6 digits before it and 4 after are not a run of 7
        assert mask_bare_domains("pedro@g-809-555@1234") == "pedro@g-809-555@1234"
        assert mask_bare_domains("pedro@g-809~555~1234") == "p***@***"
        assert mask_bare_domains("pedro@g-(809)(555)(1234)") == "p***@***"

    def test_path_email_v9_the_cases_of_rows_17_and_25_give_what_they_gave(self) -> None:
        assert mask_text("pedro@g-8095551234.mp4") == "p***@***.mp4"
        assert mask_text("pedro@g-809-555-1234.mp4") == "p***@***.mp4"
        assert mask_text("pedro@g_809_555_1234.mov") == "p***@***.mov"
        assert mask_text("pedro@g.8095551234.mp4") == "p***@***.mp4"
        assert mask_text("pedro@2g-809-555-1234.mp4") == "p***@***.mp4"
        assert mask_text("pedro@g 809 555 1234.mp4") == "p***@***.mp4"
        assert mask_text("pedro@g+809+555+1234.mp4") == "p***@***.mp4"
        assert mask_text("foto@2026-10-27.mp4") == "f***@***.mp4"
        assert mask_text("maria.lopez@g-809-555-1234.mp4") == "m***@***.mp4"
        assert mask_text("pedrogomez@yo-2026.mp4") == "p***@***.mp4"
        assert mask_text("clip@take3.mp4") == "c***@***.mp4"
