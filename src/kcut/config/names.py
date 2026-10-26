"""Project names: which characters are never allowed, and how a folder name becomes a name."""

import unicodedata

NAME_MAX = 80
DEFAULT_NAME = "proyecto"
# Control, format, line-separator and paragraph-separator characters: they can hide text, forge
# a new line in `estrategia.md` or flip the display order (U+202E).
_FORBIDDEN = frozenset({"Cc", "Cf", "Zl", "Zp"})


def has_forbidden_chars(name: str) -> bool:
    """True if `name` holds any character of the Unicode categories Cc, Cf, Zl or Zp."""
    return first_forbidden(name) is not None


def first_forbidden(text: str) -> int | None:
    """Index of the first character of `text` in the categories Cc, Cf, Zl or Zp, else None."""
    for index, ch in enumerate(text):
        if unicodedata.category(ch) in _FORBIDDEN:
            return index
    return None


def clean_default_name(folder_name: str) -> str:
    """Name taken from a folder: forbidden characters removed, cut to 80, never empty."""
    cleaned = "".join(ch for ch in folder_name if unicodedata.category(ch) not in _FORBIDDEN)
    return cleaned[:NAME_MAX] or DEFAULT_NAME
