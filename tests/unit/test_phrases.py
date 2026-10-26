"""Phrases cut by measured silences, with edges trimmed by energy (lesson 2)."""

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from kcut.analysis.energy import rms_db, silence_runs
from kcut.pack.phrases import Phrase, split_phrases
from kcut.transcribe.model import Word


def _words(*spans: tuple[str, int, int]) -> list[Word]:
    return [Word(f"a1:w{i:04d}", i, text, s, e, 0.9) for i, (text, s, e) in enumerate(spans)]


def _texts(phrases: Sequence[Phrase]) -> list[list[str]]:
    return [[w.text for w in p.words] for p in phrases]


def _edges(phrases: Sequence[Phrase]) -> list[tuple[int, int, int | None]]:
    return [(p.start_ms, p.end_ms, p.pause_before_ms) for p in phrases]


class TestCuts:
    def test_no_words_no_phrases(self) -> None:
        assert split_phrases([], [(0, 1000)], 300) == []

    def test_without_silences_everything_is_one_phrase(self) -> None:
        words = _words(("hola", 100, 400), ("que", 450, 700), ("tal", 750, 1000))
        phrases = split_phrases(words, [], 300)
        assert _texts(phrases) == [["hola", "que", "tal"]]
        assert _edges(phrases) == [(100, 1000, None)]

    def test_a_silence_of_at_least_the_phrase_pause_cuts_before_the_next_word(self) -> None:
        words = _words(("hola", 100, 400), ("que", 800, 1000), ("tal", 1050, 1200))
        phrases = split_phrases(words, [(450, 750)], 300)  # exactly 300 ms: cuts
        assert _texts(phrases) == [["hola"], ["que", "tal"]]
        assert _edges(phrases) == [(100, 400, None), (800, 1200, 400)]

    def test_a_shorter_silence_does_not_cut(self) -> None:
        words = _words(("hola", 100, 400), ("que", 700, 1000))
        assert _texts(split_phrases(words, [(450, 749)], 300)) == [["hola", "que"]]

    def test_the_cut_goes_before_the_first_word_that_starts_50_ms_after_the_silence_began(
        self,
    ) -> None:
        # silence from 500: a word starting at 549 is still "before" it, one at 550 is after
        words = _words(("a", 100, 400), ("b", 549, 600), ("c", 900, 1000))
        assert _texts(split_phrases(words, [(500, 900)], 300)) == [["a", "b"], ["c"]]
        words = _words(("a", 100, 400), ("b", 550, 600), ("c", 900, 1000))
        assert _texts(split_phrases(words, [(500, 900)], 300)) == [["a"], ["b", "c"]]

    def test_two_silences_that_point_at_the_same_word_make_one_cut(self) -> None:
        words = _words(("a", 100, 400), ("b", 2000, 2100))
        runs = [(450, 800), (900, 1900)]
        assert _texts(split_phrases(words, runs, 300)) == [["a"], ["b"]]

    def test_a_silence_after_the_last_word_cuts_nothing(self) -> None:
        words = _words(("a", 100, 400), ("b", 450, 600))
        assert len(split_phrases(words, [(700, 2000)], 300)) == 1

    def test_a_silence_before_the_first_word_cuts_nothing(self) -> None:
        words = _words(("a", 1000, 1200), ("b", 1250, 1400))
        phrases = split_phrases(words, [(0, 900)], 300)
        assert _texts(phrases) == [["a", "b"]]
        assert phrases[0].start_ms == 1000 and phrases[0].pause_before_ms is None

    def test_the_phrase_pause_is_the_threshold_not_the_long_pause(self) -> None:
        words = _words(("a", 0, 100), ("b", 500, 600))
        assert len(split_phrases(words, [(150, 450)], 300)) == 2
        assert len(split_phrases(words, [(150, 450)], 301)) == 1


