"""The picture of a stretch of audio (spec S1.4, 001.15): size, bands, words, notice, filmstrip."""

import time
from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray
from PIL import Image

from kcut.config.load import parse_config
from kcut.console import safe_text
from kcut.viz.draw import fit_text
from kcut.viz.timeline import (
    BAND,
    DOUBTFUL,
    SURE,
    THRESHOLD,
    WHITE,
    ViewWord,
    render_timeline,
    window_silences,
)

CFG = parse_config("", default_name="x").analysis
FPS = 30
LOUD = np.full(500, -20.0, dtype=np.float32)  # 5 s of 10 ms blocks, well above the threshold
BAND_ROW = 41  # inside the bands, above every bar and every label


def _render(
    *,
    db: NDArray[np.float32] = LOUD,
    silences: list[tuple[int, int]] | None = None,
    words: list[ViewWord] | None = None,
    start_f: int = 0,
    end_f: int = 150,
    filmstrip: list[NDArray[np.uint8]] | None = None,
    notice: str | None = None,
) -> Image.Image:
    return render_timeline(
        db, silences or [], words or [], start_f, end_f, FPS, CFG, filmstrip, notice
    )


def _pixels(image: Image.Image) -> NDArray[np.uint8]:
    return np.asarray(image.convert("RGB"))


def _has(image: Image.Image, color: tuple[int, int, int]) -> bool:
    return bool(np.any(np.all(_pixels(image) == color, axis=-1)))


def _bands(image: Image.Image) -> int:
    """How many separate stretches of the band color there are along the band row."""
    row = np.all(_pixels(image)[BAND_ROW] == BAND, axis=-1).astype(np.int8)
    return int(np.sum(np.diff(np.concatenate([[0], row])) == 1))


def _word(text: str, s_ms: int, e_ms: int, doubtful: bool, n: int = 31) -> ViewWord:
    return ViewWord(f"a1:w{n:04d}", text, s_ms, e_ms, doubtful)


def _frames(count: int, shape: tuple[int, int] = (96, 54)) -> list[NDArray[np.uint8]]:
    return [np.full((shape[0], shape[1], 3), 40 * (k + 1), dtype=np.uint8) for k in range(count)]


