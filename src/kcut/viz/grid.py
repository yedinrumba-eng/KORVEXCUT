"""A grid over a frame, so Claude can say "the hand is at 0.6, 0.4", and contact sheets (S1.4)."""

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw

from kcut.timebase import rdiv
from kcut.viz.draw import Color, text_box

BACKGROUND: Color = (18, 18, 22)
LINE: Color = (0, 255, 255)
CENTER: Color = (255, 0, 255)
INK: Color = (255, 255, 255)
SHADE: Color = (0, 0, 0)
MAX_SHEET_PIXELS = 25_000_000  # a sheet is never bigger than this (spec 001.20, point 5)
_CROSS = 24  # half the length of the cross at the center, in pixels
_LABEL_HEIGHT = 24  # room under each picture of a sheet for its label


def grid_overlay(img: NDArray[np.uint8], pct: int) -> Image.Image:
    """`img` (a BGR frame) with a line every `pct` percent of its width and height.

    The lines are labelled `0.1 ... 0.9` along the top edge (vertical lines) and the left edge
    (horizontal ones), and a cross marks the center. `pct` goes from 1 to 99.
    """
    if not 1 <= pct <= 99:
        raise ValueError(f"pct tiene que ir de 1 a 99 (vino {pct})")
    height, width = img.shape[:2]
    picture = Image.fromarray(np.ascontiguousarray(img[:, :, ::-1]))  # BGR to RGB
    draw = ImageDraw.Draw(picture)
    for step in range(pct, 100, pct):
        x, y = width * step // 100, height * step // 100
        draw.line((x, 0, x, height), fill=LINE)
        draw.line((0, y, width, y), fill=LINE)
        label = _fraction(step)
        text_box(draw, (x + 2, 2), label, 14, INK, SHADE)
        text_box(draw, (2, y + 2), label, 14, INK, SHADE)
    cx, cy = width // 2, height // 2
    draw.line((cx - _CROSS, cy, cx + _CROSS, cy), fill=CENTER, width=2)
    draw.line((cx, cy - _CROSS, cx, cy + _CROSS), fill=CENTER, width=2)
    return picture


class SheetBuilder:
    """A contact sheet filled one picture at a time (spec 001.20, point 5).

    The pictures all fit a cell of `frame_size`, or a narrower one if the sheet would pass
    `max_pixels`: the cell shrinks, keeping its aspect, until it fits. Each picture is resized,
    pasted and can be dropped by the caller right away, so the sheet is the only big thing in
    memory. `cell_width` is the real width of a cell.
    """

    def __init__(
        self,
        count: int,
        frame_size: tuple[int, int],
        cols: int = 8,
        max_pixels: int = MAX_SHEET_PIXELS,
    ) -> None:
        if count < 1 or cols < 1 or min(frame_size) < 1:
            raise ValueError("hace falta al menos una imagen, una columna y un tamaño real")
        width, height = frame_size
        self._count = count
        self._used = min(cols, count)
        rows = -(-count // self._used)
        self.cell_width = _fit_width(width, height, self._used, rows, max_pixels)
        self._cell_h = max(1, rdiv(height * self.cell_width, width)) + _LABEL_HEIGHT
        self._canvas = Image.new(
            "RGB", (self._used * self.cell_width, rows * self._cell_h), BACKGROUND
        )
        self._draw = ImageDraw.Draw(self._canvas)
        self._added = 0

    def add(self, image: Image.Image, label: str) -> None:
        """Paste `image` (shrunk to fit its cell, never enlarged) in the next place, labelled."""
        if self._added >= self._count:
            raise ValueError(f"la hoja se armó para {self._count} imágenes")
        room_w, room_h = self.cell_width, self._cell_h - _LABEL_HEIGHT
        scale = min(room_w / image.width, room_h / image.height, 1.0)
        shot = image
        if scale < 1.0:
            size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            shot = image.resize(size, Image.Resampling.LANCZOS)
        left = (self._added % self._used) * self.cell_width
        top = (self._added // self._used) * self._cell_h
        self._canvas.paste(shot, (left + (room_w - shot.width) // 2, top))
        text_box(self._draw, (left + 4, top + room_h + 3), label, 16, INK)
        self._added += 1

    def image(self) -> Image.Image:
        return self._canvas


def sheet(images: list[Image.Image], labels: list[str], cols: int = 8) -> Image.Image:
    """The pictures in rows of `cols`, each with its label underneath, on one image of at most
    `MAX_SHEET_PIXELS` (the cells get narrower if it would not fit)."""
    if not images or len(images) != len(labels) or cols < 1:
        raise ValueError("hace falta una etiqueta por imagen, al menos una imagen y cols >= 1")
    cell = (max(image.width for image in images), max(image.height for image in images))
    builder = SheetBuilder(len(images), cell, cols)
    for image, label in zip(images, labels, strict=True):
        builder.add(image, label)
    return builder.image()


def _fit_width(width: int, height: int, cols: int, rows: int, max_pixels: int) -> int:
    """The widest cell (up to `width`) whose sheet of `cols` x `rows` stays within `max_pixels`."""

    def pixels(w: int) -> int:
        return cols * w * rows * (max(1, rdiv(height * w, width)) + _LABEL_HEIGHT)

    low, high = 1, width
    while low < high:
        middle = (low + high + 1) // 2
        if pixels(middle) <= max_pixels:
            low = middle
        else:
            high = middle - 1
    return low


def _fraction(step: int) -> str:
    """`10` -> `0.1`, `25` -> `0.25`, `5` -> `0.05`: a percent as the fraction on the labels."""
    return f"{step / 100:.2f}".rstrip("0").rstrip(".")
