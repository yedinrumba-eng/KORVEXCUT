"""PII in file names, S1.6b round 2 (spec 001.32, point 4, row 35): in a path (`parts=True`) the
extension that is left out has to carry a letter, as in row 25: `.mp4` and `.3gp` are extensions,
`.1234` is not. So `Maria 809.555.1234`, `809.555.1234` as a file name and `Maria 809.555.1234.mp4`
leave no digit of the phone but its last two, as `809-555-1234.mp4` does. What is not a path (the
text without `parts`, the words of a transcript) is not touched in this round: the dots are also
the thousands separator in Spanish, and masking them is a product decision for Gate 1 of spec 002.
The last test only records what those two give today, so that nothing changes by accident.

Collected from `test_pii_pack.py` (through `pii_cases_paths.py`), which is at the 300-line limit.
"""

import pytest

from kcut.pack import pii, pii_written
from kcut.pack.pii import mask_pii, mask_text
from kcut.transcribe.model import Word

__all__ = ["TestPiiFileExtShared", "TestPiiPathDottedPhone"]


class TestPiiPathDottedPhone:
    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("Maria 809.555.1234", "Maria ***.***.**34"),
            ("809.555.1234", "***.***.**34"),
            ("Maria 809.555.1234.mp4", "Maria ***.***.**34.mp4"),
            ("crudo/Maria 809.555.1234", "crudo/Maria ***.***.**34"),
            ("crudo/809.555.1234", "crudo/***.***.**34"),
        ],
    )
    def test_path_dotted_phone_is_masked_as_the_hyphenated_one_is(
        self, name: str, masked: str
    ) -> None:
        assert mask_text(name) == masked
        assert mask_text(name, parts=True) == masked
        hyphenated = name.replace("809.555.1234", "809-555-1234")
        assert mask_text(hyphenated) == masked.replace("***.***.**34", "***-***-**34")

    @pytest.mark.parametrize(
        ("name", "masked"),
        [
            ("GX010123.MP4", "GX010123.MP4"),
            ("clip.3gp", "clip.3gp"),
            ("VID_20261025_143015.mp4", "VID_******25_143015.mp4"),
            ("juan@gmail.com", "j***@***.com"),
            ("lunes@10am.mp4", "lunes@10am.mp4"),
            ("clip.1234", "clip.1234"),
            ("foto.12345", "foto.12345"),
        ],
    )
    def test_path_dotted_phone_what_it_gave_it_gives(self, name: str, masked: str) -> None:
        assert mask_text(name) == masked

    @pytest.mark.parametrize("ext", [".mp4", ".MP4", ".3gp", ".m4a", ".wav", ".a1", ".1a", ".webm"])
    def test_path_dotted_phone_an_extension_with_a_letter_is_left_out(self, ext: str) -> None:
        assert mask_text(f"clip{ext}") == f"clip{ext}"
        assert mask_text(f"Maria 809.555.1234{ext}") == f"Maria ***.***.**34{ext}"

    @pytest.mark.parametrize("last", ["1234", "12345", "0001"])
    def test_path_dotted_phone_a_last_part_of_digits_is_not_an_extension(self, last: str) -> None:
        """`.1234` used to be set aside as an extension, and a phone number that ended in it was
        read without its last four digits."""
        shown = mask_text(f"Maria 809.555.{last}")
        assert shown.startswith("Maria ***.***.")
        assert "809" not in shown and "555" not in shown

    def test_path_dotted_phone_the_text_without_parts_and_the_words_are_not_touched(self) -> None:
        """What these give today, recorded and not changed (001.32, point 4): the dots of a number
        are read as separators there, `1.500.000` included. Gate 1 of spec 002 decides."""
        assert mask_text("Maria 809.555.1234", parts=False) == "Maria ***.***.**34"
        word = Word("a1:w0000", 0, "809.555.1234", 0, 500, 0.9)
        shown, ids = mask_pii([word])
        assert [w.text for w in shown] == ["***.***.**34"] and ids == {"a1:w0000"}
        assert mask_text("1.500.000", parts=False) == "*.***.*00"


class TestPiiFileExtShared:
    """001.33, point 7 (row 15): the regex of the extension of a file lives once, in
    `pii_written.FILE_EXT`, and `pii.py` imports it instead of keeping a copy. Two copies that
    nothing tied together could drift apart: rows 25, 34 and 35 depend on both being the same."""

    def test_file_ext_shared_pii_uses_the_one_of_pii_written(self) -> None:
        assert pii._EXTENSION is pii_written.FILE_EXT

    def test_file_ext_shared_it_is_public_and_the_old_private_copy_is_gone(self) -> None:
        assert not hasattr(pii_written, "_FILE_EXT")
        assert pii_written.FILE_EXT.pattern == r"\.(?=[A-Za-z0-9]{0,4}[A-Za-z])[A-Za-z0-9]{1,5}$"

    @pytest.mark.parametrize(
        ("name", "is_ext"),
        [(".mp4", True), (".3gp", True), (".1234", False), (".5551", False), (".abcdef", False)],
    )
    def test_file_ext_shared_a_letter_is_what_makes_it_an_extension(
        self, name: str, is_ext: bool
    ) -> None:
        assert (pii_written.FILE_EXT.search(name) is not None) is is_ext
