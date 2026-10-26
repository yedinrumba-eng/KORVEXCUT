"""The words `kcut view` draws: corrected, masked as a whole, and doubtful by `?` or `H`.

`window_words` is pure; the rest runs the command in process on a project written by hand (no
ffmpeg, no model): a fake engine says the words, the wav16 is synthetic (spec S1.4, 001.15 T1/T2).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut import cli
from kcut.commands import view
from kcut.transcribe.model import Word
from kcut.viz.timeline import ViewWord, window_words
from tests.unit.test_pack_command import LAYOUT
from tests.unit.transcribe_fakes import (
    FakeClip,
    Spoken,
    build_project,
    install_fake_engine,
    tone,
)

FPS = 30
PHONE = ["nueve", "siete", "dos", "ocho", "cero", "ocho", "tres"]
# LAYOUT: quiet 0-1 s, loud 1-3 s, quiet 3-4.5 s, loud 4.5-6 s, quiet 6-8 s
SAID: list[Spoken] = [
    ("Hicksville,", 1000, 1400, 0.9),  # corrected to "Higgsfield," below
    *[(w, 1500 + 300 * k, 1700 + 300 * k, 0.9) for k, w in enumerate(PHONE)],  # 1.5 s - 3.5 s
    ("fantasma", 3700, 4300, 0.9),  # all of it inside the quiet 3 s - 4.5 s: a possible ghost
    ("dudosa", 4600, 4900, 0.2),  # p < low_prob (0.5)
]


def _word(i: int, text: str, s_ms: int, e_ms: int, p: float = 0.9) -> Word:
    return Word(f"a1:w{i:04d}", i, text, s_ms, e_ms, p)


class TestWindowWords:
    def test_view_words_touching_is_compared_in_whole_units(self) -> None:
        words = [
            _word(0, "antes", 0, 100),
            _word(1, "dentro", 100, 200),
            _word(2, "luego", 200, 300),
        ]
        found = window_words(words, 3, 6, FPS, 0.5, [])  # frames 3..6 = 100 ms .. 200 ms
        assert [w.text for w in found] == ["dentro"]  # the others only touch at the edges

    def test_view_words_a_word_that_crosses_an_edge_is_in(self) -> None:
        words = [
            _word(0, "entra", 50, 150),
            _word(1, "sale", 150, 250),
            _word(2, "fuera", 400, 500),
        ]
        assert [w.text for w in window_words(words, 3, 6, FPS, 0.5, [])] == ["entra", "sale"]

    def test_view_words_words_without_text_are_left_out(self) -> None:
        words = [_word(0, "", 100, 200), _word(1, "queda", 100, 200)]
        assert [w.id for w in window_words(words, 0, 30, FPS, 0.5, [])] == ["a1:w0001"]

    def test_view_words_the_fields_of_a_view_word(self) -> None:
        (found,) = window_words([_word(7, "hola", 120, 450)], 0, 30, FPS, 0.5, [])
        assert found == ViewWord("a1:w0007", "hola", 120, 450, False)

    def test_view_words_doubtful_is_p_under_low_prob(self) -> None:
        words = [_word(0, "seguro", 0, 100, 0.5), _word(1, "dudoso", 100, 200, 0.49)]
        found = window_words(words, 0, 30, FPS, 0.5, [])
        assert [w.doubtful for w in found] == [False, True]

    def test_view_words_doubtful_is_also_a_word_whole_inside_a_silence(self) -> None:
        words = [
            _word(0, "eco", 1000, 1200),
            _word(1, "medio", 1900, 2100),
            _word(2, "voz", 3000, 3200),
        ]
        found = window_words(words, 0, 150, FPS, 0.5, [(900, 2000)])
        assert [w.doubtful for w in found] == [True, False, False]  # "medio" leaves the silence

    def test_view_words_an_empty_window_gives_an_empty_list(self) -> None:
        assert window_words([_word(0, "hola", 0, 100)], 90, 120, FPS, 0.5, []) == []


@dataclass
class Seen:
    """What the command handed to `window_words` and what came back, plus its output."""

    given: list[Word]
    found: list[ViewWord]
    doc: dict[str, Any]
    err: str


def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toml: str = "") -> Path:
    root = build_project(
        tmp_path / "proyecto ñandú", [FakeClip("a1", LAYOUT)], toml=toml, master="a1"
    ).root
    install_fake_engine(monkeypatch, {"a1": SAID})
    assert cli.main(["transcribe", "--project", str(root)]) == 0
    item = {"word": "a1:w0000", "expect": "Hicksville,", "text": "Higgsfield,", "why": "x"}
    document = {"schema": "kcut.correcciones/1", "items": [item]}
    (root / "edit").mkdir(exist_ok=True)
    (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")
    return root


def _view(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    start: str = "0",
    end: str = "6s",
    clip: str = "a1",
) -> Seen:
    given: list[Word] = []
    found: list[ViewWord] = []
    original = view.window_words

    def spy(words: Any, *rest: Any) -> list[ViewWord]:
        given.extend(words)
        found.extend(original(words, *rest))
        return list(found)

    monkeypatch.setattr(view, "window_words", spy)
    capsys.readouterr()
    code = cli.main(["view", clip, start, end, "--project", str(root), "--json"])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    return Seen(given, found, json.loads(captured.out), captured.err)


class TestViewUsesCorrectedMaskedWords:
    def test_view_words_gets_the_corrected_text_and_the_masked_digits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seen = _view(_project(tmp_path, monkeypatch), monkeypatch, capsys)
        texts = [w.text for w in seen.given]
        assert texts[0] == "Higgsfield,"  # the correction, not "Hicksville,"
        assert texts[1:8] == ["*", "*", "*", "*", "*", "8", "3"]  # all but the last two digits
        assert "nueve" not in texts and "Hicksville," not in texts
        assert seen.doc["warnings"] == [] and seen.doc["notice"] is None

    def test_view_words_without_masking_they_are_raw_and_there_is_a_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _project(tmp_path, monkeypatch, toml="[privacy]\nmask_pii = false\n")
        seen = _view(root, monkeypatch, capsys)
        texts = [w.text for w in seen.given]
        assert texts[0] == "Higgsfield," and texts[1:8] == PHONE
        message = "PII sin enmascarar (privacy.mask_pii = false)"
        assert seen.doc["warnings"] == [{"code": "pii_unmasked", "message_es": message}]
        assert f"pii_unmasked: {message}" in seen.err

    def test_view_words_the_number_is_masked_over_the_whole_clip_not_the_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # 2.5 s - 3.6 s holds only the last four words of the number: alone they are 4 digits,
        # but the number was masked with the whole list before the window was cut out
        seen = _view(_project(tmp_path, monkeypatch), monkeypatch, capsys, "2.5s", "3.6s")
        texts = [w.text for w in seen.found]
        assert texts and set(texts) <= {"*", "8", "3"}
        assert not {"ocho", "cero", "tres", "dos"} & set(texts)

    def test_view_words_the_json_counts_the_boxes_drawn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seen = _view(_project(tmp_path, monkeypatch), monkeypatch, capsys)
        assert seen.doc["words"] == len(seen.found) == 10  # the 7 digits, 3 more words
        assert (tmp_path / "proyecto ñandú" / seen.doc["png"]).is_file()

    def test_view_words_doubtful_comes_from_p_and_from_silence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seen = _view(_project(tmp_path, monkeypatch), monkeypatch, capsys)
        flags = {w.text: w.doubtful for w in seen.found}
        assert flags["dudosa"] is True  # p = 0.2 < 0.5
        assert flags["fantasma"] is True  # the whole word is in the quiet stretch
        assert flags["Higgsfield,"] is False


# 001.19 point 2: the camera that heard less is masked where the other one masked
MASTER = ["mi", "numero", "972", "y", "3211", "gracias"]
HEARD = ["mi", "numero", "972", "808", "gracias", "ya"]  # six digits alone: no PII for a2


def _say(texts: list[str]) -> list[Spoken]:
    return [(t, 1000 + k * 330, 1300 + k * 330, 0.9) for k, t in enumerate(texts)]


def _two_cameras(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toml: str = "") -> Path:
    clips = [FakeClip("a1", LAYOUT), FakeClip("a2", LAYOUT * np.float32(0.9), slug="cam2")]
    root = build_project(
        tmp_path / "proyecto ñandú", clips, toml=toml, master="a1", offsets={"a2": 0}
    ).root
    install_fake_engine(monkeypatch, {"a1": _say(MASTER), "a2": _say(HEARD)})
    assert cli.main(["transcribe", "--project", str(root)]) == 0
    return root


class TestViewCoveredByAnotherCamera:
    def test_view_words_covered_by_the_other_camera_are_stars(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        seen = _view(root, monkeypatch, capsys, clip="a2")
        shown = {w.id: w.text for w in seen.found}
        # a2 alone has six digits ("972 808") and masks nothing; a1's number covers its words
        assert [shown[f"a2:w000{n}"] for n in range(6)] == ["mi", "numero", "*", "*", "*", "ya"]
        assert seen.doc["words"] == len(seen.found) == 6
        assert "808" not in "".join(shown.values()) and "972" not in "".join(shown.values())

    def test_view_words_covered_a_covered_word_is_never_doubtful_text_leaking(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        seen = _view(root, monkeypatch, capsys, clip="a2")
        assert [w.text for w in seen.given if w.id == "a2:w0003"] == ["*"]  # one star, no length

    def test_view_words_covered_the_master_keeps_what_its_own_mask_gives(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        seen = _view(root, monkeypatch, capsys, clip="a1")
        assert [w.text for w in seen.found][:6] == ["mi", "numero", "***", "y", "**11", "gracias"]

    def test_view_words_covered_with_masking_off_nothing_is_covered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch, toml="[privacy]\nmask_pii = false\n")
        seen = _view(root, monkeypatch, capsys, clip="a2")
        assert [w.text for w in seen.found] == HEARD
        assert seen.doc["warnings"][0]["code"] == "pii_unmasked"


class TestViewBoxesCapped:
    def test_boxes_capped_view_draws_the_first_400_and_says_so(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        said = [(f"p{k}", 500 + k * 70, 500 + k * 70 + 60, 0.9) for k in range(440)]
        clips = [FakeClip("a1", tone(35.0))]
        root = build_project(tmp_path / "proyecto ñandú", clips, master="a1").root
        install_fake_engine(monkeypatch, {"a1": said})
        assert cli.main(["transcribe", "--project", str(root)]) == 0
        capsys.readouterr()
        code = cli.main(["view", "a1", "0", "35s", "--project", str(root), "--json"])
        captured = capsys.readouterr()
        assert code == 0, captured.err
        doc = json.loads(captured.out)
        assert doc["words"] == 400
        fixed = "hay más de 400 palabras en la ventana; se dibujan las primeras 400"
        assert doc["warnings"] == [{"code": "words_capped", "message_es": fixed}]
        assert f"words_capped: {fixed}" in captured.err

    def test_boxes_capped_400_words_or_fewer_say_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        said = [(f"p{k}", 500 + k * 70, 500 + k * 70 + 60, 0.9) for k in range(400)]
        clips = [FakeClip("a1", tone(35.0))]
        root = build_project(tmp_path / "proyecto ñandú", clips, master="a1").root
        install_fake_engine(monkeypatch, {"a1": said})
        assert cli.main(["transcribe", "--project", str(root)]) == 0
        capsys.readouterr()
        assert cli.main(["view", "a1", "0", "35s", "--project", str(root), "--json"]) == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["words"] == 400 and doc["warnings"] == []
