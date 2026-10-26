"""PII in `kcut pack`, round 5 (spec 001.17): alternatives behind bridges, corrections that open a
masked number, and file names read by parts. The classes are collected from `test_pii_pack.py`."""

import json
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from kcut.pack.crosscam import covered_ids
from kcut.pack.pii import mask_pii, mask_pii_spans, mask_text
from kcut.transcribe.model import Word
from tests.unit.test_pack_command import LAYOUT, _md, _pack, _ready, _tsv
from tests.unit.transcribe_fakes import FakeClip, Spoken, tone

__all__ = ["TestPiiAltBridgeHidden", "TestPiiCorrectionUnmasks", "TestPiiPathParts"]


def _say(texts: list[str], start: int = 1000, step: int = 330) -> list[Spoken]:
    return [(t, start + i * step, start + i * step + 300, 0.9) for i, t in enumerate(texts)]


def _text(root: Path) -> str:
    return "\n".join(_md(root)) + (root / "edit" / "palabras.tsv").read_text(encoding="utf-8")


MASTER = ["mi", "numero", "972", "y", "3211", "gracias"]
LOST_LAST_GROUP = ["mi", "numero", "972", "808", "gracias", "ya"]  # in its context 808 is no PII
HEARD_ALONE = ["mi", "numero", "es", "808", "listo", "gracias"]
INSIDE = ["mi", "numero", "972", "808", "3211", "gracias"]


