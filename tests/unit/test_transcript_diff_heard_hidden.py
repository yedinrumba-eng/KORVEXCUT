"""`heard` of a stretch that touches a masked expected word is `[tapado]` (spec S1.9a row 34;
001.43, point 3; T2/D19).

The expected side is masked with the context of the whole clip; the heard side only with what is
left in the render, and `mask_pii` asks for 7 digits in a row. A cut that splits a phone, heard as
`809555`, would come out raw. So if any expected word of the stretch, or the expected word right
before or right after it, is masked, the heard text of that stretch is not shown.
"""

import json
from collections.abc import Sequence

from kcut.edl.words import KeptWord
from kcut.pack.pii import mask_pii
from kcut.qa.report import QaReport
from kcut.qa.transcript_diff import (
    HIDDEN_HEARD,
    DiffItem,
    TranscriptDiff,
    diff_transcript,
    transcript_check,
)
from kcut.transcribe.model import Word

FPS = 30


def _kept(texts: Sequence[str]) -> list[KeptWord]:
    return [
        KeptWord(f"a1:w{i:04d}", text, 0, 100 + i * 6, 104 + i * 6, "a1", 0, 0)
        for i, text in enumerate(texts)
    ]


def _heard(texts: Sequence[str]) -> list[Word]:
    return [
        Word(f"qa:w{i:04d}", i, text, i * 200, i * 200 + 150, 0.9) for i, text in enumerate(texts)
    ]


def _run(
    expected: Sequence[str], heard: Sequence[str], hidden: Sequence[str] = ("809", "555")
) -> TranscriptDiff:
    """`hidden` are the expected texts that `shown` has as `***`."""
    kept, ear = _kept(expected), _heard(heard)
    shown = {w.id: ("***" if w.text in hidden else w.text) for w in kept}
    return diff_transcript(kept, shown, ear, [w.text for w in ear])


def _report(diff: TranscriptDiff) -> QaReport:
    check = transcript_check(diff, 0.8, "es", FPS)
    return QaReport(
        "salida/v1.mp4", "edit/edl-v1.json", "2026-11-23T12:00:00", (check,),
        1.0, "00:11.5", None, {"probe": 1.0}, (),
    )  # fmt: skip


def test_heard_hidden_a_phone_split_by_the_cut_is_not_shown() -> None:
    diff = _run(["llamame", "al", "809", "555"], ["llamame", "al", "809555"])
    assert diff.items == (DiffItem("replace", "*** ***", HIDDEN_HEARD, 112),)
    assert HIDDEN_HEARD == "[tapado]"
    check = json.dumps(transcript_check(diff, 0.8, "es", FPS).data, ensure_ascii=False)
    report = json.dumps(_report(diff).to_json(), ensure_ascii=False)
    for text in (check, report):
        assert "809555" not in text and "555" not in text and "[tapado]" in text


def test_heard_hidden_an_insert_right_after_a_masked_word_is_hidden() -> None:
    diff = _run(["llamame", "809", "555", "gracias"], ["llamame", "809", "555", "5", "gracias"])
    assert [(i.op, i.heard) for i in diff.items] == [("insert", HIDDEN_HEARD)]
    assert "5" not in {i.heard for i in diff.items}


def test_heard_hidden_an_insert_right_before_a_masked_word_is_hidden() -> None:
    diff = _run(["hola", "809", "555"], ["hola", "8", "809", "555"])
    assert [(i.op, i.heard) for i in diff.items] == [("insert", HIDDEN_HEARD)]


def test_heard_hidden_a_replace_next_to_a_masked_word_is_hidden() -> None:
    diff = _run(["hola", "amigo", "809", "555"], ["hola", "amiga", "809", "555"])
    assert [(i.op, i.expected, i.heard) for i in diff.items] == [
        ("replace", "amigo", HIDDEN_HEARD)
    ]  # "amigo" is right before the masked "809"


def test_heard_hidden_a_stretch_far_from_every_masked_word_keeps_its_heard_text() -> None:
    diff = _run(
        ["hola", "que", "tal", "amigo", "mio", "llamame", "809", "555"],
        ["hola", "que", "tel", "amigo", "mio", "llamame", "809", "555"],
    )
    assert diff.items == (DiffItem("replace", "tal", "tel", 112),)


def test_heard_hidden_with_the_mask_off_the_heard_text_is_raw_as_before() -> None:
    diff = _run(["llamame", "al", "809", "555"], ["llamame", "al", "809555"], hidden=())
    assert diff.items == (DiffItem("replace", "809 555", "809555", 112),)


def test_heard_masked_far_a_number_heard_far_from_a_masked_word_is_shown_masked() -> None:
    """Row 38 (001.46): where row 34 does not hide the stretch, `heard` is the text of the masked
    list (`mask_pii` over the heard words), never the raw one."""
    kept = _kept(["hola", "que", "tal", "amigo", "mio"])
    shown = {w.id: w.text for w in kept}  # nothing expected is masked
    ear = _heard(["hola", "que", "8095551234", "amigo", "mio"])
    heard_shown = [w.text for w in mask_pii(ear)[0]]
    assert heard_shown[2] != "8095551234" and "8095551234" not in heard_shown[2]
    diff = diff_transcript(kept, shown, ear, heard_shown)
    assert diff.items == (DiffItem("replace", "tal", heard_shown[2], 112),)
    assert diff.items[0].heard != HIDDEN_HEARD
    check = json.dumps(transcript_check(diff, 0.8, "es", FPS).data, ensure_ascii=False)
    report = json.dumps(_report(diff).to_json(), ensure_ascii=False)
    for text in (check, report):
        assert "8095551234" not in text and heard_shown[2] in text


def test_heard_hidden_a_delete_has_no_heard_text_to_hide() -> None:
    diff = _run(["hola", "809", "555", "adios"], ["hola", "adios"])
    assert [(i.op, i.heard) for i in diff.items] == [("delete", "")]
