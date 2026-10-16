"""Remove location, device and date metadata from text that came from a media tool."""

import re

_META_HEADER = re.compile(r"^\s*Metadata:\s*$")
# `key : value` with a short key (at most three words): an English sentence has more words.
_KEYED_LINE = re.compile(r"^\s*([\w.\-]+(?: [\w.\-]+){0,2})\s*:")
_TAG_LINE = re.compile(r"^\s*TAG:([^=\r\n]+)=", re.IGNORECASE)
_JSON_PAIR = re.compile(r'"((?:[^"\\\r\n]|\\.)*)"\s*:\s*"(?:[^"\\\r\n]|\\.)*"\s*,?')
# One key list for every format; a word matches whole, a prefix matches the start of a word.
_SENSITIVE_WORDS = (
    "location",
    "iso6709",
    "make",
    "model",
    "creation_time",
    "serial",
    "artist",
    "comment",
    "title",
    "description",
    "encoded_by",
    "copyright",
)
_SENSITIVE_PREFIXES = ("com.apple.", "gps")
_SENSITIVE_KEY = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(
        [re.escape(word) + r"(?![a-z0-9])" for word in _SENSITIVE_WORDS]
        + [re.escape(prefix) for prefix in _SENSITIVE_PREFIXES]
    )
    + ")",
    re.IGNORECASE,
)
# ISO 6709: decimal degrees (lenient digit count), or the compact DM/DMS forms that MOV files
# use, which always end in "/"; both with an optional altitude.
_ALTITUDE = r"(?:[+-]\d+(?:\.\d+)?)?"
_ISO6709 = re.compile(
    rf"[+-]\d{{1,3}}\.\d+[+-]\d{{1,3}}\.\d+{_ALTITUDE}/?"
    rf"|[+-]\d{{2}}(?:\d{{2}}){{0,2}}(?:\.\d+)?[+-]\d{{3}}(?:\d{{2}}){{0,2}}(?:\.\d+)?{_ALTITUDE}/"
)


class MetadataScrubber:
    """Line-by-line scrubber that keeps a `Metadata:` block open between calls to `feed`."""

    def __init__(self) -> None:
        self._block_indent: int | None = None

    def feed(self, text: str) -> str:
        """Scrub `text`; a block that `text` leaves open still hides the lines of the next call."""
        return "".join(self._line(line) for line in text.splitlines(keepends=True))

    def _line(self, line: str) -> str:
        body = line.rstrip("\r\n")
        indent = len(body) - len(body.lstrip())
        if self._block_indent is not None:
            if indent > self._block_indent:
                return ""
            self._block_indent = None
        if _META_HEADER.match(body):
            self._block_indent = indent
            return ""
        keyed = _TAG_LINE.match(body) or _KEYED_LINE.match(body)
        if keyed and _SENSITIVE_KEY.search(keyed.group(1)):
            return ""
        cleaned = _JSON_PAIR.sub(_drop_sensitive_pair, line)
        if cleaned != line and not cleaned.strip():
            return ""
        return _ISO6709.sub("[ubicacion omitida]", cleaned)


def scrub_media_metadata(text: str) -> str:
    """Remove `Metadata:` blocks, sensitive `key: value`, `TAG:key=value` and JSON pairs, and
    ISO 6709 coordinates."""
    return MetadataScrubber().feed(text)


def _drop_sensitive_pair(match: re.Match[str]) -> str:
    return "" if _SENSITIVE_KEY.search(match.group(1)) else match.group(0)
