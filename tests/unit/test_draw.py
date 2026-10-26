"""Text on pictures: the built-in font at a size, boxes, word wrap (spec S1.4)."""

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from kcut.viz.draw import font, text_box, wrap


class TestFont:
    def test_draw_font_is_a_freetype_font_of_the_size_asked(self) -> None:
        face = font(20)
        assert isinstance(face, ImageFont.FreeTypeFont) and face.size == 20

    def test_draw_font_is_cached_per_size(self) -> None:
        assert font(14) is font(14) and font(14) is not font(15)

    def test_draw_font_a_bigger_size_is_wider(self) -> None:
        assert font(40).getlength("kcut") > font(20).getlength("kcut")


class TestTextBox:
    def _canvas(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        image = Image.new("RGB", (300, 80), (0, 0, 0))
        return image, ImageDraw.Draw(image)

    def test_draw_text_box_draws_the_text_in_the_color(self) -> None:
        image, draw = self._canvas()
        text_box(draw, (10, 10), "hola", 24, (255, 255, 255))
        pixels = np.asarray(image)
        assert np.all(pixels == (255, 255, 255), axis=-1).any()
        assert not np.all(pixels[:, 200:] != 0, axis=-1).any()  # and nothing far to the right

    def test_draw_text_box_with_a_background_fills_a_box_around_it(self) -> None:
        image, draw = self._canvas()
        text_box(draw, (10, 10), "hola", 24, (255, 255, 255), (200, 0, 0))
        pixels = np.asarray(image)
        left, top, right, bottom = draw.textbbox((10, 10), "hola", font=font(24))
        assert tuple(pixels[top - 2, left - 2]) == (
            200,
            0,
            0,
        )  # the box hugs the text with a margin
        assert tuple(pixels[bottom + 2, right + 2]) == (200, 0, 0)
        assert tuple(pixels[top - 6, left - 6]) == (0, 0, 0)  # and no more than that

    def test_draw_text_box_without_a_background_leaves_the_rest_alone(self) -> None:
        image, draw = self._canvas()
        text_box(draw, (10, 10), "hola", 24, (255, 255, 255))
        assert tuple(np.asarray(image)[2, 2]) == (0, 0, 0)

    def test_draw_text_box_accents_and_enyes_are_drawn(self) -> None:
        image, draw = self._canvas()
        text_box(draw, (10, 10), "ñandú á é", 24, (255, 255, 255))
        assert np.all(np.asarray(image) == (255, 255, 255), axis=-1).any()


class TestWrap:
    def test_draw_wrap_a_short_text_is_one_line(self) -> None:
        assert wrap("hola mundo", 20, 1000) == ["hola mundo"]

    def test_draw_wrap_no_line_is_wider_than_the_limit(self) -> None:
        text = "uno dos tres cuatro cinco seis siete ocho nueve diez " * 3
        lines = wrap(text, 20, 300)
        assert len(lines) > 3
        assert all(font(20).getlength(line) <= 300 for line in lines)

    def test_draw_wrap_keeps_every_word_in_order(self) -> None:
        text = "uno dos tres cuatro cinco seis siete ocho nueve diez"
        assert " ".join(wrap(text, 20, 200)).split() == text.split()

    def test_draw_wrap_a_word_wider_than_a_line_is_cut_by_characters(self) -> None:
        word = "x" * 200
        lines = wrap(word, 20, 100)
        assert len(lines) > 1 and "".join(lines) == word
        assert all(font(20).getlength(line) <= 100 for line in lines)

    @pytest.mark.parametrize("text", ["", "   ", "\n\t"])
    def test_draw_wrap_empty_text_has_no_lines(self, text: str) -> None:
        assert wrap(text, 20, 100) == []

    def test_draw_wrap_spaces_in_a_row_count_once(self) -> None:
        assert wrap("a    b", 20, 1000) == ["a b"]
