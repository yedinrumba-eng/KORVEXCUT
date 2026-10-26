"""Which words of the transcript stay in the cut and where they fall (spec S1.5a, lesson 4).

The clip of most tests is the voice of `a1` frames 60..240 (2000 ms to 8000 ms of its clock) placed
at output frame 30, at 30 fps: frame `f` of the clip is `f * 1000 / 30` ms.
"""

from kcut.edl.model import Edl
from kcut.edl.words import KeptWord, map_words
from kcut.transcribe.model import Word
from tests.unit.edl_fakes import Doc, edit, parsed

FPS = 30


def _word(i: int, text: str, s_ms: int, e_ms: int, clip: str = "a1") -> Word:
    return Word(f"{clip}:w{i:04d}", i, text, s_ms, e_ms, 0.9)


def _edl(*voices: tuple[int, int, int], src: str = "a1") -> Edl:
    """An EDL whose voice clips are `(at_f, in_f, out_f)` of `src`; the spans do not matter."""

    def change(doc: Doc) -> None:
        doc["clips"] = [
            {"kind": "voice", "src": src, "at_f": at, "in_f": a, "out_f": b, "why": "x"}
            for at, a, b in voices
        ]

    return parsed(edit(change))


ONE = _edl((30, 60, 240))


def _kept(words: list[Word], edl: Edl = ONE) -> list[KeptWord]:
    return map_words(edl, {"a1": words}, FPS)


class TestInside:
    def test_edl_words_a_word_inside_is_placed_by_its_own_times(self) -> None:
        (kept,) = _kept([_word(0, "hola", 3000, 3400)])
        assert (kept.out_s_f, kept.out_e_f) == (60, 72)  # 30 + (3000 - 2000) ms, 42 frames on
        assert (kept.id, kept.text, kept.src, kept.clip_index) == ("a1:w0000", "hola", "a1", 0)
        assert (kept.s_ms, kept.e_ms) == (3000, 3400)

    def test_edl_words_the_fields_come_from_the_word_not_from_the_clip_it_belongs_to(self) -> None:
        edl = _edl((30, 60, 120), (90, 150, 240))
        (kept,) = _kept([_word(5, "tarde", 6000, 6300)], edl)
        assert kept.clip_index == 1 and kept.out_s_f == 90 + 30  # (6000 - 5000) ms into clip 2

    def test_edl_words_a_word_with_no_text_is_dropped(self) -> None:
        assert _kept([_word(0, "", 3000, 3400), _word(1, "queda", 4000, 4300)])[0].id == "a1:w0001"

    def test_edl_words_the_text_is_the_one_it_was_given(self) -> None:
        (kept,) = _kept([_word(0, "Higgsfield,", 3000, 3400)])
        assert kept.text == "Higgsfield,"


class TestLessonFour:
    def test_edl_words_a_word_that_starts_early_is_kept_when_it_ends_well_inside(self) -> None:
        # starts 100 ms before the clip, ends 400 ms into it: it is the first word of the cut
        (kept,) = _kept([_word(0, "temprana", 1900, 2400)])
        assert (kept.out_s_f, kept.out_e_f) == (30, 42)  # it starts where the clip does

    def test_edl_words_the_tail_of_the_word_before_is_not_kept(self) -> None:
        assert (
            _kept([_word(0, "cola", 1500, 2070)]) == []
        )  # ends 70 ms after the cut: 80 are needed
        assert len(_kept([_word(0, "cola", 1500, 2081)])) == 1  # 81 ms in

    def test_edl_words_a_word_that_ends_exactly_at_the_end_is_inside(self) -> None:
        (kept,) = _kept([_word(0, "final", 7500, 8000)])
        assert kept.out_e_f == 30 + 180

    def test_edl_words_a_word_stretched_over_the_cut_is_kept_to_the_end_of_the_clip(self) -> None:
        # Whisper says it ends at 8500 ms, 500 ms after the cut
        (kept,) = _kept([_word(0, "estirada", 7900, 8500)])
        assert (kept.out_s_f, kept.out_e_f) == (207, 210)

    def test_edl_words_a_word_that_starts_too_late_is_the_next_ones(self) -> None:
        assert (
            _kept([_word(0, "tarde", 7960, 8500)]) == []
        )  # starts 40 ms before the cut: 50 needed
        assert len(_kept([_word(0, "justo", 7949, 8500)])) == 1

    def test_edl_words_a_word_that_ends_after_the_cut_and_started_before_the_clip_is_not_kept(
        self,
    ) -> None:
        assert _kept([_word(0, "enorme", 1000, 9000)]) == []  # neither (a) nor (b)

    def test_edl_words_a_word_outside_the_clip_is_not_kept(self) -> None:
        assert _kept([_word(0, "antes", 100, 500), _word(1, "despues", 9000, 9500)]) == []


