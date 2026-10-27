"""PII in file names, S1.6b round 1 (spec 001.31, point 7, row 25): the digits of a phone number are
counted through the separators. If what follows the `@`, up to the end of that stretch of the path
(without the extension, if it is the file name), has 7 digits in a row once `-`, `_`, `.`, `+` and
spaces are taken out, the address is masked as in row 17 (`<first>***@***`), so a phone number
cut by separators leaves neither a digit nor the name. `foto@2026-10-27` (a date) is masked too:
masking too much is the safe side. The cases of rows 17, 18 and 25 of S1.6a give what they gave.

Collected from `test_pii_pack.py` (through `pii_cases_paths.py`), which is at the 300-line limit.
"""

import time

import pytest

from kcut.pack.pii import mask_text
from kcut.pack.pii_written import mask_bare_domains

__all__ = ["TestPiiPathEmailV8"]


class TestPiiPathEmailV8:
    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("pedro@g-809-555-1234.mp4", "p***@***.mp4"),
            ("pedro@g_809_555_1234.mov", "p***@***.mov"),
            ("pedro@g.8095551234.mp4", "p***@***.mp4"),
            ("pedro@2g-809-555-1234.mp4", "p***@***.mp4"),
            ("pedro@g 809 555 1234.mp4", "p***@***.mp4"),
            ("pedro@g+809+555+1234.mp4", "p***@***.mp4"),
            ("pedro@g.809.555.1234.mp4", "p***@***.mp4"),
            ("pedro@g-123-4567.mp4", "p***@***.mp4"),  # exactly 7 digits
            ("foto@2026-10-27.mp4", "f***@***.mp4"),  # a date: too much is the safe side
            ("crudo/pedro@g-809-555-1234.mp4", "crudo/p***@***.mp4"),
            ("crudo/pedro@g-809-555-1234/clip.mp4", "crudo/p***@***/clip.mp4"),
        ],
    )
    def test_path_email_v8_a_phone_cut_by_separators_is_masked(
        self, name: str, masked: str
    ) -> None:
        assert mask_text(name) == masked

    @pytest.mark.parametrize(
        "name",
        [
            "pedro@g-809-555-1234.mp4",
            "pedro@g_809_555_1234.mov",
            "pedro@g.8095551234.mp4",
            "pedro@2g-809-555-1234.mp4",
        ],
    )
    def test_path_email_v8_the_phone_leaves_no_digit_and_the_name_leaves_no_trace(
        self, name: str
    ) -> None:
        shown = mask_text(name)
        assert shown == "p***@***." + name.rsplit(".", 1)[1]
        assert not any(ch.isdigit() for ch in shown.rsplit(".", 1)[0])
        assert "pedro" not in shown

    def test_path_email_v8_a_dotted_local_part_leaves_neither_name_nor_digit(self) -> None:
        shown = mask_text("maria.lopez@g-809-555-1234.mp4")
        assert shown == "m***@***.mp4"
        assert not any(piece in shown for piece in ("maria", "lopez", "809", "555", "1234"))

    @pytest.mark.parametrize(
        "name",
        [
            "logo@2x.png",
            "lunes@10am.mp4",
            "foto@v2.mp4",
            "pedro@y-o-2026.mp4",
            "crudo/pedro@a-2026.mp4",
            "crudo/pedro@g-123456.mp4",  # 6 digits: not a phone number
            "pedro@g-123-456.mp4",  # 6 digits through the hyphens
            "pedro@g-123456.3gp",  # the digit of the extension is not counted
        ],
    )
    def test_path_email_v8_what_has_no_run_of_7_digits_does_not_change(self, name: str) -> None:
        assert mask_text(name) == name

    def test_path_email_v8_the_cases_of_rows_17_18_and_25_give_what_they_gave(self) -> None:
        assert mask_text("pedro@g-8095551234.mp4") == "p***@***.mp4"
        assert mask_text("pedro@g_8095551234.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@gmail_2026.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@empresa-v2.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@hotmail2.mp4") == "p***@***.mp4"
        assert mask_text("clip@take3.mp4") == "c***@***.mp4"
        assert mask_text("pedrogomez@gmail-8095551234.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@yo-8095551234.mp4") == "p***@***.mp4"
        assert mask_text("pedrogomez@yo-2026.mp4") == "p***@***.mp4"
        assert mask_text("maria.lopez@ab-2026.mp4") == "m***@***.mp4"
        assert mask_text("pedrogomez@mi-empresa.mp4") == "p***@***.mp4"

    def test_path_email_v8_the_masker_alone_follows_the_same_rule(self) -> None:
        assert mask_bare_domains("pedro@g-809-555-1234") == "p***@***"
        assert mask_bare_domains("pedro@g.8095551234") == "p***@***"
        assert mask_bare_domains("pedro@g-123-456") == "pedro@g-123-456"
        assert mask_bare_domains("@g-809-555-1234") == "@g-809-555-1234"  # no local part
        assert mask_bare_domains("foto@v2") == "foto@v2"
        # as a file name, the extension does not count; what is left of it stays
        assert mask_bare_domains("pedro@g-123456.3gp") == "pedro@g-123456.3gp"
        assert mask_bare_domains("pedro@g-809-555-1234.mp4") == "p***@***.mp4"

    def test_path_email_v8_a_stretch_of_the_path_ends_at_the_slash(self) -> None:
        """The digits of the next folder are not the phone number of this one."""
        assert mask_bare_domains("pedro@g-123/4567/x") == "pedro@g-123/4567/x"
        assert mask_bare_domains("pedro@g-809-555/1234/x") == "pedro@g-809-555/1234/x"

    def test_path_email_v8_many_at_signs_are_still_read_in_linear_time(self) -> None:
        """Each `@` used to be looked at once, with a bounded look: the digits after it are counted
        once for the stretch, not once for each `@` (no quadratic cost)."""
        text = "a@" * 20_000 + "g-12-12"  # 4 digits at the end: no `@` of it is a phone number
        started = time.perf_counter()
        assert mask_bare_domains(text) == text
        assert time.perf_counter() - started < 5.0
