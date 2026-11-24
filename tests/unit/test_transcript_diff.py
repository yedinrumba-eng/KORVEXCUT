"""`diff_transcript` and the `transcript` check (spec S1.9a, rows 2 and 6; 001.15 T2).

What the cut keeps (`KeptWord`, raw text, ALL of them: also those a graphic covers, because the
check listens to the audio) is compared with what Whisper heard in the render. The comparison is
on raw text with `norm_token`, empty tokens out, and `difflib.SequenceMatcher(autojunk=False)`;
the texts of `diffs[]` come from the masked lists (`shown`, `heard_shown`), so a phone number that
was said never reaches the report, and `match` is the ratio of the raw comparison.
"""

import json
from collections.abc import Sequence
from difflib import SequenceMatcher

from kcut.edl.words import KeptWord
from kcut.pack.pii import mask_pii
from kcut.qa.transcript_diff import (
    HIDDEN_HEARD,
    DiffItem,
    TranscriptDiff,
    diff_transcript,
    transcript_check,
)
from kcut.transcribe.model import Word

FPS = 30


def _kept(texts: Sequence[str], first_f: int = 100, step: int = 6) -> list[KeptWord]:
    """Kept words one after the other, `step` frames apart, from output frame `first_f`."""
    return [
        KeptWord(f"a1:w{i:04d}", text, 0, first_f + i * step, first_f + i * step + 4, "a1", 0, 0)
        for i, text in enumerate(texts)
    ]


def _heard(texts: Sequence[str]) -> list[Word]:
    return [
        Word(f"qa:w{i:04d}", i, text, i * 200, i * 200 + 150, 0.9) for i, text in enumerate(texts)
    ]


def _same(words: Sequence[KeptWord]) -> dict[str, str]:
    """`shown` when nothing is masked: the text of each word."""
    return {w.id: w.text for w in words}


def _diff(expected: Sequence[str], heard: Sequence[str]) -> TranscriptDiff:
    kept, ear = _kept(expected), _heard(heard)
    return diff_transcript(kept, _same(kept), ear, [w.text for w in ear])


def test_transcript_diff_the_same_words_are_a_match_of_one_and_no_diffs() -> None:
    result = _diff(["hola", "esto", "es", "una", "prueba"], ["hola", "esto", "es", "una", "prueba"])
    assert result.ratio == 1.0 and result.items == ()
    assert (result.expected_words, result.heard_words) == (5, 5)


def test_transcript_diff_a_word_that_is_heard_instead_of_another_is_a_replace() -> None:
    result = _diff(["hola", "esto", "es", "aqui"], ["hola", "esto", "es", "y"])
    assert result.items == (DiffItem("replace", "aqui", "y", 118),)
    assert result.ratio == 0.75


def test_transcript_diff_the_position_is_the_output_frame_of_the_first_expected_word() -> None:
    result = _diff(["uno", "dos", "tres", "cuatro"], ["uno", "dos", "cinco", "cuatro"])
    assert result.items == (DiffItem("replace", "tres", "cinco", 112),)  # 100 + 2 * 6


def test_transcript_diff_a_word_that_is_not_heard_is_a_delete_at_its_frame() -> None:
    result = _diff(["uno", "dos", "tres", "cuatro"], ["uno", "tres", "cuatro"])
    assert result.items == (DiffItem("delete", "dos", "", 106),)
    assert (result.expected_words, result.heard_words) == (4, 3)


def test_transcript_diff_a_word_that_is_heard_and_not_expected_is_an_insert_after_the_last() -> (
    None
):
    result = _diff(["uno", "dos", "tres"], ["uno", "dos", "eh", "tres"])
    # no expected word is there: it is placed where the last expected word before it ends
    assert result.items == (DiffItem("insert", "", "eh", 110),)  # "dos" ends at 106 + 4


def test_transcript_diff_an_insert_before_everything_is_at_the_first_frame_of_the_cut() -> None:
    result = _diff(["uno", "dos"], ["eh", "uno", "dos"])
    assert result.items == (DiffItem("insert", "", "eh", 0),)


def test_transcript_diff_several_words_in_one_stretch_are_joined_with_a_space() -> None:
    result = _diff(["a", "b", "c", "d", "e"], ["a", "x", "y", "z", "e"])
    assert result.items == (DiffItem("replace", "b c d", "x y z", 106),)


