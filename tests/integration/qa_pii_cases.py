"""`kcut qa` and the phone that was said (spec S1.9a row 6; 001.15 T2).

The kept words of a1 have a phone number (`plant_words`) and the ear is a double that hears the same
words with one digit changed (3211 -> 3011). Masked, both are `**11`: the diff has to show that and
nothing else, and `match` has to see two different words. Collected from `test_qa_synth.py`,
which is at the 300-line limit; the module that imports it has to bring `built`.
"""

import json
import shutil
from pathlib import Path

import pytest

from kcut import cli
from kcut.pack.pii import mask_pii
from kcut.qa.transcript_diff import HIDDEN_HEARD
from kcut.transcribe.model import Word
from tests.integration.graphics_helpers import plant_words
from tests.integration.qa_helpers import VIDEO, check_of, copy_of
from tests.integration.view_frames_helpers import Run, project_args
from tests.unit.qa_fakes import NoModel, install_ear

__all__ = [
    "pii",
    "pii_project",
    "test_qa_pii_a_sentence_the_ear_gets_wrong_fails_with_the_diff_and_exit_1",
    "test_qa_pii_heard_masked_far_a_number_far_from_a_masked_word_is_masked_in_the_json",
    "test_qa_pii_heard_masked_far_the_console_shows_the_masked_number_too",
    "test_qa_pii_the_diffs_are_masked_and_the_match_is_of_the_raw_text",
    "test_qa_pii_what_is_printed_is_masked_too",
    "test_qa_pii_with_masking_off_the_texts_are_raw_and_the_report_warns",
    "test_qa_pii_without_the_model_the_transcript_is_skipped_and_the_verdict_incomplete",
]
RAW_DIGITS = ("3211", "3011", "972", "808")
SPEECH = [  # what the double of the ear "hears": the same words, with one digit changed
    ("Llama", 4500, 4800),
    ("972", 4900, 5200),
    ("808", 5300, 5600),
    ("3011", 5700, 6100),
    ("ya", 6300, 6600),
    ("Higgsfield", 6700, 7200),
    ("gracias", 7300, 7800),
]


