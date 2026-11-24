"""A kept word that sits inside a masked number counts as masked in the diff (spec S1.9b step 0,
row 14; 001.46 point 4, 001.47 point 7).

`mask_pii` leaves `eh` and `y` as they are, so `shown[id] == text` and the old rule did not see the
word as hidden. With `809 eh 555` and a cut that keeps `llamame al 809 eh`, the heard `555` right
after the filler came out raw. `KeptWords.hidden` has the ids that `mask_pii_spans` puts inside a
number (its third set), calculated with the context of the whole clip as `shown` is.
"""

import dataclasses
import json
from pathlib import Path

import pytest

from kcut import cli
from kcut.edl.kept import KeptWords, kept_words
from kcut.pack.pii import mask_pii
from kcut.project import Project, load_inventory, open_project
from kcut.qa.report import QaReport
from kcut.qa.transcript_diff import HIDDEN_HEARD, diff_transcript, transcript_check
from kcut.transcribe.model import Word
from tests.unit.edl_fakes import Doc, edit, parsed
from tests.unit.test_pack_command import LAYOUT
from tests.unit.transcribe_fakes import FakeClip, Spoken, build_project, install_fake_engine

TOML = '[transcribe]\nfillers = ["eh"]\n'
CASES = [
    pytest.param(["llamame", "al", "809", "eh", "555", "1234", "gracias"], 4, id="filler"),
    pytest.param(["llamame", "al", "809", "y", "555", "1234", "gracias"], 4, id="bridge_y"),
    pytest.param(
        ["llamame", "al", "809", "eh", "eh", "555", "1234", "gracias"], 5, id="two_fillers"
    ),
]


def _project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, texts: list[str], toml: str
) -> Project:
    said: list[Spoken] = [(t, 1000 + 400 * k, 1300 + 400 * k, 0.9) for k, t in enumerate(texts)]
    root = build_project(tmp_path / "proyecto ñandú", [FakeClip("a1", LAYOUT)], toml=toml).root
    install_fake_engine(monkeypatch, {"a1": said})
    assert cli.main(["transcribe", "--project", str(root)]) == 0
    return open_project(str(root))


def _kept(project: Project, keep: int) -> KeptWords:
    """The words of the clip up to the `keep`-th one: the cut ends 67 ms after it."""
    out_f = int((1300 + 400 * (keep - 1) + 67) * 30 / 1000)

    def change(doc: Doc) -> None:
        doc["clips"] = [
            {"kind": "voice", "src": "a1", "at_f": 0, "in_f": 0, "out_f": out_f, "why": "x"}
        ]

    edl = parsed(edit(change))
    return kept_words(project, edl, load_inventory(project), notices=[], log=None)


@pytest.mark.parametrize(("texts", "keep"), CASES)
def test_heard_hidden_bridge_a_heard_piece_after_a_filler_or_a_bridge_is_not_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, texts: list[str], keep: int
) -> None:
    project = _project(tmp_path, monkeypatch, texts, TOML)
    kept = _kept(project, keep)
    assert [w.text for w in kept.words] == texts[:keep]  # the cut keeps the start of the number
    bridge = kept.words[keep - 1]  # `eh` or `y`: `mask_pii` leaves its text as it is
    assert kept.shown[bridge.id] == bridge.text
    assert bridge.id in kept.hidden  # 001.47: and still it is inside a masked number
    said = [*texts[:keep], "555"]
    heard = [Word(f"qa:w{i:04d}", i, t, i * 200, i * 200 + 150, 0.9) for i, t in enumerate(said)]
    shown = [w.text for w in mask_pii(heard, project.config.transcribe.fillers)[0]]
    assert shown[-1] == "555"  # control: heard alone, `mask_pii` does not hide the piece
    diff = diff_transcript(kept.words, kept.shown, heard, shown, hidden=kept.hidden)
    assert [(item.op, item.heard) for item in diff.items] == [("insert", HIDDEN_HEARD)]
    check = transcript_check(diff, 0.8, "es", 30)
    report = QaReport(
        "salida/v1.mp4", "edit/edl-v1.json", "2026-11-24T12:00:00", (check,),
        1.0, "00:11.5", None, {"probe": 1.0}, (),
    )  # fmt: skip
    for text in (json.dumps(check.data), json.dumps(report.to_json())):
        assert "555" not in text and HIDDEN_HEARD in text


def test_kept_words_hidden_with_masking_off_it_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    texts = CASES[0].values[0]
    project = _project(tmp_path, monkeypatch, texts, TOML + "[privacy]\nmask_pii = false\n")
    assert _kept(project, 4).hidden == frozenset()


def test_kept_words_hidden_has_no_default_so_a_constructor_cannot_forget_it() -> None:
    """001.49 point 4: a constructor that forgets `hidden` is a TypeError, as `limit_s` is."""
    (field,) = [f for f in dataclasses.fields(KeptWords) if f.name == "hidden"]
    assert field.default is dataclasses.MISSING
    assert field.default_factory is dataclasses.MISSING


def test_kept_words_hidden_only_has_ids_of_kept_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    texts = CASES[0].values[0]
    kept = _kept(_project(tmp_path, monkeypatch, texts, TOML), 4)
    assert isinstance(kept.hidden, frozenset) and kept.hidden  # ids, nothing of the raw text
    assert kept.hidden <= {w.id for w in kept.words}