def test_transcript_diff_everything_expected_is_compared_also_what_a_graphic_covers() -> None:
    """A word under a title is still said: heard, it is no difference; not heard, it is one."""
    words = ["mira", "este", "titulo", "grande", "ahora"]
    covered = {"titulo", "grande"}  # nothing in the comparison knows or cares which ones
    assert covered <= set(words)
    assert _diff(words, words).items == ()
    missing = _diff(words, [w for w in words if w not in covered])
    assert missing.items == (DiffItem("delete", "titulo grande", "", 112),)


def test_transcript_diff_norm_token_on_both_sides_accents_case_and_punctuation_do_not_count() -> (
    None
):
    result = _diff(["¿Qué", "tal?", "Ñandú,"], ["que", "TAL", "nandu"])
    assert result.items == () and result.ratio == 1.0


def test_transcript_diff_words_that_are_only_punctuation_are_not_tokens_on_either_side() -> None:
    result = _diff(["hola", "...", "mundo", "—"], ["hola", "mundo", "?"])
    assert result.items == () and (result.expected_words, result.heard_words) == (2, 2)


def test_transcript_diff_a_pause_marker_between_two_words_does_not_move_the_positions() -> None:
    result = _diff(["uno", "...", "dos", "tres"], ["uno", "dos", "cuatro"])
    assert result.items == (DiffItem("replace", "tres", "cuatro", 118),)  # "tres" is word 3


def test_transcript_diff_autojunk_is_off_so_a_word_said_many_times_still_matches() -> None:
    """With `autojunk` on, a token that is more than 1 % of 200 or more would be ignored and this
    would be close to 0; off, the 300 `a` match."""
    result = _diff(["a"] * 300 + ["b"], ["a"] * 300 + ["c"])
    assert result.ratio > 0.99
    assert len(result.items) == 1 and result.items[0].op == "replace"


def test_transcript_diff_nothing_heard_is_a_ratio_of_zero_and_one_delete() -> None:
    result = _diff(["uno", "dos"], [])
    assert result.ratio == 0.0 and result.items == (DiffItem("delete", "uno dos", "", 100),)


def test_transcript_diff_the_ratio_is_the_one_of_sequence_matcher() -> None:
    a, b = ["a", "b", "c", "d", "e", "f", "g"], ["a", "b", "x", "d", "e", "y", "g"]
    assert _diff(a, b).ratio == SequenceMatcher(None, a, b, autojunk=False).ratio()


# --- T2: the phone that was said (row 6) ---------------------------------------------------------


PHONE = ["Llama", "972", "808", "3211", "ya", "Higgsfield", "gracias"]


def _masked(texts: Sequence[str]) -> tuple[list[KeptWord], dict[str, str]]:
    """Kept words and what Claude reads of them, as `kept_words` makes it: `mask_pii` on the whole
    list."""
    kept = _kept(texts)
    words = [Word(w.id, i, w.text, 0, 0, 0.9) for i, w in enumerate(kept)]
    return kept, {w.id: w.text for w in mask_pii(words)[0]}


def _masked_heard(texts: Sequence[str]) -> tuple[list[Word], list[str]]:
    ear = _heard(texts)
    return ear, [w.text for w in mask_pii(ear)[0]]


def test_transcript_diff_pii_the_masked_texts_are_in_the_diffs_and_the_raw_ones_are_not() -> None:
    kept, shown = _masked(PHONE)
    assert shown[kept[3].id] == "**11"  # the masking of the lists is what the test relies on
    ear, ear_shown = _masked_heard(["Llama", "972", "808", "3211", "y", "Higgsfield", "gracias"])
    result = diff_transcript(kept, shown, ear, ear_shown)
    # 001.43: "ya" comes right after the masked "3211", so what was heard there is not shown
    assert result.items == (DiffItem("replace", "ya", HIDDEN_HEARD, 124),)
    # a difference inside the number: only the masked form is shown
    ear, ear_shown = _masked_heard(["Llama", "972", "808", "3011", "ya", "Higgsfield", "gracias"])
    result = diff_transcript(kept, shown, ear, ear_shown)
    assert result.items == (DiffItem("replace", "**11", HIDDEN_HEARD, 118),)  # 001.43


