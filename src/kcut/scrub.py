"""Remove location, device and date metadata, and the paths of the command, from text that came
from a media tool."""

import re
from collections.abc import Sequence
from pathlib import PurePosixPath, PureWindowsPath

PATH_MARK = "<ruta>"
_MIN_NAME = 4  # a shorter file name is hidden only as part of its path: `a` would be everywhere

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


def command_paths(args: Sequence[str]) -> list[str]:
    """The paths a command line names, as they were written: what follows `-i` (but not the graph
    of `-f lavfi -i`), the last argument if it is not an option and every argument that is an
    absolute path. The program, `args[0]`, is not one of them, and neither is `-`: it is the pipe
    (stdin or stdout), not a file, and `-i -` would hide every `-` of the tail of an error
    (001.26, point 8)."""
    found: list[str] = []
    for i, arg in enumerate(args[1:], start=1):
        is_input = args[i - 1] == "-i" and list(args[max(0, i - 3) : i - 1]) != ["-f", "lavfi"]
        is_output = i == len(args) - 1 and not arg.startswith("-")
        if arg and arg != "-" and (is_input or is_output or _is_absolute(arg)):
            found.append(arg)
    return found


def _is_absolute(arg: str) -> bool:
    """Absolute for Windows (with a drive) or for POSIX (with a first `/`), on any system."""
    return PurePosixPath(arg).is_absolute() or PureWindowsPath(arg).is_absolute()


def hide_paths(text: str, args: Sequence[str]) -> str:
    """`text` with every path of the command `args` (see `command_paths`) replaced by `<ruta>`,
    whether the tool wrote it with a backslash or with a slash. A file name is untrusted text:
    ffmpeg prints it in its errors, and an error message is read by Claude (001.25, point 12).
    The name of the file alone (four characters or more) goes too: a tool that writes the path in
    another encoding, or only the name, would not match the whole path."""
    forms: set[str] = set()
    for path in command_paths(args):
        forms.update({path, path.replace("\\", "/"), path.replace("/", "\\")})
        name = PureWindowsPath(path).name  # splits at `/` and at a backslash
        if len(name) >= _MIN_NAME:
            forms.add(name)
    for form in sorted(forms, key=len, reverse=True):  # the longest first: a folder is in a file
        text = text.replace(form, PATH_MARK)
    return text
