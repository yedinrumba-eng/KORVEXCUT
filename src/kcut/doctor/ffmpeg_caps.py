"""Pure parsers for `ffmpeg -version`, `-filters` and `-encoders` output."""

import re

_VERSION_RE = re.compile(r"ffmpeg version n?(\d+)\.(\d+)(?:\.(\d+))?")
_FILTER_RE = re.compile(r"^\s[T.][S.][C.]?\s+([A-Za-z0-9_]+)\s+[AVN|]+->[AVN|]+\s", re.MULTILINE)
_ENCODER_RE = re.compile(r"^\s[VAS][F.][S.][X.][B.][D.]\s+([^\s=]\S*)\s", re.MULTILINE)


def parse_version(text: str) -> tuple[int, int, int] | None:
    """Return (major, minor, patch) of a release build; None for git builds like `N-12345-g...`.

    A release such as `7.0` has no patch number, so the patch is reported as 0.
    """
    match = _VERSION_RE.search(text)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def parse_filters(text: str) -> frozenset[str]:
    """Names of every filter listed by `ffmpeg -filters`."""
    return frozenset(_FILTER_RE.findall(text))


def parse_encoders(text: str) -> frozenset[str]:
    """Names of every encoder listed by `ffmpeg -encoders`."""
    return frozenset(_ENCODER_RE.findall(text))
