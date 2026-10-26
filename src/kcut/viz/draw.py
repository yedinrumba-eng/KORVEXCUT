"""Text on pictures with Pillow's built-in font (DS6): sizes, boxes and word wrap.

Never `drawtext` and never a font file path: the font is the one Pillow ships, loaded at a size.
"""

from functools import cache
from typing import cast

from PIL import ImageDraw, ImageFont

from kcut.console import safe_text

Color = tuple[int, int, int]
_PAD = 3  # pixels around a text box
MAX_TEXT = 24  # characters of a text drawn from the transcript


@cache
def font(size: int) -> ImageFont.FreeTypeFont:
    """The built-in font at `size` pixels (cached: loading it is not free)."""
    return cast(ImageFont.FreeTypeFont, ImageFont.load_default(size=size))


def fit_text(text: str, limit: int = MAX_TEXT) -> str:
    """`text` as it may be drawn from a transcript (spec 001.20, point 6): on one line (newlines
    become spaces), with every control, format or invisible character shown as its escape
    (`console.safe_text`), and at most `limit` characters, the last one `…` if something was cut.

    Only the first `limit + 1` characters are looked at: each one gives at least one character
    of output, so that is enough to know whether it fits, whatever the length of `text`.
    """
    line = safe_text(text[: limit + 1].replace("\n", " "))
    return line if len(line) <= limit else line[: limit - 1] + "…"


def text_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    size: int,
    fill: Color,
    bg: Color | None = None,
) -> None:
    """Draw `text` with its top-left corner at `xy`; with `bg`, on a filled box that hugs it."""
    face = font(size)
    if bg is not None:
        left, top, right, bottom = draw.textbbox(xy, text, font=face)
        draw.rectangle((left - _PAD, top - _PAD, right + _PAD, bottom + _PAD), fill=bg)
    draw.text(xy, text, fill=fill, font=face)


def wrap(text: str, size: int, max_px: int) -> list[str]:
    """`text` cut into lines no wider than `max_px` at `size`, breaking at spaces. A word wider
    than a line is cut by characters. Empty text gives no lines."""
    face = font(size)
    lines: list[str] = []
    line = ""
    for word in text.split():
        for piece in _pieces(word, face, max_px):
            candidate = f"{line} {piece}" if line else piece
            if line and face.getlength(candidate) > max_px:
                lines.append(line)
                line = piece
            else:
                line = candidate
    if line:
        lines.append(line)
    return lines


def _pieces(word: str, face: ImageFont.FreeTypeFont, max_px: int) -> list[str]:
    """`word` whole, or cut into pieces that each fit `max_px` (at least one character)."""
    if face.getlength(word) <= max_px:
        return [word]
    pieces: list[str] = []
    current = ""
    for char in word:
        if current and face.getlength(current + char) > max_px:
            pieces.append(current)
            current = char
        else:
            current += char
    return [*pieces, current]
