"""Markers: fillers (also of two words), stutters, doubtful words, hallucinations, retakes."""

from collections.abc import Sequence
from dataclasses import replace

import pytest

from kcut.pack.markers import FLAG_ORDER, filler_sequences, retakes, word_flags
from kcut.pack.phrases import Phrase
from kcut.transcribe.model import Word

FILLERS = filler_sequences(["eh", "este", "o sea", "mmm", "bueno", "pues"])


def _words(text: str, p: float = 0.9, start: int = 0, step: int = 400) -> list[Word]:
    return [
        Word(f"a1:w{start + i:04d}", start + i, token, i * step, i * step + step - 50, p)
        for i, token in enumerate(text.split())
    ]


def _flags(text: str, fillers: Sequence[tuple[str, ...]] = FILLERS, **kw: object) -> list[str]:
    words = _words(text)
    for key, value in kw.items():
        index, field = key.split("_", 1)
        words[int(index)] = replace(words[int(index)], **{field: value})
    return word_flags(words, fillers, 0.5, [])


def _phrase(text: str, start_ms: int) -> Phrase:
    words = _words(text)
    return Phrase(words, start_ms, start_ms + 400 * len(words), None)


class TestFillers:
    def test_single_word_fillers(self) -> None:
        assert _flags("¿Te da curiosidad de la eh IA") == ["", "", "", "", "", "F", ""]

    def test_the_two_word_filler_marks_both_words(self) -> None:
        assert _flags("pues o sea vamos") == ["F", "F", "F", ""]

    def test_matching_ignores_case_accents_and_punctuation(self) -> None:
        assert _flags("Eh, ¿O SEA? Éste ÉSTA") == ["F", "F", "F", "F", ""]  # "éste" -> "este"
        assert _flags("Pues, BUENO.") == ["F", "F"]

    def test_the_longest_filler_wins_and_sequences_do_not_overlap(self) -> None:
        fillers = filler_sequences(["o", "o sea", "sea"])
        assert word_flags(_words("o sea"), fillers, 0.5, []) == ["F", "F"]
        assert word_flags(_words("sea o"), fillers, 0.5, []) == ["F", "F"]

    def test_half_of_a_two_word_filler_is_not_a_filler(self) -> None:
        assert _flags("o vamos sea") == ["", "", ""]

    def test_fillers_that_normalize_to_nothing_are_dropped(self) -> None:
        assert filler_sequences(["", "...", "¿?", "eh"]) == [("eh",)]
        assert _flags("hola", filler_sequences(["..."])) == [""]

    def test_longest_sequences_come_first(self) -> None:
        assert filler_sequences(["a", "b c d", "e f"]) == [("b", "c", "d"), ("e", "f"), ("a",)]


class TestStutter:
    def test_the_repeat_is_marked_and_the_first_one_is_not(self) -> None:
        assert _flags("qué con con bueno") == ["", "", "R", "F"]

    def test_three_in_a_row_mark_the_second_and_the_third(self) -> None:
        assert _flags("ya ya ya") == ["", "R", "R"]

    def test_the_comparison_is_by_normalized_token(self) -> None:
        assert _flags("Sí, si SÍ") == ["", "R", "R"]

    def test_the_first_word_of_a_phrase_is_never_a_repeat(self) -> None:
        assert _flags("hola") == [""]

    def test_non_adjacent_repeats_are_not_stutters(self) -> None:
        assert _flags("la casa la") == ["", "", ""]

    def test_punctuation_only_words_do_not_repeat(self) -> None:
        assert _flags("- -") == ["", ""]


class TestDoubtAndHallucination:
    def test_probability_below_the_threshold_is_doubtful(self) -> None:
        assert _flags("a b c", **{"1_p": 0.49}) == ["", "?", ""]

    def test_probability_equal_to_the_threshold_is_not_doubtful(self) -> None:
        assert _flags("a b c", **{"1_p": 0.5}) == ["", "", ""]

    def test_a_word_inside_a_silence_is_a_possible_hallucination(self) -> None:
        words = _words("gracias")  # 0..350 ms
        assert word_flags(words, FILLERS, 0.5, [(0, 1000)]) == ["H"]
        assert word_flags(words, FILLERS, 0.5, [(100, 1000)]) == [""]  # starts before the silence
        assert word_flags(words, FILLERS, 0.5, [(0, 300)]) == [""]  # ends after it

    def test_a_corrected_word_is_flagged(self) -> None:
        assert _flags("a b", **{"0_corrected": True}) == ["C", ""]

    def test_flags_come_in_the_documented_order(self) -> None:
        words = [
            Word("a1:w0000", 0, "eh", 0, 350, 0.1, True),
            Word("a1:w0001", 1, "eh", 400, 750, 0.1, True),
        ]
        flags = word_flags(words, FILLERS, 0.5, [(0, 1000)])
        assert flags == ["F?HC", "FR?HC"]
        assert all(list(f) == sorted(f, key=FLAG_ORDER.index) for f in flags)


class TestRetakes:
    def test_a_similar_earlier_phrase_is_a_retake(self) -> None:
        first = _phrase("te da curiosidad de la ia", 1000)
        again = _phrase("te da curiosidad de la IA y no sabes", 9000)
        assert retakes([first, again]) == [None, 1000]

    def test_the_most_recent_matching_phrase_wins(self) -> None:
        phrases = [
            _phrase("vamos a ver como funciona esto", 1000),
            _phrase("vamos a ver como funciona esto", 5000),
            _phrase("algo totalmente distinto aqui", 9000),
            _phrase("vamos a ver como funciona esto", 13000),
        ]
        assert retakes(phrases) == [None, 1000, None, 5000]

    def test_different_phrases_are_not_retakes(self) -> None:
        phrases = [
            _phrase("hoy hablamos de edicion", 1000),
            _phrase("gracias por ver el video", 5000),
        ]
        assert retakes(phrases) == [None, None]

    def test_the_earlier_phrase_needs_three_tokens(self) -> None:
        phrases = [_phrase("vamos a", 1000), _phrase("vamos a ver", 5000)]
        assert retakes(phrases) == [None, None]
        phrases = [_phrase("vamos a ver", 1000), _phrase("vamos a ver", 5000)]
        assert retakes(phrases) == [None, 1000]

    def test_sixty_seconds_is_the_limit(self) -> None:
        a = _phrase("vamos a ver como funciona", 1000)
        assert retakes([a, _phrase("vamos a ver como funciona", 61_000)]) == [None, 1000]
        assert retakes([a, _phrase("vamos a ver como funciona", 61_001)]) == [None, None]

    def test_the_ratio_threshold_is_075(self) -> None:
        base = _phrase("uno dos tres cuatro", 1000)
        # 3 of 4 tokens in common over 4 + 4: ratio 0.75 -> retake; 2 of 4 -> 0.5 -> not
        assert retakes([base, _phrase("uno dos tres cinco", 5000)]) == [None, 1000]
        assert retakes([base, _phrase("uno dos seis cinco", 5000)]) == [None, None]

    def test_accents_and_case_do_not_hide_a_retake(self) -> None:
        a = _phrase("Qué bueno está esto", 1000)
        b = _phrase("que BUENO esta esto", 4000)
        assert retakes([a, b]) == [None, 1000]

    @pytest.mark.parametrize("count", [0, 1])
    def test_few_phrases(self, count: int) -> None:
        assert retakes([_phrase("uno dos tres", 0)][:count]) == [None] * count
