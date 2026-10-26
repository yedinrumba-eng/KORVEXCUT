"""The marks of `transcripcion.md` as the writer draws them: groups, pauses, retakes, frames."""

from kcut.pack.writer import MdClip, MdPhrase, MdWord, render_md

W = MdWord


class TestMarks:
    def _line(self, words: list[MdWord], **kw: object) -> str:
        phrase = MdPhrase(1000, 2000, kw.pop("pause", None), words, **kw)  # type: ignore[arg-type]
        clip = MdClip("a1", "crudo/x.mov", phrases=[phrase])
        return render_md("p", 30, 700, [clip]).splitlines()[-1]

    def test_a_two_word_filler_shares_one_group(self) -> None:
        line = self._line([W("pues"), W("o", "F"), W("sea", "F"), W("vamos")])
        assert line == "[f30-60 | 1.00-2.00] pues {o sea} vamos"

    def test_separate_fillers_get_separate_groups(self) -> None:
        line = self._line([W("eh", "F"), W("hola"), W("em", "F")])
        assert line.endswith("{eh} hola {em}")

    def test_doubtful_words_end_in_a_question_mark(self) -> None:
        assert self._line([W("hola", "?"), W("que")]).endswith("hola? que")

    def test_other_camera_goes_in_square_brackets_after_the_question_mark(self) -> None:
        assert self._line([W("te", "?", "de")]).endswith("te?[≠de]")

    def test_a_possible_hallucination_is_annotated(self) -> None:
        assert self._line([W("Gracias.", "H")]).endswith("Gracias. (¿alucinacion?)")

    def test_a_repetition_groups_the_word_and_its_repeats(self) -> None:
        line = self._line([W("ya"), W("ya", "R"), W("ya", "R"), W("sí")])
        assert line.endswith("«ya ya ya» sí")

    def test_two_separate_repetitions(self) -> None:
        line = self._line([W("a"), W("a", "R"), W("b"), W("c"), W("c", "R")])
        assert line.endswith("«a a» b «c c»")

    def test_fillers_inside_a_repetition_are_grouped_inside_it(self) -> None:
        line = self._line([W("eh", "F"), W("eh", "FR"), W("hola")])
        assert line.endswith("«{eh eh}» hola")

    def test_a_filler_run_is_cut_at_the_edge_of_a_repetition(self) -> None:
        line = self._line([W("este", "F"), W("este", "FR"), W("o", "F")])
        assert line.endswith("«{este este}» {o}")

    def test_the_corrected_flag_is_not_shown(self) -> None:
        assert self._line([W("Higgsfield,", "C")]).endswith("] Higgsfield,")

    def test_pause_lines(self) -> None:
        assert "(pausa 0.30 s) hola" in self._line([W("hola")], pause=300)
        assert "(pausa 0.69 s) hola" in self._line([W("hola")], pause=690)
        assert "(pausa 0.70 s LARGA) hola" in self._line([W("hola")], pause=700)
        assert "(pausa" not in self._line([W("hola")], pause=0)
        assert "(pausa" not in self._line([W("hola")], pause=None)

    def test_retake_marker_uses_the_floor_frame_of_the_earlier_phrase(self) -> None:
        assert self._line([W("hola")], retake_of_ms=48_700).endswith("hola ⟳ f1461")

    def test_frames_floor_the_start_and_ceil_the_end(self) -> None:
        phrase = MdPhrase(1001, 1999, None, [W("x")])
        text = render_md("p", 30, 700, [MdClip("a1", "f", phrases=[phrase])])
        assert "[f30-60 | 1.00-2.00] x" in text
        phrase = MdPhrase(1000, 2001, None, [W("x")])
        text = render_md("p", 30, 700, [MdClip("a1", "f", phrases=[phrase])])
        assert "[f30-61 | 1.00-2.00] x" in text

    def test_frames_follow_the_project_fps(self) -> None:
        phrase = MdPhrase(1000, 2000, None, [W("x")])
        text = render_md("p", 24, 700, [MdClip("a1", "f", phrases=[phrase])])
        assert "fps 24 ·" in text and "[f24-48 | 1.00-2.00] x" in text
