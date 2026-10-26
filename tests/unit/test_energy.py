"""Energy analysis: levels per block, silence runs, voice without words, words in silence."""

from typing import ClassVar

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut.analysis.energy import (
    containing_run,
    rms_db,
    rms_db_stream,
    silence_runs,
    voiced_without_words,
    word_in_silence,
)
from kcut.transcribe.model import Word

SR = 16000
HOP = 10


def _signal(*parts: tuple[float, float]) -> NDArray[np.float32]:
    """Consecutive `(seconds, amplitude)` pieces of a 440 Hz-ish square wave at 16 kHz."""
    pieces = []
    for seconds, amplitude in parts:
        n = round(seconds * SR)
        wave = np.where(np.arange(n) % 2 == 0, amplitude, -amplitude)
        pieces.append(wave.astype(np.float32))
    return np.concatenate(pieces)


def _word(s_ms: int, e_ms: int, i: int = 0) -> Word:
    return Word(f"a1:w{i:04d}", i, "x", s_ms, e_ms, 0.9)


class TestRmsDb:
    def test_a_constant_signal_has_the_textbook_level(self) -> None:
        db = rms_db(_signal((1.0, 0.5)), SR)
        assert len(db) == 100
        assert db.dtype == np.float32
        assert np.allclose(db, 20 * np.log10(0.5), atol=1e-4)

    def test_digital_silence_sits_at_the_floor(self) -> None:
        db = rms_db(np.zeros(SR, dtype=np.float32), SR)
        assert np.allclose(db, -180.0, atol=1e-3)

    def test_blocks_follow_the_hop(self) -> None:
        x = _signal((0.5, 0.0), (0.5, 0.5))
        assert len(rms_db(x, SR, hop_ms=20)) == 50
        db = rms_db(x, SR)
        assert db[49] < -100 < -7 < db[50]

    def test_the_short_last_block_is_averaged_over_its_own_samples(self) -> None:
        x = _signal((1.0, 0.0), (0.005, 0.5))  # 1 s of silence + 80 loud samples
        db = rms_db(x, SR)
        assert len(db) == 101
        assert db[-1] == pytest.approx(20 * np.log10(0.5), abs=1e-4)

    def test_empty_input_gives_no_blocks(self) -> None:
        assert len(rms_db(np.zeros(0, dtype=np.float32), SR)) == 0
        assert len(rms_db_stream([], SR)) == 0

    @pytest.mark.parametrize("size", [1, 159, 160, 161, 1000, 4097])
    def test_streaming_in_any_chunk_size_equals_the_whole_signal(self, size: int) -> None:
        rng = np.random.default_rng(7)
        x = (rng.standard_normal(SR * 2 + 77) * 0.1).astype(np.float32)
        chunks = [x[k : k + size] for k in range(0, len(x), size)]
        assert np.array_equal(rms_db_stream(chunks, SR), rms_db(x, SR))


class TestSilenceRuns:
    def test_ranges_are_half_open_and_in_milliseconds(self) -> None:
        db = rms_db(_signal((0.3, 0.5), (0.4, 0.0), (0.3, 0.5)), SR)
        assert silence_runs(db, HOP, -42.0, 250) == [(300, 700)]

    def test_runs_shorter_than_the_minimum_are_dropped(self) -> None:
        db = rms_db(_signal((0.3, 0.5), (0.24, 0.0), (0.3, 0.5), (0.25, 0.0), (0.2, 0.5)), SR)
        assert silence_runs(db, HOP, -42.0, 250) == [(840, 1090)]

    def test_a_silence_at_the_start_and_one_at_the_end(self) -> None:
        db = rms_db(_signal((0.5, 0.0), (0.2, 0.5), (0.6, 0.0)), SR)
        assert silence_runs(db, HOP, -42.0, 250) == [(0, 500), (700, 1300)]

    def test_all_loud_has_no_silence_and_all_quiet_is_one_run(self) -> None:
        assert silence_runs(rms_db(_signal((1.0, 0.5)), SR), HOP, -42.0, 250) == []
        assert silence_runs(rms_db(_signal((1.0, 0.0)), SR), HOP, -42.0, 250) == [(0, 1000)]

    def test_the_threshold_decides_what_is_quiet(self) -> None:
        db = rms_db(_signal((0.5, 0.01), (0.5, 0.5)), SR)  # 0.01 -> -40 dB
        assert silence_runs(db, HOP, -42.0, 250) == []
        assert silence_runs(db, HOP, -30.0, 250) == [(0, 500)]

    def test_nothing_in_nothing_out(self) -> None:
        assert silence_runs(np.zeros(0, dtype=np.float32), HOP, -42.0, 250) == []