class TestPiiAltBridgeHidden:
    """001.17 point 2: the alternative of EVERY master word inside a masked number is hidden,
    bridges and separators included, whichever camera it came from."""

    def _cameras(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        master: list[str],
        members: dict[str, list[str]],
    ) -> Path:
        clips = [FakeClip("a1", LAYOUT)]
        script = {"a1": _say(master)}
        for n, (clip_id, words) in enumerate(members.items()):
            clips.append(FakeClip(clip_id, LAYOUT * np.float32(0.9 - n / 10), slug=f"c{n}"))
            script[clip_id] = _say(words)
        offsets = dict.fromkeys(members, 0)
        root = _ready(tmp_path, monkeypatch, clips, script, offsets=offsets)
        assert _pack(root, "--json") == 0
        return root

    @pytest.mark.parametrize("member", [LOST_LAST_GROUP, HEARD_ALONE], ids=["lost_group", "alone"])
    def test_alt_bridge_hidden_with_two_cameras(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, member: list[str]
    ) -> None:
        root = self._cameras(tmp_path, monkeypatch, MASTER, {"a2": member})
        assert "808" not in _text(root)

    @pytest.mark.parametrize("order", [("a2", "a3"), ("a3", "a2")], ids=["a2_first", "a3_first"])
    def test_alt_bridge_hidden_with_three_cameras_in_any_order(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, order: tuple[str, str]
    ) -> None:
        heard = {"a2": INSIDE, "a3": HEARD_ALONE}
        root = self._cameras(tmp_path, monkeypatch, MASTER, {k: heard[k] for k in order})
        assert "808" not in _text(root)

    def test_alt_bridge_hidden_the_bridge_shows_stars_in_the_md_and_the_tsv(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._cameras(tmp_path, monkeypatch, MASTER, {"a2": LOST_LAST_GROUP})
        rows = {r[0]: r for r in _tsv(root)[1:]}
        assert rows["a1:w0003"][7:9] == [
            "y",
            "*",
        ]  # the bridge, and its alternative hidden: one star
        assert "y[≠*]" in "\n".join(_md(root))

    def test_alt_bridge_hidden_a_neutral_word_inside_the_number_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        master = ["mi", "972", "double", "5", "5", "5", "gracias"]  # `double` is neutral here
        member = ["mi", "hola", "808", "listo", "ya", "ok", "gracias"]
        root = self._cameras(tmp_path, monkeypatch, master, {"a2": member})
        assert "808" not in _text(root)

    def test_alt_bridge_hidden_outside_a_masked_number_the_alternative_is_still_shown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        master = ["mi", "casa", "es", "y", "gracias", "ya"]
        member = ["mi", "casa", "es", "808", "gracias", "ya"]
        root = self._cameras(tmp_path, monkeypatch, master, {"a2": member})
        assert {r[0]: r for r in _tsv(root)[1:]}["a1:w0003"][8] == "808"

    def test_alt_bridge_hidden_the_detector_says_which_words_are_inside(self) -> None:
        words = [Word(f"a1:w{i}", i, t, i * 100, i * 100 + 90, 0.9) for i, t in enumerate(MASTER)]
        shown, ids, inside = mask_pii_spans(words)
        assert ids == {"a1:w2", "a1:w4"}  # the digits
        assert inside == {"a1:w2", "a1:w3", "a1:w4"}  # and the "y" between them
        assert mask_pii(words)[1] == ids and [w.text for w in shown][2:5] == ["***", "y", "**11"]

    def test_alt_bridge_hidden_words_outside_the_number_are_not_inside(self) -> None:
        words = [Word(f"a1:w{i}", i, t, i * 100, i * 100 + 90, 0.9) for i, t in enumerate(MASTER)]
        assert not {"a1:w0", "a1:w1", "a1:w5"} & mask_pii_spans(words)[2]

    def test_alt_bridge_hidden_the_member_rows_under_the_master_mask_are_masked_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The member missed the last group: alone its "972 808" is six digits and no PII, but the
        master heard a phone number there, so those rows are masked and flagged `P`."""
        root = self._cameras(tmp_path, monkeypatch, MASTER, {"a2": LOST_LAST_GROUP})
        rows = {r[0]: r for r in _tsv(root)[1:]}
        for word_id in ("a2:w0002", "a2:w0003"):
            assert rows[word_id][7] == "*" and "P" in rows[word_id][6], word_id
        assert rows["a2:w0000"][7:] == ["mi", "", ""] and rows["a2:w0001"][6] == ""
        assert "972" not in _text(root)

    def test_alt_bridge_hidden_covering_goes_the_other_way_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The member heard the whole number and the master only part of it: the master's words
        at that time are masked as well."""
        master = ["mi", "numero", "972", "808", "gracias", "ya"]
        root = self._cameras(tmp_path, monkeypatch, master, {"a2": INSIDE})
        rows = {r[0]: r for r in _tsv(root)[1:] if r[1] == "a1"}
        assert rows["a1:w0002"][7] == "*" and rows["a1:w0003"][7] == "*"
        assert "972" not in _text(root) and "808" not in _text(root)

    def test_alt_bridge_hidden_a_word_barely_touching_the_span_is_left_alone(self) -> None:
        master = [Word(f"a1:w{i}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(MASTER)]
        member = [
            Word("a2:w0", 0, "ya", 5 * 400 + 300, 5 * 400 + 700, 0.9),  # 50 of its 400 ms
            Word("a2:w1", 1, "808", 3 * 400, 3 * 400 + 350, 0.9),  # all of it
        ]
        inside = mask_pii_spans(master)[2]
        found = covered_ids({"a1": (master, inside, 0), "a2": (member, set(), 0)})
        assert found == {"a2": {"a2:w1"}}

    def test_alt_bridge_hidden_the_offset_puts_the_member_on_the_masters_clock(self) -> None:
        master = [Word(f"a1:w{i}", i, t, i * 400, i * 400 + 350, 0.9) for i, t in enumerate(MASTER)]
        member = [Word("a2:w0", 0, "808", 3 * 400 - 1000, 3 * 400 - 1000 + 350, 0.9)]
        inside = mask_pii_spans(master)[2]
        assert covered_ids({"a1": (master, inside, 0), "a2": (member, set(), 1000)}) == {
            "a2": {"a2:w0"}
        }
        assert covered_ids({"a1": (master, inside, 0), "a2": (member, set(), 0)}) == {}

    def test_alt_bridge_hidden_nothing_is_covered_when_masking_is_off(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        toml = "[privacy]\nmask_pii = false\n"
        clips = [FakeClip("a1", LAYOUT), FakeClip("a2", LAYOUT * np.float32(0.9), slug="c2")]
        script = {"a1": _say(MASTER), "a2": _say(LOST_LAST_GROUP)}
        root = _ready(tmp_path, monkeypatch, clips, script, toml=toml, offsets={"a2": 0})
        assert _pack(root) == 0
        assert {r[0]: r for r in _tsv(root)[1:]}["a2:w0003"][6:8] == ["", "808"]


class TestPiiCorrectionUnmasks:
    """001.17 point 5: after the corrections, a word masked in the raw text has to stay masked."""

    SAID: ClassVar[list[str]] = [
        *("mi", "numero", "ocho", "cero", "nueve", "eh", "cinco", "cinco", "cinco"),
        *("uno", "dos", "tres", "cuatro"),
    ]

    def _ready(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        spoken = _say(self.SAID, step=300)
        return _ready(tmp_path, monkeypatch, [FakeClip("a1", tone(8.0))], {"a1": spoken})

    def _fix(self, root: Path, word: str, expect: str, text: str) -> None:
        item = {"word": word, "expect": expect, "text": text, "why": "x"}
        (root / "edit").mkdir(exist_ok=True)
        document = {"schema": "kcut.correcciones/1", "items": [item]}
        (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")

    def test_correction_unmasks_the_bridge_changed_to_a_word_is_check_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = self._ready(tmp_path, monkeypatch)
        self._fix(root, "a1:w0005", "eh", "a b c d e f g")  # 001.20: one word is an aside
        capsys.readouterr()
        assert _pack(root, "--json") == 1
        error = json.loads(capsys.readouterr().out)["error"]
        assert (error["exit_code"], error["kind"]) == (1, "CheckFailed")
        assert error["message"] == (
            "la corrección de a1:w0005 dejaría ver un dato privado; no se aplica"
        )
        assert not (root / "edit" / "transcripcion.md").exists()

    def test_correction_unmasks_deleting_the_bridge_keeps_the_number_masked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._ready(tmp_path, monkeypatch)
        self._fix(root, "a1:w0005", "eh", "")
        assert _pack(root) == 0
        md = "\n".join(_md(root))
        assert "ocho" not in md and "cinco" not in md and "* * *" in md

    def test_correction_unmasks_two_words_instead_of_the_bridge_is_check_failed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._ready(tmp_path, monkeypatch)
        self._fix(
            root, "a1:w0005", "eh", "a b c d e f g"
        )  # 001.20: seven words, "a ver" is an aside
        assert _pack(root) == 1

    def test_correction_unmasks_another_bridge_word_keeps_the_number_masked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._ready(tmp_path, monkeypatch)
        self._fix(root, "a1:w0005", "eh", "y")
        assert _pack(root) == 0
        assert "ocho" not in "\n".join(_md(root))

    def test_correction_unmasks_a_word_far_from_the_number_is_fine(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = self._ready(tmp_path, monkeypatch)
        self._fix(root, "a1:w0000", "mi", "mí")
        assert _pack(root) == 0
        assert "mí" in "\n".join(_md(root))

    def test_correction_unmasks_names_the_correction_not_the_word_that_came_to_light(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = self._ready(tmp_path, monkeypatch)
        self._fix(root, "a1:w0005", "eh", "a b c d e f g")  # 001.20: one word is an aside
        capsys.readouterr()
        _pack(root)
        err = capsys.readouterr().err
        assert "a1:w0005" in err and "a1:w0002" not in err and "ocho" not in err


class TestPiiPathParts:
    """001.17 point 6: a path is read by parts (`/ _ . -`), the extension apart."""

    def test_path_parts_a_number_split_by_spaces_in_the_name_is_masked(self) -> None:
        assert mask_text("crudo/Juan 809 555 1234.mp4") == "crudo/Juan *** *** **34.mp4"

    def test_path_parts_camera_names_stay_distinguishable(self) -> None:
        assert mask_text("GX010123.MP4") == "GX010123.MP4"  # six digits
        first = mask_text("crudo/VID_20261025_143015.mp4")
        second = mask_text("crudo/VID_20261025_150215.mp4")
        assert first != second and first.endswith("_143015.mp4") and second.endswith("_150215.mp4")

    def test_path_parts_the_extension_does_not_count_its_digits(self) -> None:
        assert mask_text("tel1234567.mp4") == "tel*****67.mp4"  # not "...4" from the extension
        assert mask_text("IMG_123456.mp4") == "IMG_123456.mp4"
        assert mask_text("clip.1234") == "clip.1234"

    def test_path_parts_a_part_alone_with_seven_digits_is_masked(self) -> None:
        assert mask_text("crudo/IMG_8095551234.mov") == "crudo/IMG_********34.mov"

    def test_path_parts_each_part_is_read_on_its_own(self) -> None:
        assert mask_text("crudo/cam a/IMG 123.mp4") == "crudo/cam a/IMG 123.mp4"

    def test_path_parts_a_name_is_read_whole_not_by_parts(self) -> None:
        assert mask_text("Boda 809-555-1234", parts=False) == "Boda ***-***-**34"
        assert mask_text("Boda 809 555 1234") == "Boda *** *** **34"

    def test_path_parts_text_without_digits_comes_back_the_same(self) -> None:
        for text in ("", "crudo/voz.wav", "a/b_c-d.e.mp4", "  espacios  ", "ñandú_ÿ.mov"):
            assert mask_text(text) == text
