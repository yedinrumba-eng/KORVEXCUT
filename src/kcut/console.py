"""Console output: UTF-8 streams, human/JSON writer and throttled progress."""

import io
import json
import re
import sys
import time
from collections.abc import Mapping

_TAGS = frozenset({"OK", "FALTA", "AVISO", "ERROR", "INFO"})
_PROGRESS_INTERVAL_S = 2.0
# What `safe_text` escapes, as inclusive code point ranges (newline, U+000A, excluded):
#   - the Unicode categories Cc, Cf, Zl, Zp, Cs and Co: on a terminal they change the title, clear
#     the screen, flip the text direction or forge a line, and private-use ones show whatever the
#     viewer's font maps them to;
#   - the variation selectors U+FE00-U+FE0F and U+E0100-U+E01EF (category Mn): they ride on any
#     character and hide text from whoever reviews what Claude reads (spec 001.10, point 4);
#   - the invisible fillers U+115F, U+1160, U+3164, U+FFA0 and U+2800 (001.12, point 14): blank
#     "letters" that can pose as an empty name. NBSP is ordinary text and stays;
#   - more invisibles (001.14, point 10): U+034F, U+17B4-U+17B5, U+180B-U+180D, U+180F, U+2065,
#     U+FFF0-U+FFF8 and the whole tag block U+E0000-U+E0FFF.
# The table is what the character-by-character definition gives on Python 3.12's Unicode data;
# `tests/unit/test_console_hygiene.py` compares the two on every code point.
_ESCAPED_RANGES = (
    (0x0, 0x9), (0xB, 0x1F), (0x7F, 0x9F), (0xAD, 0xAD), (0x34F, 0x34F), (0x600, 0x605),
    (0x61C, 0x61C), (0x6DD, 0x6DD), (0x70F, 0x70F), (0x890, 0x891), (0x8E2, 0x8E2),
    (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F), (0x200B, 0x200F), (0x2028, 0x202E),
    (0x2060, 0x206F), (0x2800, 0x2800), (0x3164, 0x3164), (0xD800, 0xF8FF), (0xFE00, 0xFE0F),
    (0xFEFF, 0xFEFF), (0xFFA0, 0xFFA0), (0xFFF0, 0xFFFB), (0x110BD, 0x110BD), (0x110CD, 0x110CD),
    (0x13430, 0x1343F), (0x1BCA0, 0x1BCA3), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF),
    (0xF0000, 0xFFFFD), (0x100000, 0x10FFFD),
)  # fmt: skip
_ESCAPE = re.compile(
    "[" + "".join(f"\\U{low:08x}-\\U{high:08x}" for low, high in _ESCAPED_RANGES) + "]"
)
_LAST_LATIN1 = 0xFF
_LAST_BMP = 0xFFFF


def setup_streams() -> None:
    """Force UTF-8 on stdout/stderr so Windows code pages never garble output (spec 0.10.2)."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


def safe_text(text: str) -> str:
    r"""`text` with every Cc, Cf, Zl, Zp, Cs or Co character, every variation selector
    (U+FE00-U+FE0F, U+E0100-U+E01EF), the invisible fillers (U+115F, U+1160, U+3164, U+FFA0,
    U+2800) and the other invisibles of the table above swapped for its visible escape: `\xNN` up
    to U+00FF, `\uNNNN` up to U+FFFF, `\UNNNNNNNN` above. The newline stays. Text without such
    characters comes back identical.

    Every line kcut prints goes through here: file names, ids and keys of `inventory.json` are not
    trusted and must not reach the terminal as escape sequences (spec 001.8, point 1).
    """
    return _ESCAPE.sub(_visible, text)


def _visible(match: re.Match[str]) -> str:
    code = ord(match.group())
    if code <= _LAST_LATIN1:
        return f"\\x{code:02x}"
    if code <= _LAST_BMP:
        return f"\\u{code:04x}"
    return f"\\U{code:08x}"


def _clean(value: object) -> object:
    """A copy of a JSON-like value with `safe_text` applied to every string, keys included."""
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, Mapping):
        return {_clean(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(item) for item in value]
    return value


class Out:
    """Writes human lines or one single JSON document, depending on the mode."""

    def __init__(self, json_mode: bool) -> None:
        self.json_mode = json_mode

    def line(self, tag: str, text: str) -> None:
        """Print `[TAG] text` to stdout; silent in JSON mode."""
        if tag not in _TAGS:
            raise ValueError(f"unknown tag: {tag!r}")
        if not self.json_mode:
            print(f"[{tag}] {safe_text(text)}")

    def result(self, obj: Mapping[str, object]) -> None:
        """Print the one JSON document to stdout; silent in human mode. Every string of `obj`,
        keys included, goes through `safe_text` first; `ensure_ascii` stays off, so accents do
        not change."""
        if self.json_mode:
            print(json.dumps(_clean(obj), ensure_ascii=False, indent=1, allow_nan=False))

    def warn(self, text: str) -> None:
        """Print a warning to stderr, in both modes."""
        print(f"[AVISO] {safe_text(text)}", file=sys.stderr)


class Progress:
    """Progress lines on stderr, at most one every 2 seconds."""

    def __init__(self, label: str, total: int, unit: str) -> None:
        self.label = label
        self.total = total
        self.unit = unit
        self._start = time.monotonic()
        self._last_print = self._start
        self._done = 0
        self._printed_done = -1

    def update(self, done: int) -> None:
        """Record `done` units and print a line if 2 s passed since the last one."""
        self._done = done
        now = time.monotonic()
        if now - self._last_print >= _PROGRESS_INTERVAL_S:
            self._emit(now)

    def close(self) -> None:
        """Print the final state if it was not printed yet."""
        if self._done != self._printed_done and self._done > 0:
            self._emit(time.monotonic())

    def _emit(self, now: float) -> None:
        self._last_print = now
        self._printed_done = self._done
        elapsed = max(now - self._start, 1e-9)
        rate = self._done / elapsed
        pct = 100 * self._done // self.total if self.total > 0 else 0
        rate_unit = "fps" if self.unit == "frames" else f"{self.unit}/s"
        remaining = max(self.total - self._done, 0)
        eta = f" - faltan {round(remaining / rate)} s" if rate > 0 and remaining > 0 else ""
        line = (
            f"{self.label}: {self._done}/{self.total} {self.unit} ({pct}%)"
            f" - {rate:.1f} {rate_unit}{eta}"
        )
        print(safe_text(line), file=sys.stderr)
