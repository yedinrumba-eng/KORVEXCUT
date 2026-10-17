"""Console output: UTF-8 streams, human/JSON writer and throttled progress."""

import io
import json
import sys
import time
import unicodedata
from collections.abc import Mapping

_TAGS = frozenset({"OK", "FALTA", "AVISO", "ERROR", "INFO"})
_PROGRESS_INTERVAL_S = 2.0
# Control, format, line separator, paragraph separator and surrogate characters: on a terminal
# they change the title, clear the screen, flip the text direction or forge a line.
_ESCAPED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp", "Cs"})
_LAST_LATIN1 = 0xFF
_LAST_BMP = 0xFFFF


def setup_streams() -> None:
    """Force UTF-8 on stdout/stderr so Windows code pages never garble output (spec 0.10.2)."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


def safe_text(text: str) -> str:
    r"""`text` with every Cc, Cf, Zl, Zp or Cs character swapped for its visible escape: `\xNN`
    up to U+00FF, `\uNNNN` up to U+FFFF, `\UNNNNNNNN` above. The newline stays. Text without such
    characters comes back identical.

    Every line kcut prints goes through here: file names, ids and keys of `inventory.json` are not
    trusted and must not reach the terminal as escape sequences (spec 001.8, point 1).
    """
    return "".join(_visible(ch) for ch in text)


def _visible(ch: str) -> str:
    if ch == "\n" or unicodedata.category(ch) not in _ESCAPED_CATEGORIES:
        return ch
    code = ord(ch)
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
            print(json.dumps(_clean(obj), ensure_ascii=False, indent=1))

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