class TestSeveralClips:
    def test_edl_words_a_word_in_two_clips_stays_with_the_one_it_overlaps_most(self) -> None:
        edl = _edl((30, 60, 240), (270, 230, 300))  # the sources overlap on frames 230..240
        (kept,) = _kept([_word(0, "doble", 7800, 8400)], edl)
        assert kept.clip_index == 1  # 6000 units in the first clip, 18000 in the second

    def test_edl_words_a_tie_goes_to_the_first_clip(self) -> None:
        edl = _edl((30, 60, 240), (300, 60, 240))
        (kept,) = _kept([_word(0, "igual", 3000, 3400)], edl)
        assert kept.clip_index == 0 and kept.out_s_f == 60

    def test_edl_words_the_same_word_is_not_repeated_by_two_clips(self) -> None:
        edl = _edl((30, 60, 240), (300, 60, 240))
        assert len(_kept([_word(0, "una", 3000, 3400)], edl)) == 1

    def test_edl_words_the_result_is_ordered_by_the_output_frame(self) -> None:
        edl = _edl((30, 150, 240), (150, 60, 120))  # the later part of the source comes first
        kept = _kept([_word(0, "dos", 3100, 3400), _word(1, "uno", 5200, 5500)], edl)
        assert [w.text for w in kept] == ["uno", "dos"] and kept[0].out_s_f < kept[1].out_s_f

    def test_edl_words_only_the_sources_the_edl_uses_are_read(self) -> None:
        kept = map_words(
            ONE, {"a1": [_word(0, "si", 3000, 3400)], "a2": [_word(0, "no", 3000, 3400, "a2")]}, FPS
        )
        assert [w.src for w in kept] == ["a1"]
        assert map_words(ONE, {}, FPS) == []

    def test_edl_words_a_clip_of_another_source_takes_its_words(self) -> None:
        edl = _edl((30, 60, 240), src="a2")
        assert map_words(edl, {"a1": [_word(0, "no", 3000, 3400)]}, FPS) == []
        (kept,) = map_words(edl, {"a2": [_word(0, "si", 3000, 3400, "a2")]}, FPS)
        assert kept.src == "a2"


class TestLength:
    def test_edl_words_a_word_is_shown_for_at_least_120_ms(self) -> None:
        (kept,) = _kept([_word(0, "ya", 3000, 3030)])
        assert kept.out_e_f - kept.out_s_f == 4  # 120 ms at 30 fps, rounded up

    def test_edl_words_the_minimum_depends_on_the_fps(self) -> None:
        edl = _edl((60, 120, 480))  # the same 2000 ms to 8000 ms at 60 fps
        (kept,) = map_words(edl, {"a1": [_word(0, "ya", 3000, 3030)]}, 60)
        assert kept.out_e_f - kept.out_s_f == 8

    def test_edl_words_a_word_is_shown_for_at_most_900_ms(self) -> None:
        (kept,) = _kept([_word(0, "larga", 3000, 6000)])
        assert kept.out_e_f - kept.out_s_f == 27

    def test_edl_words_the_minimum_does_not_leave_the_clip(self) -> None:
        (kept,) = _kept([_word(0, "fin", 7970, 8000)])
        assert (kept.out_s_f, kept.out_e_f) == (209, 210)

    def test_edl_words_a_word_that_starts_on_the_last_frame_still_has_one_frame(self) -> None:
        (kept,) = _kept([_word(0, "ultima", 7984, 8000)])
        assert (kept.out_s_f, kept.out_e_f) == (209, 210)

    def test_edl_words_no_word_has_an_empty_or_backwards_interval_or_leaves_its_clip(self) -> None:
        words = [_word(i, f"w{i}", 2000 + 37 * i, 2000 + 37 * i + (i % 7) * 90) for i in range(160)]
        for kept in _kept(words):
            assert 30 <= kept.out_s_f < kept.out_e_f <= 210
