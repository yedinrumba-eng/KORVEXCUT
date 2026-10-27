"""No control character hides in the code (spec 001.29, point 2; row 30).

A heredoc has turned a `\\b` of a regular expression into the character 0x08 three times: the file
looked right and the rule never found anything. A `.py`, `.js` or `.css` of `src/` or `tests/` that
has a character of the Unicode category `Cc` (the C0 and C1 controls and DEL) other than tab, LF or
CR fails this test, with the list `file:line`. Newlines are only `\\n` here, so a line number is the
one an editor shows.
"""

import unicodedata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TREES = ("src", "tests")
SUFFIXES = (".py", ".js", ".css")
ALLOWED = frozenset("\t\n\r")


def control_characters(path: Path) -> list[str]:
    """`file:line` of every control character in `path` (the same line may be listed twice)."""
    text = path.read_text(encoding="utf-8")
    found: list[str] = []
    for number, line in enumerate(text.split("\n"), start=1):
        found += [
            f"{path.as_posix()}:{number}"
            for ch in line
            if ch not in ALLOWED and unicodedata.category(ch) == "Cc"
        ]
    return found


def source_files() -> list[Path]:
    return sorted(
        p
        for tree in TREES
        for p in (ROOT / tree).rglob("*")
        if p.suffix in SUFFIXES and p.is_file() and "__pycache__" not in p.parts
    )


def test_source_bytes_it_looks_at_the_code_of_both_trees() -> None:
    files = source_files()
    names = {p.relative_to(ROOT).as_posix() for p in files}
    assert "src/kcut/paths.py" in names and "tests/unit/test_source_bytes.py" in names
    assert "src/kcut/gfx/web/runtime.js" in names and "src/kcut/gfx/web/base.css" in names


def test_source_bytes_no_control_character_in_any_py_js_or_css_of_src_and_tests() -> None:
    found = [place for path in source_files() for place in control_characters(path)]
    shown = [place.removeprefix(ROOT.as_posix() + "/") for place in found]
    assert shown == [], f"caracteres de control en: {shown}"


@pytest.mark.parametrize(
    ("char", "name"),
    [
        ("\x08", "backspace"),
        ("\x00", "NUL"),
        ("\x0b", "VT"),
        ("\x0c", "FF"),
        ("\x7f", "DEL"),
        ("\x85", "NEL, a C1 control"),
        ("\x9b", "CSI, a C1 control"),
    ],
)
def test_source_bytes_the_scan_finds_a_control_character_and_says_where(
    tmp_path: Path, char: str, name: str
) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(f"first = 1\nsecond = r'a{char}b'\nthird = 3\n", encoding="utf-8")
    assert control_characters(planted) == [f"{planted.as_posix()}:2"], name


def test_source_bytes_tab_lf_and_cr_are_fine_and_other_text_is_not_flagged(tmp_path: Path) -> None:
    planted = tmp_path / "fine.js"
    planted.write_bytes("a\tb\r\nc\n// ñandú —     ok\n".encode())
    assert control_characters(planted) == []
