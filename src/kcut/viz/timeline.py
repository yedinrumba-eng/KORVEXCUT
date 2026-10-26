"""The picture of a stretch of audio: level, silences, ruler and the words on top (spec S1.4).

Technique of `piloto/view.py`. Everything here is pure: arrays and lists in, a Pillow image out.
Times are compared in whole units of `1/(1000 * fps)` s (spec 0.6): milliseconds are multiplied
by `fps`, frames by 1000. Pixels come from integer arithmetic too.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from kcut.analysis.energy import Run
from kcut.config.model import AnalysisSection
from kcut.pack.markers import word_flags
from kcut.timebase import ms_to_f_round
from kcut.transcribe.model import Word
from kcut.viz.draw import Color, fit_text, text_box

WIDTH = 2400
HEIGHT = 420
STRIP_HEIGHT = 220  # the filmstrip goes on top of the timeline
BACKGROUND: Color = (18, 18, 22)
BAR: Color = (120, 200, 255)
THRESHOLD: Color = (255, 80, 80)
BAND: Color = (60, 20, 20)
BAND_TEXT: Color = (255, 120, 120)
SURE: Color = (240, 200, 40)
DOUBTFUL: Color = (255, 120, 30)
INK: Color = (20, 20, 20)
WHITE: Color = (255, 255, 255)
RULER: Color = (200, 200, 200)
_TOP = 40  # the wave zone: its top edge, its base and the height of the loudest bar
_BASE = 300
_PEAK = 250
_FLOOR_DB = 70.0  # the bar of a block is (db + 70) / 70 of the peak, as in the pilot
_ROWS_Y = 348  # words go in 3 staggered rows of 20 pixels
_ROW_STEP = 24
_HOP_MS = 10  # the level comes in blocks of 10 ms
_TICK_MS = 500
_LABEL_GAP_PX = 70  # ruler labels are at least this far apart
PixelOf = Callable[[int], int]  # pixel of a time of the clip in ms
MAX_BOXES = 400  # word boxes in one picture (spec 001.20, point 6)


@dataclass(frozen=True)
class ViewWord:
    """A word of the window as it is drawn: text as shown (already masked), clip time in ms."""

    id: str
    text: str
    s_ms: int
    e_ms: int
    doubtful: bool


def window_silences(
    silences: Sequence[Run], start_f: int, end_f: int, fps: int
) -> list[tuple[int, int]]:
    """The silences (ms of the clip) that touch the window `[start_f, end_f)`."""
    return [(a, b) for a, b in silences if b * fps > start_f * 1000 and a * fps < end_f * 1000]


def window_words(
    words: Sequence[Word],
    start_f: int,
    end_f: int,
    fps: int,
    low_prob: float,
    silences: Sequence[Run],
) -> list[ViewWord]:
    """The words with text that touch the window, in order.

    A word touches it when `e_ms * fps > start_f * 1000` and `s_ms * fps < end_f * 1000`. It is
    doubtful when `pack.markers.word_flags` gives it `?` (`p < low_prob`) or `H` (the whole word
    lies inside a silence).
    """
    found: list[ViewWord] = []
    for word in words:
        if not word.text:
            continue
        if word.e_ms * fps > start_f * 1000 and word.s_ms * fps < end_f * 1000:
            marks = word_flags([word], (), low_prob, silences)[0]
            doubtful = "?" in marks or "H" in marks
            found.append(ViewWord(word.id, word.text, word.s_ms, word.e_ms, doubtful))
    return found


def render_timeline(
    db: NDArray[np.float32],
    silences: Sequence[Run],
    words: Sequence[ViewWord],
    start_f: int,
    end_f: int,
    fps: int,
    cfg: AnalysisSection,
    filmstrip: Sequence[NDArray[np.uint8]] | None,
    notice: str | None,
) -> Image.Image:
    """The window as a 2400 x 420 picture (640 high with a filmstrip, which goes on top).

    `db` is the level of the window's samples in blocks of 10 ms (`analysis.energy.rms_db`),
    `silences` and the words are in ms of the clip, `filmstrip` BGR frames. The silence bands
    and the words that touch the window are drawn clipped to it (the first `MAX_BOXES` words, each
    with its text cut to 24 characters); a band says the whole length of its silence. With
    `notice` the text goes at the top left, in white.
    """
    if end_f <= start_f:
        raise ValueError("la ventana tiene que tener al menos un frame")
    span = end_f - start_f

    def at(abs_ms: int) -> int:  # pixel of a time of the clip
        return (abs_ms * fps - start_f * 1000) * WIDTH // (span * 1000)

    def rel(rel_ms: int) -> int:  # pixel of a time since the start of the window
        return rel_ms * fps * WIDTH // (span * 1000)

    img = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(img)
    touching = window_silences(silences, start_f, end_f, fps)
    for a, b in touching:
        left = max(0, at(a))
        draw.rectangle((left, _TOP, max(left, min(WIDTH, at(b)) - 1), _BASE), fill=BAND)
    for k, level in enumerate(db):
        height = int(min(1.0, max(0.0, (float(level) + _FLOOR_DB) / _FLOOR_DB)) * _PEAK)
        left = rel(k * _HOP_MS)
        right = max(left, rel((k + 1) * _HOP_MS) - 1)
        if height and left < WIDTH:
            draw.rectangle((left, _BASE - height, min(right, WIDTH - 1), _BASE), fill=BAR)
    line = _BASE - int(max(0.0, (cfg.silence_db + _FLOOR_DB) / _FLOOR_DB) * _PEAK)
    draw.line((0, line, WIDTH, line), fill=THRESHOLD)
    for a, b in touching:
        label = f"{(b - a) / 1000:.2f}s"  # the whole silence, not just the part in the window
        text_box(draw, (max(0, at(a)) + 2, _TOP + 2), label, 12, BAND_TEXT)
    _ruler(draw, start_f, end_f, fps, at)
    for j, word in enumerate(words[:MAX_BOXES]):
        _word_box(draw, word, _ROWS_Y + (j % 3) * _ROW_STEP, at)
    if notice:
        text_box(draw, (10, 6), notice, 28, WHITE)
    return _with_filmstrip(img, filmstrip) if filmstrip else img


def _ruler(draw: ImageDraw.ImageDraw, start_f: int, end_f: int, fps: int, at: PixelOf) -> None:
    """A tick every 0.5 s with the second and the frame; labels thin out when they would touch."""
    first = -((-2 * start_f) // fps)  # first tick (in half seconds) at or after the window start
    per_tick = max(1, WIDTH * fps // (2 * (end_f - start_f)))
    every = max(1, -(-_LABEL_GAP_PX // per_tick))
    k = first
    while k * _TICK_MS * fps < end_f * 1000:
        x = at(k * _TICK_MS)
        draw.line((x, _BASE, x, _BASE + 10), fill=RULER)
        if (k - first) % every == 0:
            text_box(draw, (x - 14, _BASE + 12), f"{k / 2:.1f}", 13, RULER)
            text_box(draw, (x - 14, _BASE + 27), f"f{ms_to_f_round(k * _TICK_MS, fps)}", 11, RULER)
        k += 1


def _word_box(draw: ImageDraw.ImageDraw, word: ViewWord, y: int, at: PixelOf) -> None:
    left = max(0, min(WIDTH - 1, at(word.s_ms)))
    right = max(left + 2, min(WIDTH, at(word.e_ms)))
    color = DOUBTFUL if word.doubtful else SURE
    draw.rectangle((left, y, right, y + 20), fill=color)
    label = f"{fit_text(word.text)} {fit_text(word.id.partition(':')[2] or word.id, 12)}"
    text_box(draw, (left + 2, y + 2), label, 14, INK, color)


def _with_filmstrip(timeline: Image.Image, frames: Sequence[NDArray[np.uint8]]) -> Image.Image:
    """The frames side by side, `STRIP_HEIGHT` high, on top of the timeline."""
    canvas = Image.new("RGB", (WIDTH, HEIGHT + STRIP_HEIGHT), BACKGROUND)
    cell = WIDTH // len(frames)
    for k, frame in enumerate(frames):
        shot = Image.fromarray(np.ascontiguousarray(frame[:, :, ::-1]))  # BGR to RGB
        shot.thumbnail((cell - 4, STRIP_HEIGHT - 4), Image.Resampling.LANCZOS)
        canvas.paste(shot, (k * cell + (cell - shot.width) // 2, (STRIP_HEIGHT - shot.height) // 2))
    canvas.paste(timeline, (0, STRIP_HEIGHT))
    return canvas
