"""Console hygiene (spec 001.8, point 1): untrusted text never reaches the terminal raw."""

import json
import math
import time
import unicodedata
from pathlib import Path

import pytest

from kcut import cli, console
from kcut.commands import doctor

_ESCAPED_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Cs"}
_TITLE = "\x1b]0;pwned\x07\x1b[2J"
_TITLE_SAFE = "\\x1b]0;pwned\\x07\\x1b[2J"


class TestSafeText:
    @pytest.mark.parametrize(
        ("raw", "safe"),
        [
            ("\x1b", "\\x1b"),
            ("\x07", "\\x07"),
            ("\x7f", "\\x7f"),
            ("\x00", "\\x00"),
            ("\r", "\\x0d"),
            ("\t", "\\x09"),
            ("\x85", "\\x85"),
            ("\x9b", "\\x9b"),
            ("\xad", "\\xad"),
            ("\u200b", "\\u200b"),
            ("\u202e", "\\u202e"),
            ("\u2028", "\\u2028"),
            ("\u2029", "\\u2029"),
            ("\ufeff", "\\ufeff"),
            ("\ud800", "\\ud800"),
            ("\U000e0001", "\\U000e0001"),
        ],
    )
    def test_safe_text_swaps_each_character_for_its_visible_escape(
        self, raw: str, safe: str
    ) -> None:
        assert console.safe_text(f"a{raw}b") == f"a{safe}b"

    def test_safe_text_defangs_a_terminal_title_and_clear_screen(self) -> None:
        assert console.safe_text(_TITLE) == _TITLE_SAFE

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "ñandú áéíóú üÜ ¿qué? ¡hola!",
            "emoji 😀 🎬",
            "日本語 العربية",
            "linea 1\nlinea 2\n",
            "[OK] a1: video_voz - crudo/cam a.mp4 - 12.5 s",
            "ruta C:\\Users\\Yedin\\proyecto ñandú\\crudo",
        ],
    )
    def test_safe_text_leaves_clean_text_byte_identical(self, text: str) -> None:
        assert console.safe_text(text) == text

    def test_safe_text_keeps_the_newline_but_not_the_carriage_return(self) -> None:
        assert console.safe_text("a\r\nb\n") == "a\\x0d\nb\n"

    def test_safe_text_leaves_no_escaped_category_in_the_output(self) -> None:
        sweep = "".join(chr(c) for c in (*range(0x20000), *range(0xE0000, 0xE1000)))
        out = console.safe_text(sweep)
        left = {c for c in out if unicodedata.category(c) in _ESCAPED_CATEGORIES}
        assert left <= {"\n"}
        assert console.safe_text(out) == out  # applying it twice changes nothing


