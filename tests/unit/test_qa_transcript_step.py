"""The `transcript` step of `kcut qa` (spec S1.9a): when it is skipped and why, which language the
ear listens in, and what it asks the diff to show. The words the cut keeps, the ear and the cached
transcripts are replaced; the audit is in `test_qa_*.py` and `tests/integration/test_qa_synth.py`.
"""

from pathlib import Path
from typing import Any

import pytest

from kcut.audio.loudnorm import EburMeasure
from kcut.edl.kept import KeptWords
from kcut.edl.words import KeptWord
from kcut.ingest.inventory import Notice
from kcut.qa import run as qa_run
from kcut.qa.ear import Heard
from kcut.transcribe.model import Transcript, Word
from tests.unit.edl_fakes import edit, inventory, parsed
from tests.unit.gfx_resolve_fakes import make_project, with_privacy

LOUD = EburMeasure(-14.0, -2.0, 3.0)
KEPT = [KeptWord(f"a1:w{i:04d}", t, 1, 30 + 6 * i, 34 + 6 * i, "a1", 0, 0) for i, t in enumerate(
    ["Llama", "972", "808", "3211", "ya"]
)]  # fmt: skip


def _kept(words: list[KeptWord] | None = None) -> KeptWords:
    found = KEPT if words is None else words
    return KeptWords(words=found, shown={w.id: w.text for w in found}, missing=(), masked=True)


def _heard(*texts: str) -> Heard:
    return Heard([Word(f"qa:w{i:04d}", i, t, 0, 0, 0.9) for i, t in enumerate(texts)], "es")


class Seen:
    """What the step asked of the ear."""

    def __init__(self) -> None:
        self.calls: list[str] = []


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    kept: KeptWords | None = None,
    heard: Heard | None = None,
    languages: dict[str, str] | None = None,
) -> Seen:
    seen = Seen()
    monkeypatch.setattr(qa_run, "kept_words", lambda *a, **k: kept or _kept())

    def hear(_project: Any, _video: Path, language: str, **_k: Any) -> Heard | None:
        seen.calls.append(language)
        return heard

    monkeypatch.setattr(qa_run, "hear", hear)
    spoken = {"a1": "es"} if languages is None else languages
    monkeypatch.setattr(qa_run.cache, "read_index", lambda *a, **k: dict.fromkeys(spoken, "k"))

    def load(_project: Any, clip_id: str, *_a: Any, **_k: Any) -> Transcript | None:
        if clip_id not in spoken:
            return None
        return Transcript(clip_id, "k", spoken[clip_id], 0.9, 1000, [], [], {}, 1.0)

    monkeypatch.setattr(qa_run.cache, "load_transcript", load)
    return seen


def _step(
    tmp_path: Path, measure: EburMeasure | None = LOUD, mask: bool = True, doc: Any = None
) -> Any:
    project = with_privacy(make_project(tmp_path), mask)
    return qa_run._transcript(
        project, inventory(), parsed(doc), tmp_path / "v1.mp4", measure, [], None
    )


def test_qa_transcript_step_with_words_and_a_loud_render_it_listens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _wire(monkeypatch, heard=_heard("Llama", "972", "808", "3211", "ya"))
    check = _step(tmp_path)
    assert check.status == "pass" and check.data["match"] == 1.0
    assert seen.calls == ["es"]


def test_qa_transcript_step_no_kept_words_is_skipped_and_nobody_listens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _wire(monkeypatch, kept=_kept([]))
    check = _step(tmp_path)
    assert check.status == "skipped" and check.reason_es == qa_run.NO_WORDS_ES
    assert seen.calls == []


def test_qa_transcript_step_a_cut_with_no_transcript_of_its_sources_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Words kept but no cached transcript to take the language from: there is nothing to say."""
    seen = _wire(monkeypatch, languages={})
    check = _step(tmp_path)
    assert check.status == "skipped" and check.reason_es == qa_run.NO_WORDS_ES
    assert seen.calls == []


@pytest.mark.parametrize("silent", [None, -50.1, -60.0, -70.0])
def test_qa_transcript_step_a_silent_render_is_skipped_and_nobody_listens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, silent: float | None
) -> None:
    seen = _wire(monkeypatch, heard=_heard("x"))
    check = _step(tmp_path, EburMeasure(silent, None, None))
    assert check.status == "skipped" and check.reason_es == qa_run.SILENT_ES
    assert seen.calls == []


@pytest.mark.parametrize("loud", [-50.0, -49.9, -30.0])
def test_qa_transcript_step_at_minus_50_and_above_it_does_listen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, loud: float
) -> None:
    seen = _wire(monkeypatch, heard=_heard("x"))
    assert _step(tmp_path, EburMeasure(loud, None, None)).status == "fail"
    assert seen.calls == ["es"]


def test_qa_transcript_step_a_video_without_audio_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _wire(monkeypatch, heard=_heard("x"))
    check = _step(tmp_path, None)
    assert check.status == "skipped" and check.reason_es == qa_run.NO_AUDIO_ES and not seen.calls


def test_qa_transcript_step_without_the_model_is_skipped_with_the_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wire(monkeypatch, heard=None)
    check = _step(tmp_path)
    assert check.status == "skipped" and check.reason_es == qa_run.NO_MODEL_ES
    assert "Whisper" in qa_run.NO_MODEL_ES and "--allow-download" in qa_run.NO_MODEL_ES


def test_qa_transcript_step_the_language_is_the_most_frequent_among_the_voice_clips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The example has two voice clips of a1; a third of a2 in English does not change that."""
    project = make_project(tmp_path)
    doc = edit(lambda d: d["clips"].insert(1, {**d["clips"][1], "src": "a2", "at_f": 30}))
    _wire(monkeypatch, languages={"a1": "es", "a2": "en"})
    assert qa_run._language(project, parsed(doc)) == "es"


def test_qa_transcript_step_a_tie_in_the_language_goes_to_the_first_in_the_alphabet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path)
    doc = edit(lambda d: d["clips"][3].update(src="a2"))  # one voice clip of a1, one of a2
    _wire(monkeypatch, languages={"a1": "es", "a2": "en"})
    assert qa_run._language(project, parsed(doc)) == "en"


def test_qa_transcript_step_a_source_with_no_transcript_does_not_vote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path)
    doc = edit(lambda d: d["clips"][3].update(src="a2"))
    _wire(monkeypatch, languages={"a2": "en"})  # a1 has none: only a2 speaks
    assert qa_run._language(project, parsed(doc)) == "en"


def test_qa_transcript_step_the_heard_text_is_masked_as_a_whole_list_unless_it_is_off(
    tmp_path: Path,
) -> None:
    words = [Word(f"qa:w{i}", i, t, 0, 0, 0.9) for i, t in enumerate(["972", "808", "3211", "ya"])]
    masked = qa_run._heard_shown(with_privacy(make_project(tmp_path), True), words)
    assert masked == ["***", "***", "**11", "ya"]
    raw = qa_run._heard_shown(with_privacy(make_project(tmp_path / "otro"), False), words)
    assert raw == ["972", "808", "3211", "ya"]


def test_qa_transcript_step_the_warnings_have_no_repeats() -> None:
    notices = [
        Notice("cache_rebuilt", "a"),
        Notice("pii_unmasked", "b"),
        Notice("cache_rebuilt", "a"),
    ]
    assert qa_run._warnings(notices) == (
        {"code": "cache_rebuilt", "message_es": "a"},
        {"code": "pii_unmasked", "message_es": "b"},
    )
