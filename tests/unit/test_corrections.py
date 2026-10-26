"""Corrections by word id + expected text (spec DS8): expect, delete, split, mismatch."""

from itertools import pairwise
from typing import Any

import pytest

from kcut.errors import CheckFailed, ProjectError
from kcut.text.corrections import (
    Correction,
    apply,
    mismatch_message,
    parse_corrections,
    unmatched,
)
from kcut.transcribe.model import Word

DOC = {
    "schema": "kcut.correcciones/1",
    "items": [
        {"word": "a1:w0031", "expect": "Hicksville,", "text": "Higgsfield,", "why": "glosario"},
        {"word": "a1:w0301", "expect": "por", "text": "por su", "why": "confirmado por Yedin"},
        {"word": "a1:w0400", "expect": "Gracias.", "text": "", "why": "alucinacion sobre silencio"},
    ],
}


def _word(i: int, text: str, s_ms: int = 1000, e_ms: int = 1500, clip: str = "a1") -> Word:
    return Word(f"{clip}:w{i:04d}", i, text, s_ms, e_ms, 0.9)


def _fail(doc: Any) -> str:
    with pytest.raises(ProjectError) as info:
        parse_corrections(doc)
    return info.value.message_es


class TestParse:
    def test_the_spec_example_loads(self) -> None:
        corr = parse_corrections(DOC)
        assert sorted(corr) == ["a1:w0031", "a1:w0301", "a1:w0400"]
        assert corr["a1:w0031"] == Correction("a1:w0031", "Hicksville,", "Higgsfield,", "glosario")

    def test_why_is_optional(self) -> None:
        doc = {"schema": DOC["schema"], "items": [{"word": "a1:w0001", "expect": "x", "text": "y"}]}
        assert parse_corrections(doc)["a1:w0001"].why == ""

    def test_empty_items_are_fine(self) -> None:
        assert parse_corrections({"schema": DOC["schema"], "items": []}) == {}

    @pytest.mark.parametrize(
        ("doc", "path"),
        [
            ([], "debe ser un objeto"),
            ({"schema": "otro/1", "items": []}, "schema"),
            ({"schema": DOC["schema"]}, "items"),
            ({"schema": DOC["schema"], "items": [], "extra": 1}, "<clave desconocida>"),
            ({"schema": DOC["schema"], "items": [3]}, "items[0]"),
            (
                {"schema": DOC["schema"], "items": [{"word": "a1:w0001", "expect": "x"}]},
                "items[0].text",
            ),
            (
                {"schema": DOC["schema"], "items": [{"word": "a1:w0001", "text": "x"}]},
                "items[0].expect",
            ),
            (
                {"schema": DOC["schema"], "items": [{"word": "a1:w1", "expect": "x", "text": "y"}]},
                "items[0].word",
            ),
            (
                {
                    "schema": DOC["schema"],
                    "items": [{"word": "a1:w0001.1", "expect": "x", "text": "y"}],
                },
                "items[0].word",
            ),
            (
                {
                    "schema": DOC["schema"],
                    "items": [{"word": "a1:w0001", "expect": "", "text": "y"}],
                },
                "items[0].expect",
            ),
            (
                {
                    "schema": DOC["schema"],
                    "items": [{"word": "a1:w0001", "expect": "x", "text": "y", "color": 1}],
                },
                "items[0].<clave desconocida>",
            ),
            (
                {
                    "schema": DOC["schema"],
                    "items": [{"word": "a1:w0001", "expect": "x", "text": 5}],
                },
                "items[0].text",
            ),
        ],
    )
    def test_invalid_documents_name_their_path(self, doc: Any, path: str) -> None:
        assert path in _fail(doc)

    def test_one_correction_per_word(self) -> None:
        item = {"word": "a1:w0001", "expect": "x", "text": "y"}
        message = _fail({"schema": DOC["schema"], "items": [item, item]})
        assert "items[1].word" in message and "repetida" in message