class TestOut:
    def test_console_hygiene_line_goes_through_the_sink(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        console.Out(json_mode=False).line("INFO", "sincronía: maestro a1 (ñandú)")  # clean: same
        console.Out(json_mode=False).line("OK", f"a1: {_TITLE}")
        captured = capsys.readouterr()
        assert captured.out == f"[INFO] sincronía: maestro a1 (ñandú)\n[OK] a1: {_TITLE_SAFE}\n"
        assert captured.err == ""

    def test_console_hygiene_warn_goes_through_the_sink(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        console.Out(json_mode=False).warn("a2: hdr — ñ")  # clean: same
        console.Out(json_mode=False).warn(f"cache_rebuilt: {_TITLE}")
        captured = capsys.readouterr()
        assert captured.err == f"[AVISO] a2: hdr — ñ\n[AVISO] cache_rebuilt: {_TITLE_SAFE}\n"
        assert captured.out == ""

    def test_console_hygiene_json_escapes_every_key_and_value(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        document = {
            f"k{_TITLE}": [f"\x9b{_TITLE}", {"n": "ñ\u202e"}, ("t\x7f", 3)],
            "plain": {"ok": True, "none": None, "n": 7, "f": 1.5, "name": "ñandú\nlínea"},
        }
        console.Out(json_mode=True).result(document)
        out = capsys.readouterr().out
        assert not [c for c in out if c in "\x1b\x07\x7f\u202e" or "\x80" <= c <= "\x9f"]
        assert '"name": "ñandú\\nlínea"' in out and "\\u00f1" not in out  # accents stay as typed
        assert json.loads(out) == {
            f"k{_TITLE_SAFE}": [f"\\x9b{_TITLE_SAFE}", {"n": "ñ\\u202e"}, ["t\\x7f", 3]],
            "plain": {"ok": True, "none": None, "n": 7, "f": 1.5, "name": "ñandú\nlínea"},
        }

    def test_console_hygiene_progress_line_goes_through_the_sink(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        progress = console.Progress(f"ingest{_TITLE}", 2, "pasos")
        progress.update(1)
        progress.close()
        err = capsys.readouterr().err
        assert err.startswith(f"ingest{_TITLE_SAFE}: 1/2 pasos (50%)")
        assert "\x1b" not in err and "\x07" not in err


class TestVariationSelectors:
    """001.10, point 4: variation selectors and private-use characters hide text from a reader."""

    @pytest.mark.parametrize(
        ("raw", "safe"),
        [
            ("\ufe00", "\\ufe00"),
            ("\ufe08", "\\ufe08"),
            ("\ufe0f", "\\ufe0f"),
            ("\U000e0100", "\\U000e0100"),
            ("\U000e0180", "\\U000e0180"),
            ("\U000e01ef", "\\U000e01ef"),
            ("\ue000", "\\ue000"),
            ("\uf8ff", "\\uf8ff"),
            ("\U000f0000", "\\U000f0000"),
            ("\U0010fffd", "\\U0010fffd"),
        ],
    )
    def test_safe_text_variation_selectors_are_escaped(self, raw: str, safe: str) -> None:
        assert console.safe_text(f"a{raw}b") == f"a{safe}b"

    @pytest.mark.parametrize(
        "text",
        [
            "ñandú áéíóú üÜ ¿qué? ¡hola!",
            "emoji 😀 🎬 ❤ 👍",
            "borde \ufe10 \U000e1000 \U000dffff \ufdfd",  # neighbours of the escaped ranges
            "日本語 العربية",
        ],
    )
    def test_safe_text_variation_selectors_leave_clean_text_byte_identical(self, text: str) -> None:
        assert console.safe_text(text) == text

    def test_safe_text_variation_selectors_sweep_leaves_none_behind(self) -> None:
        ranges = (range(0xFE00, 0xFE10), range(0xE0100, 0xE01F0), range(0xE000, 0xF900))
        sweep = "".join(chr(c) for r in ranges for c in r)
        out = console.safe_text(sweep)
        assert out.isascii()
        assert console.safe_text(out) == out  # idempotent


_REFERENCE_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs", "Co"})
_INVISIBLE_FILLERS = (0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800)
_MORE_INVISIBLES = (
    0x034F,
    0x17B4,
    0x17B5,
    0x180B,
    0x180C,
    0x180D,
    0x180F,
    0x2065,
    *range(0xFFF0, 0xFFF9),
    *range(0xE0000, 0xE1000),
)  # fmt: skip  (001.14 point 10)


def _reference_safe_text(text: str) -> str:
    """The character-by-character version of `safe_text`: the definition the fast one must match."""

    def visible(ch: str) -> str:
        code = ord(ch)
        hides = (
            unicodedata.category(ch) in _REFERENCE_CATEGORIES
            or 0xFE00 <= code <= 0xFE0F
            or 0xE0100 <= code <= 0xE01EF
            or code in _INVISIBLE_FILLERS
            or code in _MORE_INVISIBLES
        )
        if ch == "\n" or not hides:
            return ch
        if code <= 0xFF:
            return f"\\x{code:02x}"
        return f"\\u{code:04x}" if code <= 0xFFFF else f"\\U{code:08x}"

    return "".join(visible(ch) for ch in text)


class TestSafeTextFast:
    @pytest.mark.slow  # ~26 s: walks all 0x110000 code points
    def test_safe_text_fast_equals_the_reference_on_every_code_point(self) -> None:
        step = 0x1000
        for start in range(0, 0x110000, step):
            block = "".join(chr(c) for c in range(start, start + step))
            assert console.safe_text(block) == _reference_safe_text(block), hex(start)

    def test_safe_text_fast_each_code_point_alone_matches_too_around_the_edges(self) -> None:
        edges = [0x9, 0xA, 0xB, 0x1F, 0x20, 0x7E, 0x7F, 0x9F, 0xA0, 0xAD, 0xAE, 0x2027, 0x2028]
        edges += [0x202E, 0x202F, 0xD7FF, 0xD800, 0xDFFF, 0xE000, 0xF8FF, 0xF900, 0xFFFF]
        edges += [0x10000, 0xEFFFF, 0xF0000, 0xFFFFD, 0xFFFFE, 0x100000, 0x10FFFD, 0x10FFFF]
        for code in edges:
            assert console.safe_text(chr(code)) == _reference_safe_text(chr(code)), hex(code)

    def test_safe_text_fast_mixed_text_keeps_clean_runs_whole(self) -> None:
        text = "ñandú \x1b[2J ok\n\u202eRLO\u200b fin 😀 \ufe0f"
        assert console.safe_text(text) == _reference_safe_text(text)
        assert console.safe_text(text).startswith("ñandú \\x1b[2J ok\n\\u202eRLO")

    def test_safe_text_fast_is_a_lot_faster_than_a_character_loop(self) -> None:
        text = ("línea de texto normal con acentos ñ y un poco de ruido \x1b[2J " * 10) * 2000
        started = time.monotonic()
        console.safe_text(text)
        assert time.monotonic() - started < 1.0


class TestInvisibleFillers:
    @pytest.mark.parametrize("code", _INVISIBLE_FILLERS)
    def test_safe_text_invisible_fillers_are_escaped(self, code: int) -> None:
        shown = f"\\u{code:04x}"
        assert console.safe_text(f"a{chr(code)}b") == f"a{shown}b"

    def test_safe_text_invisible_fillers_leave_the_non_breaking_space_alone(self) -> None:
        assert console.safe_text("a\u00a0b") == "a\u00a0b"
        assert console.safe_text("a\u3000b\u2003c") == "a\u3000b\u2003c"  # ordinary spaces

    def test_safe_text_invisible_fillers_a_filler_cannot_pose_as_a_blank_name(self) -> None:
        assert console.safe_text("\u3164\u3164") == "\\u3164\\u3164"


class TestJsonNoNan:
    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf], ids=["nan", "inf", "-inf"])
    def test_json_no_nan_result_refuses_the_value_and_prints_nothing(
        self, bad: float, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(ValueError, match="JSON"):
            console.Out(json_mode=True).result({"ok": True, "values": [1, {"x": bad}]})
        assert capsys.readouterr().out == ""

    def test_json_no_nan_in_human_mode_nothing_is_serialized(self) -> None:
        console.Out(json_mode=False).result({"x": math.nan})  # silent: no document, no error

    def test_json_no_nan_the_cli_exits_10_and_stdout_is_one_valid_document(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def run(_args: object) -> int:
            console.Out(json_mode=True).result({"ok": True, "score": math.nan})
            return 0

        monkeypatch.setattr(doctor, "run", run)
        assert cli.main(["doctor", "--json"]) == 10
        out = capsys.readouterr().out
        assert "NaN" not in out and "Infinity" not in out
        assert json.loads(out)["error"]["exit_code"] == 10

    def test_json_no_nan_ordinary_numbers_still_print(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        console.Out(json_mode=True).result({"a": 1, "b": 1.5, "c": None, "d": [True]})
        assert json.loads(capsys.readouterr().out) == {"a": 1, "b": 1.5, "c": None, "d": [True]}


class TestMoreInvisibles:
    @pytest.mark.parametrize(
        "code",
        [
            *(0x034F, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180F, 0x2065),
            *(0xFFF0, 0xFFF4, 0xFFF8),
            *(0xE0000, 0xE0001, 0xE0020, 0xE007F, 0xE0100, 0xE01EF, 0xE01F0, 0xE0800, 0xE0FFF),
        ],
    )
    def test_more_invisibles_are_escaped(self, code: int) -> None:
        escaped = f"\\U{code:08x}" if code > 0xFFFF else f"\\u{code:04x}"
        assert console.safe_text(f"a{chr(code)}b") == f"a{escaped}b"

    @pytest.mark.parametrize(
        "code",
        [0x034E, 0x0350, 0x17B3, 0x17B6, 0x180A, 0x180E, 0x2064, 0xFFEF, 0xFFF9, 0xE1000, 0xDFFFF],
    )
    def test_more_invisibles_the_neighbours_follow_their_own_category(self, code: int) -> None:
        assert console.safe_text(chr(code)) == _reference_safe_text(chr(code))

    def test_more_invisibles_the_whole_tag_block_and_the_bmp_set_leave_nothing_behind(self) -> None:
        text = "".join(chr(c) for c in _MORE_INVISIBLES)
        assert console.safe_text(text).isascii()

    def test_more_invisibles_ordinary_text_is_untouched(self) -> None:
        text = "ñandú café 日本語 😀 a\u00a0b \u0e01\u0e34 \u1780\u17b6"
        assert console.safe_text(text) == text
