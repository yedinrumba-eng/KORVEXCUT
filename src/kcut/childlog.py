"""A child's stderr for the command log, streamed in chunks (spec 0.8, 0.11, 001.3).

Memory stays bounded by the constants below, whatever the child writes: the log gets the
stderr chunk by chunk, and only its last `TAIL_CAP_BYTES` are kept for errors and parsers.
The block is written through `logfile.log_writer`, so it gets the same per-path lock and the
same checks as any other append to that log (001.6).
"""

import codecs
import re
from typing import IO

from kcut.scrub import MetadataScrubber

TAIL_CAP_BYTES = 8 * 1024**2
CHUNK_BYTES = 1024**2
LONG_LINE_CHARS = 1024**2
_MB = 1024**2
_UTF8_CONTINUATION = bytes(range(0x80, 0xC0))
_LEADING_INDENTED_LINES = re.compile(rb"\A(?:[ \t][^\n]*\n)*")


def omitted(skipped_bytes: int) -> str:
    """The marker that stands for bytes left out of a text."""
    return f"[... {skipped_bytes / _MB:.1f} MB omitidos]"


def read_tail(src: IO[bytes], size: int) -> str:
    """Decode the last `TAIL_CAP_BYTES` of the first `size` bytes of `src`.

    When the start is cut, the text begins on a whole line (or a whole character) after a marker
    line that says how much was left out. The indented lines right after the cut go too: they may
    belong to a `Metadata:` block whose header was cut off, which the scrubber could not see.
    """
    start = max(0, size - TAIL_CAP_BYTES)
    src.seek(start)
    data = src.read(size - start)
    if start == 0:
        return data.decode("utf-8", errors="replace")
    newline = data.find(b"\n")
    if newline >= 0:
        data = _LEADING_INDENTED_LINES.sub(b"", data[newline + 1 :], count=1)
    else:
        data = data.lstrip(_UTF8_CONTINUATION)
    return omitted(size - len(data)) + "\n" + data.decode("utf-8", errors="replace")


def copy_scrubbed(src: IO[bytes], size: int, dst: IO[str]) -> bool:
    """Copy the first `size` bytes of `src` into `dst` in chunks, scrubbed line by line.

    Lines are never split before scrubbing, so an open `Metadata:` block is never lost between
    chunks; a single line longer than `LONG_LINE_CHARS` keeps its start plus a marker. Returns
    True when what was written ends a line (or nothing was written).
    """
    src.seek(0)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    scrubber = MetadataScrubber()
    pending, skipped, left, ends_line = "", 0, size, True
    while True:
        chunk = src.read(min(CHUNK_BYTES, left))
        left -= len(chunk)
        data = decoder.decode(chunk, final=not chunk)
        if skipped:
            end = _first_line_end(data)
            if end < 0 and chunk:
                skipped += len(data.encode("utf-8"))
                continue
            dropped, data = (data, "") if end < 0 else (data[:end], data[end:])
            pending += " " + omitted(skipped + len(dropped.encode("utf-8")))
            skipped = 0
        pending += data
        cut = len(pending) if not chunk else _whole_lines(pending)
        if cut:
            text = scrubber.feed(pending[:cut]).replace("\r\n", "\n")
            pending = pending[cut:]
            if text:
                dst.write(text)
                ends_line = text.endswith("\n")
        if not chunk:
            return ends_line
        if len(pending) > LONG_LINE_CHARS:
            skipped = len(pending[LONG_LINE_CHARS:].encode("utf-8"))
            pending = pending[:LONG_LINE_CHARS]


def _whole_lines(text: str) -> int:
    """Length of the longest prefix of `text` that ends a line; a final CR may still get its LF."""
    return max(text.rfind("\n"), text.rfind("\r", 0, len(text) - 1)) + 1


def _first_line_end(text: str) -> int:
    ends = [i for i in (text.find("\n"), text.find("\r")) if i >= 0]
    return min(ends) if ends else -1