class TestApply:
    def test_a_replacement_keeps_the_timing_and_marks_the_word(self) -> None:
        words = [_word(30, "Hola"), _word(31, "Hicksville,", 2000, 2600), _word(32, "bien")]
        done = apply(words, parse_corrections(DOC))
        assert [w.text for w in done] == ["Hola", "Higgsfield,", "bien"]
        assert (done[1].id, done[1].s_ms, done[1].e_ms, done[1].p) == ("a1:w0031", 2000, 2600, 0.9)
        assert [w.corrected for w in done] == [False, True, False]

    def test_untouched_words_are_the_same_objects(self) -> None:
        words = [_word(1, "a"), _word(2, "b")]
        assert apply(words, parse_corrections(DOC)) == words

    def test_an_empty_text_deletes_the_word_but_keeps_it_in_the_list(self) -> None:
        done = apply([_word(400, "Gracias.")], parse_corrections(DOC))
        assert [(w.id, w.text, w.corrected) for w in done] == [("a1:w0400", "", True)]

    def test_several_words_split_the_duration_in_proportion_to_their_length(self) -> None:
        # "por su": lengths 3 and 2 over 1000 ms -> 600 and 400
        done = apply([_word(301, "por", 10_000, 11_000)], parse_corrections(DOC))
        assert [(w.id, w.text, w.s_ms, w.e_ms) for w in done] == [
            ("a1:w0301", "por", 10_000, 10_600),
            ("a1:w0301.1", "su", 10_600, 11_000),
        ]
        assert all(w.corrected and w.i == 301 and w.p == 0.9 for w in done)

    def test_the_last_token_absorbs_the_rounding_remainder(self) -> None:
        corr = {"a1:w0005": Correction("a1:w0005", "x", "uno dos tres", "")}
        done = apply([_word(5, "x", 0, 100)], corr)
        # lengths 3, 3, 4 over 100 ms -> 30, 30 and the rest (40)
        assert [(w.id, w.s_ms, w.e_ms) for w in done] == [
            ("a1:w0005", 0, 30),
            ("a1:w0005.1", 30, 60),
            ("a1:w0005.2", 60, 100),
        ]

    def test_split_pieces_are_contiguous_and_cover_the_word(self) -> None:
        corr = {"a1:w0005": Correction("a1:w0005", "x", "a bb ccc dddd eeeee", "")}
        done = apply([_word(5, "x", 777, 1234)], corr)
        assert done[0].s_ms == 777 and done[-1].e_ms == 1234
        assert all(a.e_ms == b.s_ms for a, b in pairwise(done))
        assert [w.id for w in done] == ["a1:w0005", *(f"a1:w0005.{k}" for k in range(1, 5))]

    def test_whitespace_around_the_text_is_ignored(self) -> None:
        corr = {"a1:w0005": Correction("a1:w0005", "x", "  hola \t", "")}
        assert [w.text for w in apply([_word(5, "x")], corr)] == ["hola"]

    def test_expect_is_compared_after_strip(self) -> None:
        corr = {"a1:w0005": Correction("a1:w0005", "  Hola ", "Hey", "")}
        assert apply([_word(5, "Hola")], corr)[0].text == "Hey"

    def test_a_mismatch_is_check_failed_and_names_both_texts(self) -> None:
        corr = parse_corrections(DOC)
        with pytest.raises(CheckFailed) as info:
            apply([_word(31, "Higgsfield,")], corr)
        assert info.value.exit_code == 1
        message = info.value.message_es
        assert "la corrección apunta a otra palabra (¿cambió la transcripción?)" in message
        assert "a1:w0031" in message and "Hicksville," in message and "Higgsfield," in message

    def test_expect_is_exact_not_normalized(self) -> None:
        corr = {"a1:w0005": Correction("a1:w0005", "hola", "Hey", "")}
        with pytest.raises(CheckFailed):
            apply([_word(5, "Hola")], corr)

    def test_a_correction_for_another_clip_is_not_applied(self) -> None:
        corr = parse_corrections(DOC)
        words = [_word(31, "otra cosa", clip="a2")]
        assert apply(words, corr) == words


class TestUnmatched:
    def test_ids_of_a_known_clip_without_a_word_are_reported(self) -> None:
        corr = parse_corrections(DOC)
        words = [_word(31, "Hicksville,"), _word(301, "por")]
        assert unmatched(corr, words, {"a1"}) == ["a1:w0400"]

    def test_corrections_of_clips_that_were_not_loaded_are_not_judged(self) -> None:
        corr = parse_corrections(DOC)
        assert unmatched(corr, [], {"a2"}) == []

    def test_the_message_lists_the_ids(self) -> None:
        text = mismatch_message(["a1:w0400", "a1:w0500"])
        assert "a1:w0400, a1:w0500" in text and "¿cambió la transcripción?" in text