class TestSize:
    def test_timeline_img_without_a_filmstrip_is_2400_by_420(self) -> None:
        assert _render().size == (2400, 420)

    def test_timeline_img_with_a_filmstrip_it_grows_220_on_top(self) -> None:
        image = _render(filmstrip=_frames(6))
        assert image.size == (2400, 640)
        pixels = _pixels(image)
        assert pixels[0:220].std() > 0  # the frames are up there
        assert tuple(pixels[225, 5]) == (18, 18, 22)  # and the timeline below keeps its background

    def test_timeline_img_every_frame_of_the_strip_is_drawn_in_its_own_cell(self) -> None:
        pixels = _pixels(_render(filmstrip=_frames(4)))
        cell = 2400 // 4
        for k in range(4):
            middle = pixels[110, k * cell + cell // 2]
            assert tuple(middle) == (40 * (k + 1),) * 3  # BGR frame of one gray: the same in RGB

    def test_timeline_img_a_hole_in_the_strip_stays_gray(self) -> None:
        hole = np.full((96, 54, 3), (46, 40, 40), dtype=np.uint8)  # BGR of (40, 40, 46)
        pixels = _pixels(_render(filmstrip=[hole, hole]))
        assert tuple(pixels[110, 600]) == (40, 40, 46)

    def test_timeline_img_a_window_without_frames_is_refused(self) -> None:
        with pytest.raises(ValueError):
            _render(start_f=30, end_f=30)


class TestBands:
    def test_timeline_img_one_band_per_silence(self) -> None:
        silences = [(500, 900), (1500, 2100), (3000, 3500)]
        assert _bands(_render(silences=silences)) == 3

    def test_timeline_img_no_silences_no_bands(self) -> None:
        assert _bands(_render()) == 0

    def test_timeline_img_a_silence_outside_the_window_has_no_band(self) -> None:
        assert _bands(_render(silences=[(6000, 7000), (500, 900)])) == 1

    def test_timeline_img_a_silence_that_crosses_the_edge_is_clipped_to_it(self) -> None:
        image = _render(silences=[(-300, 400), (4700, 6000)])
        assert _bands(image) == 2
        row = np.all(_pixels(image)[BAND_ROW] == BAND, axis=-1)
        assert row[0] and row[-1]  # both reach the border of the picture

    def test_timeline_img_window_silences_touch_in_whole_units(self) -> None:
        # [0, 100) ms ends before frame 3 (100 ms at 30 fps) starts; [0, 101) does not
        assert window_silences([(0, 100)], 3, 6, FPS) == []
        assert window_silences([(0, 101)], 3, 6, FPS) == [(0, 101)]
        assert window_silences([(200, 300)], 3, 6, FPS) == []  # starts when frame 6 does


class TestWords:
    def test_timeline_img_a_doubtful_word_is_orange_and_a_sure_one_is_yellow(self) -> None:
        sure = _render(words=[_word("hola", 500, 1500, False)])
        doubt = _render(words=[_word("hola", 500, 1500, True)])
        assert _has(sure, SURE) and not _has(sure, DOUBTFUL)
        assert _has(doubt, DOUBTFUL) and not _has(doubt, SURE)

    def test_timeline_img_both_colors_in_one_picture(self) -> None:
        words = [_word("uno", 300, 900, False, 1), _word("dos", 1200, 1800, True, 2)]
        image = _render(words=words)
        assert _has(image, SURE) and _has(image, DOUBTFUL)

    def test_timeline_img_no_words_no_word_colors(self) -> None:
        image = _render()
        assert not _has(image, SURE) and not _has(image, DOUBTFUL)

    def test_timeline_img_the_words_take_three_staggered_rows(self) -> None:
        words = [_word(f"w{k}", 100 + k * 40, 130 + k * 40, False, k) for k in range(6)]
        pixels = _pixels(_render(words=words))
        rows = {y for y in range(340, 420) if np.any(np.all(pixels[y] == SURE, axis=-1))}
        assert min(rows) == 348 and max(rows) >= 396  # three rows of 20 pixels, 24 apart

    def test_timeline_img_the_word_box_sits_under_its_time(self) -> None:
        pixels = _pixels(_render(words=[_word("hola", 1000, 2000, False)]))
        columns = np.flatnonzero(np.all(pixels[352] == SURE, axis=-1))
        left, right = 2400 * 1000 // 5000, 2400 * 2000 // 5000
        assert abs(int(columns.min()) - left) <= 4  # the label's box reaches 3 pixels to the left
        assert columns.max() >= right - 2

    def test_timeline_img_a_word_wider_than_the_window_does_not_break_it(self) -> None:
        image = _render(words=[_word("largo", -5000, 9000, True)])
        assert image.size == (2400, 420) and _has(image, DOUBTFUL)


class TestNoticeAndWave:
    def test_timeline_img_a_notice_with_no_words_is_drawn_anyway(self) -> None:
        image = _render(notice="sin transcripcion")
        top_left = _pixels(image)[:40, :700]
        assert bool(np.any(np.all(top_left == WHITE, axis=-1)))

    def test_timeline_img_without_a_notice_nothing_is_that_white(self) -> None:
        assert not _has(_render(silences=[(500, 900)], words=[_word("a", 1, 400, False)]), WHITE)

    def test_timeline_img_the_level_is_drawn_and_a_silent_window_has_no_bars(self) -> None:
        bar = (120, 200, 255)
        assert _has(_render(), bar)
        assert not _has(_render(db=np.full(500, -90.0, dtype=np.float32)), bar)

    def test_timeline_img_the_threshold_line_is_at_the_configured_level(self) -> None:
        pixels = _pixels(_render())
        # -42 dB is 28/70 of the way up the 250 px of the wave zone: 300 - 100
        assert tuple(pixels[200, 5]) == THRESHOLD

    def test_timeline_img_is_a_pure_function_of_its_inputs(self) -> None:
        args = {"silences": [(500, 900)], "words": [_word("hola", 500, 1500, False)]}
        assert _pixels(_render(**args)).tobytes() == _pixels(_render(**args)).tobytes()

    def test_timeline_img_a_minute_of_audio_draws_fast(self) -> None:
        db = np.random.default_rng(3).uniform(-80, -10, 6000).astype(np.float32)
        started = time.monotonic()
        image = _render(db=db, start_f=0, end_f=1800, silences=[(1000, 2000)])
        assert time.monotonic() - started < 2.0 and image.size == (2400, 420)


class TestWordTextAndBoxesCapped:
    """001.20 point 6: the text of a box is `safe_text`, one line, 24 characters at most; no more
    than 400 boxes are drawn."""

    def _drawn(self, monkeypatch: pytest.MonkeyPatch, words: list[ViewWord]) -> list[str]:
        from kcut.viz import timeline

        texts: list[str] = []
        original = timeline.text_box

        def spy(draw: Any, xy: Any, text: str, *rest: Any) -> None:
            texts.append(text)
            original(draw, xy, text, *rest)

        monkeypatch.setattr(timeline, "text_box", spy)
        _render(words=words)
        return texts

    def test_word_text_capped_a_long_text_is_cut_to_24_characters_with_an_ellipsis(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        label = self._drawn(monkeypatch, [_word("x" * 200, 500, 900, False)])[-1]
        text, _, suffix = label.rpartition(" ")
        assert len(text) == 24 and text.endswith("…") and suffix == "w0031"

    def test_word_text_capped_a_text_of_24_characters_is_whole(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        label = self._drawn(monkeypatch, [_word("y" * 24, 500, 900, False)])[-1]
        assert label == "y" * 24 + " w0031"

    def test_word_text_capped_it_is_one_line_and_has_no_control_characters(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        hostile = ["uno\ndos", "\x1b[31mrojo", "\u202etxet", "a\u200bb", "\x00nul", "tab\tbed"]
        words = [_word(t, 100 + k * 300, 350 + k * 300, False, k) for k, t in enumerate(hostile)]
        labels = self._drawn(monkeypatch, words)[-len(hostile) :]
        for label in labels:
            assert label == safe_text(label) and "\n" not in label
        assert labels[0].startswith("uno dos ")  # the newline became a space

    def test_word_text_capped_fit_text_by_itself(self) -> None:
        assert fit_text("hola") == "hola" and fit_text("") == ""
        assert fit_text("z" * 25) == "z" * 23 + "…"
        assert fit_text("a\nb\rc") == "a b\\x0dc"
        assert len(fit_text("\x1b" * 100)) == 24 and fit_text("x" * 10**6).endswith("…")

    def test_boxes_capped_no_more_than_400_boxes_are_drawn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from kcut.viz import timeline

        words = [_word("w", 10 + k * 8, 14 + k * 8, False, k) for k in range(650)]
        boxes: list[ViewWord] = []
        original = timeline._word_box

        def spy(draw: Any, word: ViewWord, y: int, at: Any) -> None:
            boxes.append(word)
            original(draw, word, y, at)

        monkeypatch.setattr(timeline, "_word_box", spy)
        _render(words=words)
        assert timeline.MAX_BOXES == 400 and len(boxes) == 400
        assert [w.id for w in boxes] == [w.id for w in words[:400]]  # the first 400

    def test_boxes_capped_400_or_fewer_are_all_drawn(self, monkeypatch: pytest.MonkeyPatch) -> None:
        texts = self._drawn(
            monkeypatch, [_word("w", 10 + k * 8, 14 + k * 8, False, k) for k in range(400)]
        )
        assert sum(1 for t in texts if t.startswith("w w")) == 400
