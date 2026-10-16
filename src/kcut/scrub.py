"""Remove location, device and date metadata from text that came from a media tool."""

import re

_META_HEADER = re.compile(r"^\s*Metadata:\s*$")
_KEYED_LINE = re.compile(r"^\s*([\w.\-]+(?: [\w.\-]+)*)\s*:")
_SENSITIVE_KEYS = ("location", "gps", "com.apple.", "make", "model", "creation_time")
_ISO6709 = re.compile(r"[+-]\d{1,3}\.\d+[+-]\d{1,3}\.\d+")


def scrub_media_metadata(text: str) -> str:
    """Remove `Metadata:` blocks, location/device/date tag lines and ISO 6709 coordinates."""
    kept: list[str] = []
    block_indent: int | None = None
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        indent = len(body) - len(body.lstrip())
        if block_indent is not None:
            if indent > block_indent:
                continue
            block_indent = None
        if _META_HEADER.match(body):
            block_indent = indent
            continue
        keyed = _KEYED_LINE.match(body)
        if keyed and any(key in keyed.group(1).lower() for key in _SENSITIVE_KEYS):
            continue
        kept.append(_ISO6709.sub("[ubicacion omitida]", line))
    return "".join(kept)