def test_transcript_diff_pii_match_is_of_the_raw_text_not_of_the_masked_one() -> None:
    """3211 and 3011 look the same once masked (`**11`): the ratio still sees two numbers."""
    kept, shown = _masked(PHONE)
    ear, ear_shown = _masked_heard(["Llama", "972", "808", "3011", "ya", "Higgsfield", "gracias"])
    result = diff_transcript(kept, shown, ear, ear_shown)
    assert result.ratio == 6 / 7
    same = diff_transcript(kept, shown, *_masked_heard(PHONE))
    assert same.ratio == 1.0 and same.items == ()


def test_transcript_diff_pii_a_word_swallowed_by_an_address_adds_no_text() -> None:
    """An address said in words is one masked word and the rest are `""`: they are not in the
    join (no double spaces) and they are still words of the comparison."""
    kept = _kept(["mi", "correo", "es", "juan", "arroba", "gmail", "punto", "com", "gracias"])
    shown = {w.id: w.text for w in kept}
    for word in kept[3:8]:
        shown[word.id] = ""
    shown[kept[3].id] = "j***@***.com"
    ear = _heard(["mi", "correo", "es", "gracias"])
    result = diff_transcript(kept, shown, ear, [w.text for w in ear])
    assert result.items == (DiffItem("delete", "j***@***.com", "", 118),)


def test_transcript_diff_pii_the_check_has_no_raw_digit_of_the_number() -> None:
    kept, shown = _masked(PHONE)
    ear, ear_shown = _masked_heard(["Llama", "972", "808", "3011", "ya", "Higgsfield", "gracias"])
    check = transcript_check(diff_transcript(kept, shown, ear, ear_shown), 0.8, "es", FPS)
    text = json.dumps(check.to_json())
    assert "3211" not in text and "3011" not in text and "972" not in text and "808" not in text


# --- the check -----------------------------------------------------------------------------------


def test_transcript_diff_check_the_example_of_the_spec() -> None:
    expected = ["uno", "dos", "tres", "cuatro", "cinco"]
    kept = _kept(expected, first_f=1020, step=6)
    ear = _heard(["uno", "dos", "y", "cuatro", "cinco"])
    diff = diff_transcript(kept, _same(kept), ear, [w.text for w in ear])
    check = transcript_check(diff, 0.5, "es", FPS)
    assert check.to_json() == {
        "id": "transcript",
        "status": "pass",
        "match": 0.8,
        "min": 0.5,
        "language": "es",
        "expected_words": 5,
        "heard_words": 5,
        "diffs": [
            {
                "op": "replace",
                "expected": "tres",
                "heard": "y",
                "at_f": 1032,
                "at_display": "00:34.4",
            }
        ],
    }


def test_transcript_diff_check_at_display_is_minutes_seconds_and_tenths() -> None:
    kept = _kept(["uno"], first_f=1020)
    check = transcript_check(diff_transcript(kept, _same(kept), [], []), 0.8, "es", FPS)
    diffs = check.data["diffs"]
    assert (
        isinstance(diffs, list) and diffs[0]["at_f"] == 1020 and diffs[0]["at_display"] == "00:34.0"
    )


def test_transcript_diff_check_the_limit_is_closed_at_min_transcript_match() -> None:
    kept = _kept(["a", "b", "c", "d", "e"])
    ear = _heard(["a", "b", "c", "d", "x"])
    diff = diff_transcript(kept, _same(kept), ear, [w.text for w in ear])  # ratio 0.8
    assert transcript_check(diff, 0.8, "es", FPS).status == "pass"
    assert transcript_check(diff, 0.81, "es", FPS).status == "fail"


def test_transcript_diff_check_reports_the_ratio_with_four_decimals() -> None:
    kept = _kept(["a", "b", "c"])
    ear = _heard(["a", "b", "c", "d"])
    diff = diff_transcript(kept, _same(kept), ear, [w.text for w in ear])  # 6 / 7
    assert transcript_check(diff, 0.8, "es", FPS).data["match"] == 0.8571


def test_transcript_diff_check_the_language_is_the_one_it_was_heard_in() -> None:
    kept = _kept(["hello"])
    ear = _heard(["hello"])
    check = transcript_check(diff_transcript(kept, _same(kept), ear, ["hello"]), 0.8, "en", FPS)
    assert check.data["language"] == "en" and check.status == "pass" and check.data["diffs"] == []