class TestVoicedWithoutWords:
    def _db(self) -> NDArray[np.float32]:
        # 0-500 quiet | 500-900 loud (400 ms) | 900-1500 quiet | 1500-1700 loud (200 ms) | quiet
        return rms_db(_signal((0.5, 0.0), (0.4, 0.5), (0.6, 0.0), (0.2, 0.5), (0.3, 0.0)), SR)

    def test_a_loud_stretch_with_no_word_is_reported(self) -> None:
        assert voiced_without_words(self._db(), HOP, -42.0, []) == [(500, 900)]

    def test_a_word_over_the_stretch_hides_it(self) -> None:
        assert voiced_without_words(self._db(), HOP, -42.0, [_word(450, 950)]) == []

    def test_a_word_that_only_grazes_the_stretch_still_hides_it(self) -> None:
        # the word ends at 480 and the tolerance is 50 ms: 480 + 50 > 500
        assert voiced_without_words(self._db(), HOP, -42.0, [_word(100, 480)]) == []

    def test_a_word_just_outside_the_tolerance_does_not_hide_it(self) -> None:
        assert voiced_without_words(self._db(), HOP, -42.0, [_word(100, 450)]) == [(500, 900)]
        assert voiced_without_words(self._db(), HOP, -42.0, [_word(950, 1200)]) == [(500, 900)]

    def test_a_word_just_after_the_stretch_within_the_tolerance_hides_it(self) -> None:
        assert voiced_without_words(self._db(), HOP, -42.0, [_word(940, 1100)]) == []

    def test_stretches_shorter_than_the_minimum_are_ignored(self) -> None:
        assert voiced_without_words(self._db(), HOP, -42.0, [], min_ms=500) == []
        assert voiced_without_words(self._db(), HOP, -42.0, [], min_ms=200) == [
            (500, 900),
            (1500, 1700),
        ]

    def test_a_far_away_long_word_does_not_hide_a_stretch(self) -> None:
        words = [_word(0, 100, 0), _word(1000, 1400, 1)]
        assert voiced_without_words(self._db(), HOP, -42.0, words) == [(500, 900)]

    def test_a_long_early_word_that_reaches_the_stretch_hides_it(self) -> None:
        words = [_word(0, 600, 0), _word(1000, 1100, 1)]
        assert voiced_without_words(self._db(), HOP, -42.0, words) == []


class TestWordInSilence:
    RUNS: ClassVar[list[tuple[int, int]]] = [(1000, 2000), (3000, 3500)]

    @pytest.mark.parametrize(
        ("s_ms", "e_ms", "inside"),
        [
            (1000, 2000, True),
            (1200, 1300, True),
            (999, 1300, False),
            (1500, 2001, False),
            (2000, 2100, False),
            (3100, 3400, True),
            (500, 600, False),
            (4000, 4100, False),
        ],
    )
    def test_the_whole_word_must_fit_in_one_run(self, s_ms: int, e_ms: int, inside: bool) -> None:
        assert word_in_silence(_word(s_ms, e_ms), self.RUNS) is inside

    def test_no_runs_no_silence(self) -> None:
        assert word_in_silence(_word(0, 100), []) is False

    def test_a_word_spanning_two_runs_is_not_in_silence(self) -> None:
        assert word_in_silence(_word(1500, 3200), self.RUNS) is False


class TestContainingRun:
    RUNS: ClassVar[list[tuple[int, int]]] = [(1000, 2000), (3000, 3500)]

    @pytest.mark.parametrize(
        ("t_ms", "run"),
        [
            (1000, (1000, 2000)),
            (1999, (1000, 2000)),
            (2000, None),
            (999, None),
            (3200, (3000, 3500)),
        ],
    )
    def test_start_included_end_excluded(self, t_ms: int, run: tuple[int, int] | None) -> None:
        assert containing_run(self.RUNS, t_ms) == run