@pytest.fixture(scope="module")
def pii_project(built: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = copy_of(built, tmp_path_factory.mktemp("qapii"))
    plant_words(root)  # what a1 says: a phone number in digits
    return root


@pytest.fixture
def pii(pii_project: Path) -> Path:
    """The project with an empty cache of the ear: the key of the cache is the audio and the
    parameters, not what the double says, so each test starts without what the last one made."""
    shutil.rmtree(pii_project / ".kcut" / "qa_ear", ignore_errors=True)
    return pii_project


def _mask_pii_off(root: Path) -> None:
    path = root / "kcut.toml"
    text = path.read_text(encoding="utf-8")
    assert "mask_pii = true" in text
    path.write_text(text.replace("mask_pii = true", "mask_pii = false"), encoding="utf-8")


def test_qa_pii_the_diffs_are_masked_and_the_match_is_of_the_raw_text(
    pii: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_ear(monkeypatch, SPEECH)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(pii))
    assert code == 0, (doc, err)
    check = check_of(doc, "transcript")
    assert check["status"] == "pass" and check["language"] == "es"
    # 3211 and 3011 are both `**11` once masked, but they are two different words: 6 of 7
    assert check["match"] == round(6 / 7, 4)
    assert check["expected_words"] == check["heard_words"] == 7
    assert len(check["diffs"]) == 1
    diff = check["diffs"][0]
    # 001.43: the heard side of a stretch with a masked expected word is not shown: `[tapado]`
    assert (diff["op"], diff["expected"], diff["heard"]) == ("replace", "**11", HIDDEN_HEARD)
    # 3211 starts at 5.7 s of a1 = frame 171; the clip puts the frame 60 of a1 at the frame 30
    assert diff["at_f"] == 141 and diff["at_display"] == "00:04.7"
    on_disk = (pii / "qa" / "v1" / "report.json").read_text(encoding="utf-8")
    for text in (json.dumps(doc), on_disk):
        assert not any(digits in text for digits in RAW_DIGITS), text


SPEECH_FAR = [  # the same words as expected, and then a number that the cut does not keep
    ("Llama", 4500, 4800),
    ("972", 4900, 5200),
    ("808", 5300, 5600),
    ("3211", 5700, 6100),
    ("ya", 6300, 6600),
    ("Higgsfield", 6700, 7200),
    ("gracias", 7300, 7800),
    ("8095551234", 7900, 8300),
]
FAR_NUMBER = "8095551234"


def _far_forms() -> tuple[str, str]:
    """`(what mask_pii shows of FAR_NUMBER, the digits of it that the mask covers)`, from `mask_pii`
    over the heard words, as `run` does (001.46, row 38): nothing is written by hand."""
    words = [Word(f"qa:w{i:04d}", i, t, s, e, 0.9) for i, (t, s, e) in enumerate(SPEECH_FAR)]
    shown = [w.text for w in mask_pii(words)[0]][-1]
    covered = "".join(raw for raw, seen in zip(FAR_NUMBER, shown, strict=True) if seen == "*")
    assert shown != FAR_NUMBER and len(covered) >= 4, shown
    return shown, covered


def test_qa_pii_heard_masked_far_a_number_far_from_a_masked_word_is_masked_in_the_json(
    pii: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    shown, covered = _far_forms()
    install_ear(monkeypatch, SPEECH_FAR)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(pii))
    assert code == 0, (doc, err)
    diffs = check_of(doc, "transcript")["diffs"]
    assert [(d["op"], d["expected"], d["heard"]) for d in diffs] == [("insert", "", shown)]
    on_disk = (pii / "qa" / "v1" / "report.json").read_text(encoding="utf-8")
    for text in (json.dumps(doc), on_disk):
        assert shown in text and FAR_NUMBER not in text and covered not in text, text


def test_qa_pii_heard_masked_far_the_console_shows_the_masked_number_too(
    pii: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shown, covered = _far_forms()
    install_ear(monkeypatch, SPEECH_FAR)
    capsys.readouterr()
    assert cli.main(["qa", VIDEO, *project_args(pii)]) == 0
    shown_out = capsys.readouterr()
    text = shown_out.out + shown_out.err
    assert f"oído '{shown}'" in text and FAR_NUMBER not in text and covered not in text, text


def test_qa_pii_what_is_printed_is_masked_too(
    pii: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_ear(monkeypatch, SPEECH)
    capsys.readouterr()
    assert cli.main(["qa", VIDEO, *project_args(pii)]) == 0
    shown = capsys.readouterr()
    text = shown.out + shown.err
    assert "**11" in text and not any(digits in text for digits in RAW_DIGITS), text


def test_qa_pii_with_masking_off_the_texts_are_raw_and_the_report_warns(
    built: Path, tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = copy_of(built, tmp_path)
    plant_words(root)
    _mask_pii_off(root)
    install_ear(monkeypatch, SPEECH)
    code, doc, err = kcut_json("qa", VIDEO, *project_args(root))
    assert code == 0, (doc, err)
    diff = check_of(doc, "transcript")["diffs"][0]
    assert (diff["expected"], diff["heard"]) == ("3211", "3011")
    assert [w["code"] for w in doc["warnings"]] == ["pii_unmasked"]
    assert "pii_unmasked" in err  # and on the console, as every command says it


def test_qa_pii_a_sentence_the_ear_gets_wrong_fails_with_the_diff_and_exit_1(
    pii: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_ear(monkeypatch, [("otra", 4500, 4800), ("cosa", 4900, 5200)])
    code, doc, _ = kcut_json("qa", VIDEO, *project_args(pii))
    check = check_of(doc, "transcript")
    assert code == 1 and doc["verdict"] == "fail" and check["status"] == "fail", doc
    assert check["match"] < 0.8 and check["diffs"]


def test_qa_pii_without_the_model_the_transcript_is_skipped_and_the_verdict_incomplete(
    pii: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kcut.qa import ear

    monkeypatch.setattr(ear, "Engine", NoModel)
    code, doc, _ = kcut_json("qa", VIDEO, *project_args(pii))
    check = check_of(doc, "transcript")
    assert code == 0 and check["status"] == "skipped" and "Whisper" in check["reason_es"]
    assert doc["verdict"] == "incomplete"