class TestEdgesByEnergy:
    def test_the_stretched_con_of_1_68_s_ends_where_the_voice_ends(self) -> None:
        """Whisper says "con" lasts 1.68 s; the audio says 0.3 s of voice and then silence."""
        words = _words(("bueno", 1000, 1400), ("con", 1500, 3180), ("ven", 3500, 3900))
        runs = [(1800, 3450)]
        phrases = split_phrases(words, runs, 300)
        assert _texts(phrases) == [["bueno", "con"], ["ven"]]
        assert _edges(phrases) == [(1000, 1800, None), (3500, 3900, 1700)]

    def test_the_same_case_measured_from_real_samples(self) -> None:
        sr = 16000

        def piece(seconds: float, amplitude: float) -> NDArray[np.float32]:
            n = round(seconds * sr)
            return np.where(np.arange(n) % 2 == 0, amplitude, -amplitude).astype(np.float32)

        x = np.concatenate([piece(1.0, 0), piece(0.8, 0.5), piece(1.65, 0), piece(0.4, 0.5)])
        runs = silence_runs(rms_db(x, sr), 10, -42.0, 250)
        assert runs == [(0, 1000), (1800, 3450)]
        words = _words(("bueno", 1010, 1400), ("con", 1500, 3180), ("ven", 3450, 3850))
        phrases = split_phrases(words, runs, 300)
        assert _edges(phrases) == [(1010, 1800, None), (3450, 3850, 1650)]

    def test_a_start_inside_a_silence_moves_to_where_the_silence_ends(self) -> None:
        words = _words(("a", 100, 300), ("b", 1000, 1200))
        phrases = split_phrases(words, [(500, 1100)], 300)  # "b" starts inside the silence
        assert _edges(phrases) == [(100, 300, None), (1100, 1200, 800)]

    def test_a_start_exactly_where_a_silence_ends_is_not_inside_it(self) -> None:
        words = _words(("a", 100, 300), ("b", 1100, 1200))
        assert split_phrases(words, [(500, 1100)], 300)[1].start_ms == 1100

    def test_an_end_inside_a_silence_moves_to_where_the_silence_starts(self) -> None:
        words = _words(("a", 100, 600), ("b", 1500, 1700))
        phrases = split_phrases(words, [(400, 1400)], 300)
        assert _edges(phrases) == [(100, 400, None), (1500, 1700, 1100)]

    def test_an_end_exactly_where_a_silence_ends_counts_as_inside(self) -> None:
        words = _words(("a", 100, 800), ("b", 1500, 1700))
        assert split_phrases(words, [(400, 800)], 300)[0].end_ms == 400

    def test_an_end_exactly_where_a_silence_starts_is_not_inside_it(self) -> None:
        words = _words(("a", 100, 400), ("b", 1500, 1700))
        assert split_phrases(words, [(400, 800)], 300)[0].end_ms == 400

    def test_a_silence_shorter_than_the_phrase_pause_still_trims_the_edges(self) -> None:
        words = _words(("a", 100, 300), ("b", 400, 600))
        phrases = split_phrases(words, [(500, 700)], 300)  # 200 ms: no cut, but "b" ends inside
        assert _texts(phrases) == [["a", "b"]]
        assert _edges(phrases) == [(100, 500, None)]

    def test_when_the_trim_leaves_nothing_the_raw_times_are_used(self) -> None:
        words = _words(("a", 100, 300), ("b", 1200, 1300))
        # "b" starts and ends inside one silence: start -> 1900, end -> 1000, so end <= start
        phrases = split_phrases(words, [(1000, 1900)], 300)
        assert phrases[1].start_ms == 1200 and phrases[1].end_ms == 1300

    def test_pause_before_uses_the_trimmed_edges(self) -> None:
        words = _words(("a", 0, 900), ("b", 1000, 1200), ("c", 2400, 2600))
        runs = [(300, 950), (1250, 2350)]
        phrases = split_phrases(words, runs, 300)
        assert _edges(phrases) == [(0, 300, None), (1000, 1200, 700), (2400, 2600, 1200)]
