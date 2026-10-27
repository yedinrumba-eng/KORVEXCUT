"""The words the cut keeps, raw for the MP4 and masked for Claude (spec S1.5a, 001.15 T1 and T2).

The project is written by hand (no ffmpeg, no model): a fake engine says the words, the wav16 files
are synthetic. A phone number said in words is the PII.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from kcut import cli
from kcut.edl.kept import KeptWords, kept_words
from kcut.edl.model import Edl
from kcut.edl.words import KeptWord
from kcut.ingest.inventory import Notice
from kcut.project import Project, load_inventory, open_project
from tests.unit.edl_fakes import Doc, edit, parsed
from tests.unit.test_pack_command import LAYOUT
from tests.unit.transcribe_fakes import FakeClip, Spoken, build_project, install_fake_engine

PHONE = ["nueve", "siete", "dos", "ocho", "cero", "ocho", "tres"]
SAID: list[Spoken] = [
    ("Hicksville,", 1000, 1400, 0.9),  # corrected to "Higgsfield," below
    *[(w, 1500 + 300 * k, 1700 + 300 * k, 0.9) for k, w in enumerate(PHONE)],  # 1.5 s - 3.5 s
    ("gracias", 3800, 4200, 0.9),
]
UNMASKED = Notice("pii_unmasked", "PII sin enmascarar (privacy.mask_pii = false)")


def _edl(*voices: tuple[str, int, int, int]) -> Edl:
    """An EDL whose clips are voices `(src, at_f, in_f, out_f)`; the rest does not matter."""

    def change(doc: Doc) -> None:
        doc["clips"] = [
            {"kind": "voice", "src": s, "at_f": at, "in_f": a, "out_f": b, "why": "x"}
            for s, at, a, b in voices
        ]

    return parsed(edit(change))


def _project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toml: str = "", only: str | None = None
) -> Project:
    clips = [FakeClip("a1", LAYOUT)]
    if only is not None:
        clips.append(FakeClip("a2", LAYOUT * np.float32(0.9), slug="cam2"))
    root = build_project(tmp_path / "proyecto ñandú", clips, toml=toml).root
    install_fake_engine(monkeypatch, {"a1": SAID})
    assert cli.main(["transcribe", *([only] if only else []), "--project", str(root)]) == 0
    item = {"word": "a1:w0000", "expect": "Hicksville,", "text": "Higgsfield,", "why": "x"}
    document = {"schema": "kcut.correcciones/1", "items": [item]}
    (root / "edit").mkdir(exist_ok=True)
    (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")
    return open_project(str(root))


def _kept(project: Project, edl: Edl) -> tuple[KeptWords, list[Notice]]:
    notices: list[Notice] = []
    return kept_words(project, edl, load_inventory(project), notices=notices, log=None), notices


ONE = _edl(("a1", 0, 0, 150))  # the first 5 s of a1


class TestMasking:
    def test_edl_kept_words_are_raw_and_shown_is_masked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kept, notices = _kept(_project(tmp_path, monkeypatch), ONE)
        assert [w.text for w in kept.words] == ["Higgsfield,", *PHONE, "gracias"]
        shown = [kept.shown[w.id] for w in kept.words]
        assert shown == ["Higgsfield,", "*", "*", "*", "*", "*", "8", "3", "gracias"]
        assert kept.masked is True and kept.missing == () and notices == []

    def test_edl_kept_the_correction_is_applied_before_the_words_are_mapped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kept, _ = _kept(_project(tmp_path, monkeypatch), ONE)
        assert kept.words[0].text == "Higgsfield," and kept.words[0].id == "a1:w0000"

    def test_edl_kept_shown_has_one_entry_per_kept_word_and_nothing_else(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        edl = _edl(("a1", 0, 0, 60))  # only 2 s: "Higgsfield," and the first digits
        kept, _ = _kept(_project(tmp_path, monkeypatch), edl)
        assert set(kept.shown) == {w.id for w in kept.words}
        assert len(kept.words) < len(SAID)

    def test_edl_kept_the_number_is_masked_over_the_whole_clip_not_over_the_kept_part(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # the cut keeps from 2.7 s: only the last 3 digits of the number, which alone would be
        # 3 digits and not PII, but the number was masked with the whole list of the clip
        kept, _ = _kept(_project(tmp_path, monkeypatch), _edl(("a1", 0, 81, 150)))
        shown = [kept.shown[w.id] for w in kept.words]
        assert shown[:-1] == ["*", "8", "3"] and shown[-1] == "gracias"
        assert not {"ocho", "cero", "tres", "dos"} & set(shown)

    def test_edl_kept_without_masking_shown_is_raw_and_there_is_a_notice(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path, monkeypatch, toml="[privacy]\nmask_pii = false\n")
        kept, notices = _kept(project, ONE)
        assert [kept.shown[w.id] for w in kept.words] == ["Higgsfield,", *PHONE, "gracias"]
        assert kept.masked is False and notices == [UNMASKED]


class TestMissingTranscripts:
    def test_edl_kept_a_voice_without_a_transcript_is_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path, monkeypatch, only="a1")
        kept, _ = _kept(project, _edl(("a2", 0, 0, 60), ("a1", 60, 0, 150), ("a2", 210, 60, 90)))
        assert kept.missing == ("a2",)  # once, in the order it first appears
        assert {w.src for w in kept.words} == {"a1"}

    def test_edl_kept_every_voice_without_a_transcript_in_order_of_first_appearance(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = _project(tmp_path, monkeypatch, only="a1")
        kept, _ = _kept(project, _edl(("a2", 0, 0, 30), ("a1", 30, 0, 60), ("zz", 60, 0, 30)))
        assert kept.missing == ("a2", "zz") and [w.src for w in kept.words][:1] == ["a1"]

    def test_edl_kept_an_edl_without_voice_has_no_words(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        edl = parsed(
            edit(lambda d: d.update(clips=[{"kind": "gap", "at_f": 0, "dur_f": 345, "why": "x"}]))
        )
        kept, notices = _kept(_project(tmp_path, monkeypatch), edl)
        assert (kept.words, kept.shown, kept.missing) == ([], {}, ())
        assert notices == []


class TestRepr:
    """001.24 point 11 (S1.5b row 28): the raw text is not in the `repr` of a `KeptWord` or of
    `KeptWords`, so a `print` or a log line cannot leak a phone number said in the video."""

    def test_edl_kept_repr_the_phone_said_in_words_is_not_in_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        kept, _ = _kept(_project(tmp_path, monkeypatch), ONE)
        text = repr(kept)
        assert not set(PHONE) & set(text.replace("'", " ").replace(",", " ").split())
        assert "nueve" not in text and "ocho" not in text and "siete" not in text
        assert "KeptWords(" in text and "shown=" in text and "masked=True" in text

    def test_edl_kept_repr_a_word_hides_its_text_and_keeps_where_it_is(self) -> None:
        word = KeptWord("a1:w0001", "8095551234", 1, 30, 60, "a1", 1000, 2000)
        shown = repr(word)
        assert "8095551234" not in shown and "809" not in shown
        assert "a1:w0001" in shown and "out_s_f=30" in shown

    def test_edl_kept_repr_the_words_are_still_there_to_be_read(self) -> None:
        word = KeptWord("a1:w0001", "8095551234", 1, 30, 60, "a1", 1000, 2000)
        kept = KeptWords([word], {"a1:w0001": "********34"}, (), True)
        assert kept.words[0].text == "8095551234" and kept.words == [word]
        assert "8095551234" not in repr(kept) and "********34" in repr(kept)
