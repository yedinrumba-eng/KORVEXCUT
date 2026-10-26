"""The grid over a frame and the contact sheet (spec S1.4)."""

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from kcut.viz.grid import CENTER, INK, LINE, SheetBuilder, grid_overlay, sheet


def _black(w: int = 200, h: int = 120) -> NDArray[np.uint8]:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _pixel(image: Image.Image, x: int, y: int) -> tuple[int, ...]:
    return tuple(np.asarray(image)[y, x])


class TestGridOverlay:
    def test_grid_img_keeps_the_size_and_draws_a_line_every_ten_percent(self) -> None:
        image = grid_overlay(_black(400, 300), 10)
        assert image.size == (400, 300) and image.mode == "RGB"
        for k in range(1, 10):
            assert _pixel(image, 400 * k * 10 // 100, 299) == LINE  # vertical line, bottom row
            assert _pixel(image, 399, 300 * k * 10 // 100) == LINE  # horizontal line, right edge

    def test_grid_img_the_step_is_the_percent_asked(self) -> None:
        image = grid_overlay(_black(400, 100), 25)
        assert [_pixel(image, x, 99) == LINE for x in (100, 200, 300)] == [True] * 3
        assert _pixel(image, 40, 99) != LINE  # no line at 10 percent

    def test_grid_img_a_cross_marks_the_center(self) -> None:
        image = grid_overlay(_black(), 10)
        assert _pixel(image, 100, 60) == CENTER and _pixel(image, 110, 60) == CENTER

    def test_grid_img_the_labels_are_on_the_top_and_left_edges(self) -> None:
        pixels = np.asarray(grid_overlay(_black(400, 300), 10))
        top = np.all(pixels[:22, 100:240] == INK, axis=-1)  # label of the first lines
        left = np.all(pixels[20:80, :40] == INK, axis=-1)
        assert top.any() and left.any()
        assert not np.all(pixels[140:260, 60:300] == INK, axis=-1).any()  # nothing in the middle

    def test_grid_img_reads_a_bgr_frame_as_rgb(self) -> None:
        frame = np.zeros((300, 400, 3), dtype=np.uint8)
        frame[:, :, 0] = 255  # blue in BGR
        assert _pixel(grid_overlay(frame, 10), 50, 165) == (0, 0, 255)  # between lines and labels

    @pytest.mark.parametrize("pct", [0, -5, 100, 250])
    def test_grid_img_a_percent_out_of_range_is_refused(self, pct: int) -> None:
        with pytest.raises(ValueError):
            grid_overlay(_black(), pct)


class TestSheet:
    def _images(self, count: int) -> list[Image.Image]:
        return [Image.new("RGB", (100, 60), (10 * k, 20, 30)) for k in range(count)]

    def test_grid_img_sheet_lays_the_pictures_in_rows_with_room_for_a_label(self) -> None:
        image = sheet(self._images(3), ["a", "b", "c"], cols=2)
        assert image.size == (200, 2 * (60 + 24))

    def test_grid_img_sheet_default_is_eight_columns(self) -> None:
        image = sheet(self._images(10), [str(k) for k in range(10)])
        assert image.size == (800, 2 * (60 + 24))

    def test_grid_img_sheet_fewer_pictures_than_columns_makes_a_narrow_sheet(self) -> None:
        assert sheet(self._images(2), ["a", "b"]).size == (200, 84)

    def test_grid_img_sheet_places_each_picture_in_its_cell_and_writes_the_label(self) -> None:
        image = sheet(self._images(3), ["uno", "dos", "tres"], cols=2)
        assert _pixel(image, 50, 30) == (0, 20, 30)
        assert _pixel(image, 150, 30) == (10, 20, 30)
        assert _pixel(image, 50, 84 + 30) == (20, 20, 30)
        labels = np.all(np.asarray(image)[60:84, :100] == INK, axis=-1)
        assert labels.any()

    @pytest.mark.parametrize(
        ("count", "labels", "cols"), [(0, [], 8), (2, ["a"], 8), (2, ["a", "b"], 0)]
    )
    def test_grid_img_sheet_refuses_what_makes_no_sense(
        self, count: int, labels: list[str], cols: int
    ) -> None:
        with pytest.raises(ValueError):
            sheet(self._images(count), labels, cols)


class TestSheetCapped:
    """001.20 point 5: a sheet has at most 25 Mpx; the cells get narrower until it fits."""

    def test_sheet_capped_a_small_sheet_keeps_the_width_of_its_frames(self) -> None:
        builder = SheetBuilder(3, (200, 100), cols=8)
        assert builder.cell_width == 200
        for k in range(3):
            builder.add(Image.new("RGB", (200, 100), (k, 0, 0)), str(k))
        assert builder.image().size == (600, 100 + 24)

    def test_sheet_capped_64_frames_of_540_by_960_are_shrunk_to_fit_25_mpx(self) -> None:
        builder = SheetBuilder(64, (540, 960), cols=8)
        assert 100 < builder.cell_width < 540
        width, height = builder.image().size
        assert width * height <= 25_000_000
        assert width * height > 20_000_000  # and no more shrunk than it has to be

    def test_sheet_capped_each_frame_is_pasted_resized_and_can_be_dropped(self) -> None:
        builder = SheetBuilder(64, (540, 960), cols=8)
        for k in range(64):
            builder.add(Image.new("RGB", (540, 960), (k, 10, 10)), f"f{k}")
        sheet_image = builder.image()
        cell = builder.cell_width
        assert tuple(np.asarray(sheet_image)[5, 5]) == (0, 10, 10)
        assert tuple(np.asarray(sheet_image)[5, 7 * cell + 5]) == (7, 10, 10)

    def test_sheet_capped_more_frames_than_it_was_built_for_is_refused(self) -> None:
        builder = SheetBuilder(1, (20, 20))
        builder.add(Image.new("RGB", (20, 20)), "a")
        with pytest.raises(ValueError):
            builder.add(Image.new("RGB", (20, 20)), "b")

    def test_sheet_capped_the_function_sheet_follows_the_same_cap(self) -> None:
        images = [Image.new("RGB", (4000, 4000), (9, 9, 9)) for _ in range(2)]
        out = sheet(images, ["a", "b"])
        assert out.size[0] * out.size[1] <= 25_000_000
