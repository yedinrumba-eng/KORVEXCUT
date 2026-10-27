"""Every text file kcut or its tests open says its encoding (S1.6a step 0, 001.27 point 2, row 13).

Windows opens text with the code page of the machine unless told otherwise, so a test that writes
`kcut.toml` with `write_text` and no `encoding=` passes with `-X utf8` and fails without it (001.26
point 13). This test walks the AST of `src/` and `tests/` and fails with the list `file:line` of
every call to `open`, `.open`, `.read_text` or `.write_text` that has no `encoding=` keyword.

What does not need one:
- an `open` / `.open` call with a literal mode that has a `b` in it (`"rb"`, `"wb"`, `"xb"`): a
  binary file has no encoding;
- `os.open` (a file descriptor, with flags) and Pillow's `Image.open` (an image): they open no
  text, and they take no `encoding` argument at all.
"""

import ast
from functools import cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TREES = ("src", "tests")
TEXT_METHODS = frozenset({"read_text", "write_text"})
MODE_LETTERS = frozenset("rwxabt+U")
NOT_TEXT_OPENERS = frozenset({"os", "Image", "PIL.Image"})  # `os.open(...)`, `Image.open(...)`


def _is_binary_mode(node: ast.Call) -> bool:
    """Does the call say, with a literal, that it opens the file in binary mode?"""
    modes = [a.value for a in node.args if isinstance(a, ast.Constant)]
    modes += [
        k.value.value
        for k in node.keywords
        if k.arg == "mode" and isinstance(k.value, ast.Constant)
    ]
    return any(
        isinstance(m, str) and m != "" and set(m) <= MODE_LETTERS and "b" in m for m in modes
    )


def _needs_encoding(node: ast.Call) -> bool:
    func = node.func
    name = (
        func.id
        if isinstance(func, ast.Name)
        else func.attr
        if isinstance(func, ast.Attribute)
        else ""
    )
    if name in TEXT_METHODS:
        return not any(k.arg == "encoding" for k in node.keywords)
    if name != "open" or any(k.arg == "encoding" for k in node.keywords):
        return False
    if isinstance(func, ast.Attribute) and ast.unparse(func.value) in NOT_TEXT_OPENERS:
        return False
    return not _is_binary_mode(node)


def lines_without_encoding(source: str) -> list[int]:
    """The lines of the calls in `source` that open text and do not say its encoding."""
    return sorted(
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and _needs_encoding(node)
    )


@cache
def offenders() -> tuple[str, ...]:
    found: list[str] = []
    for tree in TREES:
        for path in sorted((ROOT / tree).rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            found += [
                f"{path.relative_to(ROOT).as_posix()}:{n}" for n in lines_without_encoding(source)
            ]
    return tuple(found)


def test_text_encoding_every_text_call_in_src_and_tests_says_its_encoding() -> None:
    assert list(offenders()) == [], "faltan encoding= en:\n" + "\n".join(offenders())


class TestTheChecker:
    """The AST walk itself: what it flags and what it lets through."""

    def test_text_encoding_checker_flags_a_call_with_no_encoding(self) -> None:
        source = "\n".join(
            [
                'open("a.txt")',  # 1
                "p.open()",  # 2
                'p.open("w")',  # 3
                "p.read_text()",  # 4
                'p.write_text("x")',  # 5
                'open("a.txt", "r")',  # 6
                'p.read_text("utf-8")',  # 7: positional, the rule asks for `encoding=`
                "p.open(mode=mode)",  # 8: a mode that is not a literal
                'open("tab.txt")',  # 9: the `b` of the name is not a mode
            ]
        )
        assert lines_without_encoding(source) == [1, 2, 3, 4, 5, 6, 7, 8, 9]

    def test_text_encoding_checker_lets_through_a_call_with_encoding(self) -> None:
        source = "\n".join(
            [
                'open("a.txt", encoding="utf-8")',
                'p.open("w", encoding="utf-8", newline="\\n")',
                'p.read_text(encoding="utf-8")',
                'p.write_text("x", encoding="utf-8")',
            ]
        )
        assert lines_without_encoding(source) == []

    def test_text_encoding_checker_lets_through_a_binary_mode_with_a_literal(self) -> None:
        source = "\n".join(
            [
                'open("a.bin", "rb")',
                'p.open("wb")',
                'p.open("xb")',
                'p.open(mode="rb")',
                'wave.open(str(p), "rb")',
                'open("a.bin", "r+b")',
            ]
        )
        assert lines_without_encoding(source) == []

    def test_text_encoding_checker_lets_through_the_openers_that_open_no_text(self) -> None:
        source = "\n".join(
            [
                "os.open(path, os.O_RDWR | os.O_CREAT, 0o644)",
                "Image.open(path)",
                "PIL.Image.open(path)",
            ]
        )
        assert lines_without_encoding(source) == []

    def test_text_encoding_checker_still_flags_another_receiver_called_open(self) -> None:
        assert lines_without_encoding("handle.open(path)\nio.open(path)") == [1, 2]
