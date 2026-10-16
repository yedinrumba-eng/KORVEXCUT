"""Console output: UTF-8 streams, human/JSON writer and throttled progress."""

import io
import json
import sys
import time
from collections.abc import Mapping

_TAGS = frozenset({"OK", "FALTA", "AVISO", "ERROR", "INFO"})
_PROGRESS_INTERVAL_S = 2.0


def setup_streams() -> None:
    """Force UTF-8 on stdout/stderr so Windows code pages never garble output (spec 0.10.2)."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8", errors="replace")


class Out:
    """Writes human lines or one single JSON document, depending on the mode."""

    def __init__(self, json_mode: bool) -> None:
        self.json_mode = json_mode

    def line(self, tag: str, text: str) -> None:
        """Print `[TAG] text` to stdout; silent in JSON mode."""
        if tag not in _TAGS:
            raise ValueError(f"unknown tag: {tag!r}")
        if not self.json_mode:
            print(f"[{tag}] {text}")

    def result(self, obj: Mapping[str, object]) -> None:
        """Print the one JSON document to stdout; silent in human mode."""
        if self.json_mode:
            print(json.dumps(obj, ensure_ascii=False, indent=1))

    def warn(self, text: str) -> None:
        """Print a warning to stderr, in both modes."""
        print(f"[AVISO] {text}", file=sys.stderr)


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
        print(
            f"{self.label}: {self._done}/{self.total} {self.unit} ({pct}%)"
            f" - {rate:.1f} {rate_unit}{eta}",
            file=sys.stderr,
        )