class TestOrphanListCapped:
    """001.12 point 7: 50 000 orphan corrections do not become a 50 000-name message."""

    def _orphans(self, count: int) -> dict[str, Correction]:
        ids = [f"a1:w{10_000 + i:05d}" for i in range(count)]
        return {i: Correction(i, "x", "y") for i in ids}

    def test_orphan_list_capped_names_the_first_20_and_counts_the_rest(self) -> None:
        orphans = unmatched(self._orphans(50_000), [_word(1, "x")], {"a1"})
        assert len(orphans) == 50_000
        message = mismatch_message(orphans)
        assert "a1:w10000" in message and "a1:w10019" in message and "a1:w10020" not in message
        assert message.endswith("(y 49980 más)") and len(message) < 2_000

    def test_orphan_list_capped_exactly_20_has_no_tail(self) -> None:
        message = mismatch_message([f"a1:w{i:04d}" for i in range(20)])
        assert "más)" not in message and "a1:w0019" in message

    def test_orphan_list_capped_21_says_one_more(self) -> None:
        assert mismatch_message([f"a1:w{i:04d}" for i in range(21)]).endswith("(y 1 más)")


class TestMessageOneLine:
    """001.12 point 8: the texts in a CheckFailed message are one line and at most 80 characters."""

    def _fail(self, expect: str, actual: str) -> str:
        corr = {"a1:w0005": Correction("a1:w0005", expect, "z")}
        with pytest.raises(CheckFailed) as info:
            apply([_word(5, actual)], corr)
        return info.value.message_es

    def test_message_one_line_breaks_become_spaces(self) -> None:
        message = self._fail("uno\ndos\r\ntres", "cua\rtro\ncinco")
        assert "\n" not in message and "\r" not in message
        assert '"uno dos  tres"' in message and '"cua tro cinco"' in message

    def test_message_one_line_long_texts_are_cut_to_80_characters(self) -> None:
        message = self._fail("e" * 500, "w" * 500)
        quoted = [part for part in message.split('"') if set(part) <= {"e", "w", "."} and part]
        assert len(quoted) == 2 and all(len(part) == 80 for part in quoted)
        assert len(message) < 300

    def test_message_one_line_short_texts_are_not_touched(self) -> None:
        assert '"Hicksville,"' in self._fail("Hicksville,", "Higgsfield,")

    def test_message_one_line_an_80_character_text_is_whole(self) -> None:
        assert f'"{"a" * 80}"' in self._fail("a" * 80, "otra")


class TestSplitTooShort:
    """001.12 point 12: a word cannot be split into more tokens than it has milliseconds."""

    def _split(self, ms: int, text: str) -> list[Word]:
        corr = {"a1:w0005": Correction("a1:w0005", "x", text)}
        return apply([_word(5, "x", 1000, 1000 + ms)], corr)

    def test_split_too_short_names_the_word_the_duration_and_the_count(self) -> None:
        with pytest.raises(CheckFailed) as info:
            self._split(2, "uno dos tres")
        assert info.value.exit_code == 1
        assert info.value.message_es == "la palabra a1:w0005 dura 2 ms y no se puede partir en 3"

    def test_split_too_short_one_ms_for_two_tokens(self) -> None:
        with pytest.raises(CheckFailed, match="dura 1 ms y no se puede partir en 2"):
            self._split(1, "uno dos")

    def test_split_too_short_as_many_ms_as_tokens_works_when_none_is_empty(self) -> None:
        done = self._split(3, "a b c")
        assert [w.e_ms - w.s_ms for w in done] == [1, 1, 1]

    def test_split_too_short_a_proportion_that_would_leave_a_token_empty_is_refused(self) -> None:
        with pytest.raises(CheckFailed, match="no se puede partir en 3"):
            self._split(3, "aaaaaaaaaa b c")  # 10 : 1 : 1 over 3 ms gives 2, 0 and 1

    def test_split_too_short_a_single_token_or_a_deletion_never_fails(self) -> None:
        assert [w.text for w in self._split(1, "uno")] == ["uno"]
        assert [w.text for w in self._split(1, "")] == [""]
