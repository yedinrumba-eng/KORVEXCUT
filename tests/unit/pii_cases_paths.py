"""PII in file names, round 6 (spec 001.18, point 4): a pass over the digits that separators cut.

Collected from `test_pii_pack.py`.
"""

import pytest

from kcut.pack.pii import mask_text

__all__ = [
    "TestPiiPathContiguous",
    "TestPiiPathEmail",
    "TestPiiPathJoiners",
    "TestPiiPathUnderscoreV2",
]


class TestPiiPathContiguous:
    """Besides the pass by parts, one pass over the digits of the name with `- _ .` read as spaces,
    so a number cut by separators is masked and camera names stay distinguishable."""

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("809-555-1234.mp4", "***-***-**34.mp4"),
            ("Maria_809_555_1234.mp4", "Maria_***_***_**34.mp4"),
            ("(809) 555-1234.mp4", "(***) ***-**34.mp4"),
            ("4111-1111-1111-1111.mp4", "****-****-****-**11.mp4"),
            ("crudo/809-555-1234.mp4", "crudo/***-***-**34.mp4"),
            ("crudo/cam a/809.555.1234.mov", "crudo/cam a/***.***.**34.mov"),
        ],
    )
    def test_path_contiguous_a_number_cut_by_separators_is_masked(
        self, name: str, masked: str
    ) -> None:
        assert mask_text(name) == masked

    def test_path_contiguous_camera_names_stay_distinguishable(self) -> None:
        assert mask_text("GX010123.MP4") == "GX010123.MP4"
        first = mask_text("VID_20261025_143015.mp4")
        second = mask_text("VID_20261025_150215.mp4")
        assert first == "VID_******25_143015.mp4" and second == "VID_******25_150215.mp4"
        assert mask_text("IMG_1234_5678.mp4") == "IMG_****_**78.mp4"  # eight digits in two parts

    def test_path_contiguous_what_the_parts_pass_masked_stays_as_it_was(self) -> None:
        # 001.20: the hyphens join the groups, so only the last two digits of the ID stay
        assert mask_text("Juan Perez 001-1234567-8.mp4") == "Juan Perez ***-******7-8.mp4"
        assert mask_text("crudo/Juan 809 555 1234.mp4") == "crudo/Juan *** *** **34.mp4"

    def test_path_contiguous_six_digits_in_all_are_not_a_number(self) -> None:
        for name in ("clip_123_456.mp4", "IMG-12-34-56.mov", "a.12.34.56.wav"):
            assert mask_text(name) == name

    def test_path_contiguous_digits_in_two_folders_are_not_joined(self) -> None:
        assert mask_text("crudo/809-555/1234.mp4") == "crudo/809-555/1234.mp4"

    def test_path_contiguous_a_name_read_whole_is_not_read_by_parts(self) -> None:
        assert mask_text("809-555-1234", parts=False) == "***-***-**34"


class TestPiiPathJoiners:
    """001.20 point 8: between digits `-`, `.`, `(`, `)` and a space ALWAYS join the groups of a
    name; `_` joined only groups of 4 digits or fewer, so a phone with `_` was one number and a
    date of 8 digits next to a time was not. 001.21 (point 3): `_` joins groups of any size, but a
    date; see `TestPiiPathUnderscoreV2`."""

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("001-1234567-8.mov", "***-******7-8.mov"),  # only the last two digits stay
            ("cedula 001 1234567 8.jpg", "cedula *** ******7 8.jpg"),
            ("001.1234567.8.mov", "***.******7.8.mov"),
            ("Maria_809_555_1234.mp4", "Maria_***_***_**34.mp4"),
            ("Juan_Perez_cel_809_555_1234_v2.mp4", "Juan_Perez_cel_***_***_**34_v2.mp4"),
            ("1-809-555-1234.mp4", "*-***-***-**34.mp4"),
            ("(809) 555-1234.mp4", "(***) ***-**34.mp4"),
            ("809.555.1234.mov", "***.***.**34.mov"),
            ("IMG_1234_5678.mp4", "IMG_****_**78.mp4"),
            (
                "2026-10-25.mp4",
                "****-**-25.mp4",
            ),  # eight digits joined by hyphens: too much, not too little
        ],
    )
    def test_path_joiners_always_join_and_the_underscore_joins_short_groups(
        self, name: str, masked: str
    ) -> None:
        assert mask_text(name) == masked

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("VID_20261025_143015.mp4", "VID_******25_143015.mp4"),
            ("VID_20261025_150215.mp4", "VID_******25_150215.mp4"),
            ("IMG_12345_678.mp4", "IMG_*****_*78.mp4"),  # 001.21: `_` joins a group of 5 too
            ("IMG_8095551234_7.mov", "IMG_*********4_7.mov"),  # 001.21: and the 7 after it
        ],
    )
    def test_path_joiners_the_underscore_does_not_join_a_long_group(
        self, name: str, masked: str
    ) -> None:
        assert mask_text(name) == masked

    def test_path_joiners_camera_names_stay_distinguishable(self) -> None:
        first = mask_text("crudo/VID_20261025_143015.mp4")
        second = mask_text("crudo/VID_20261025_150215.mp4")
        assert first != second and mask_text("GX010123.MP4") == "GX010123.MP4"

    def test_path_joiners_a_folder_is_a_path_apart(self) -> None:
        assert mask_text("crudo/809-555/1234.mp4") == "crudo/809-555/1234.mp4"


class TestPiiPathUnderscoreV2:
    """001.21 point 3: in a name `_` ALWAYS joins the groups of digits it sits between, except
    when one of the two is a date, `(19|20)` and six more digits (YYYYMMDD)."""

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("amex_3782_822463_10005.png", "amex_****_******_***05.png"),
            ("Maria_80955_51234.mp4", "Maria_*****_***34.mp4"),
            ("809555_1234.mp4", "******_**34.mp4"),
            ("cedula_001_1234567_8.jpg", "cedula_***_******7_8.jpg"),
            ("IMG_12345_678.mp4", "IMG_*****_*78.mp4"),
            ("IMG_8095551234_7.mov", "IMG_*********4_7.mov"),
            ("crudo/Maria_8095_551234.mp4", "crudo/Maria_****_****34.mp4"),
        ],
    )
    def test_path_underscore_v2_joins_groups_of_any_size(self, name: str, masked: str) -> None:
        assert mask_text(name) == masked

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("VID_20261025_143015.mp4", "VID_******25_143015.mp4"),
            ("VID_20261025_150215.mp4", "VID_******25_150215.mp4"),
            ("crudo/VID_19991231_143015.mp4", "crudo/VID_******31_143015.mp4"),
        ],
    )
    def test_path_underscore_v2_a_date_does_not_join_and_the_time_stays_readable(
        self, name: str, masked: str
    ) -> None:
        assert mask_text(name) == masked

    def test_path_underscore_v2_eight_digits_that_are_no_date_are_a_number(self) -> None:
        for name in ("VID_30261025_143015.mp4", "VID_18261025_143015.mp4"):
            assert "143015" not in mask_text(name)  # 3026... is no date: it joins the time

    def test_path_underscore_v2_the_other_separators_did_not_change(self) -> None:
        assert mask_text("clip_123_456.mp4") == "clip_123_456.mp4"  # six digits are not a number
        assert mask_text("809-555-1234.mp4") == "***-***-**34.mp4"
        assert mask_text("crudo/809_555/1234.mp4") == "crudo/809_555/1234.mp4"  # two folders


class TestPiiPathEmail:
    """001.21 point 4: an address written in a name is masked on the whole folder or file name,
    before it is cut at `_ . -`; what follows is read as digits and words as it always was."""

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("crudo/contrato_juan@gmail.com.mp4", "crudo/c***@***.com.mp4"),
            ("crudo/juan.perez@gmail.com/clip.mp4", "crudo/j***@***.com/clip.mp4"),
            ("juan-perez@empresa.com.do.mov", "j***@***.com.do.mov"),
            (
                "crudo/cam a/maria_lopez@correo.org/GX010123.MP4",
                "crudo/cam a/m***@***.org/GX010123.MP4",
            ),
        ],
    )
    def test_path_email_the_address_in_a_name_is_masked(self, name: str, masked: str) -> None:
        assert mask_text(name) == masked

    def test_path_email_nothing_of_the_address_stays_in_any_part(self) -> None:
        shown = mask_text("crudo/contrato_juan.perez@gmail.com.mp4")
        assert "juan" not in shown and "perez" not in shown and "gmail" not in shown

    def test_path_email_what_follows_the_address_is_still_masked_as_a_number(self) -> None:
        shown = mask_text("juan@gmail.com_8095551234.mp4")
        assert "8095551234" not in shown and "809" not in shown and "juan" not in shown

    def test_path_email_a_name_with_an_at_and_no_domain_is_left_as_it_is(self) -> None:
        assert mask_text("crudo/lunes@10am.mp4") == "crudo/lunes@10am.mp4"
