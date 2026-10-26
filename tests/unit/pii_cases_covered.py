"""Words that only another camera's mask covers (spec 001.17, closing hotfix of round 5).

The master heard "972 y 3211" and the member "972 808", six digits: alone, the member masks nothing.
Its rows are masked because of the master. Claude sees `*` with the `P` flag there, so it may try
to correct them: the answer must not quote what is behind the mask, and a covered word must not
show how long it was ("cuatro" as six stars). Collected from `test_pii_pack.py`.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from kcut.pack.assemble import displayed_alts
from kcut.pack.votes import tally
from kcut.transcribe.model import Word
from tests.unit.test_pack_command import LAYOUT, _md, _pack, _ready, _tsv
from tests.unit.transcribe_fakes import FakeClip, Spoken

__all__ = ["TestPiiAltStraddle", "TestPiiCoveredCorrection"]

MASTER = ["mi", "numero", "972", "y", "3211", "gracias"]


def _say(texts: list[str]) -> list[Spoken]:
    return [(t, 1000 + i * 330, 1000 + i * 330 + 300, 0.9) for i, t in enumerate(texts)]


def _two_cameras(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, heard: str = "808") -> Path:
    clips = [FakeClip("a1", LAYOUT), FakeClip("a2", LAYOUT * np.float32(0.9), slug="c2")]
    script = {"a1": _say(MASTER), "a2": _say(["mi", "numero", "972", heard, "gracias", "ya"])}
    root = _ready(tmp_path, monkeypatch, clips, script, offsets={"a2": 0})
    assert _pack(root, "--json") == 0
    return root


def _fix(root: Path, word: str, expect: str, text: str) -> None:
    item = {"word": word, "expect": expect, "text": text, "why": "x"}
    (root / "edit").mkdir(exist_ok=True)
    document = {"schema": "kcut.correcciones/1", "items": [item]}
    (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")


class TestPiiCoveredCorrection:
    @pytest.mark.parametrize(
        ("word", "expect"),
        [
            ("a2:w0003", "***"),  # covered: what Claude sees
            ("a2:w0003", "808"),  # covered: what Claude guesses
            ("a2:w0002", "***"),
            ("a2:w0002", "972"),
            ("a2:w0004", "gracias"),  # covered by the last group of the master
            ("a1:w0002", "***"),  # masked by its own camera
        ],
    )
    def test_correction_unmasks_a_covered_word_cannot_be_corrected(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        word: str,
        expect: str,
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        (root / "edit" / "palabras.tsv").unlink()
        (root / "edit" / "transcripcion.md").unlink()
        _fix(root, word, expect, "")
        capsys.readouterr()
        assert _pack(root, "--json") == 1
        out = capsys.readouterr().out
        error = json.loads(out)["error"]
        assert (error["exit_code"], error["kind"]) == (1, "CheckFailed")
        assert error["message"] == (
            f"la palabra {word} está enmascarada por privacidad; no se corrige desde aquí"
        )
        assert "808" not in out and "972" not in out and "3211" not in out
        assert not (root / "edit" / "palabras.tsv").exists()

    def test_correction_unmasks_a_covered_word_in_human_mode_says_the_same(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        _fix(root, "a2:w0003", "808", "otra")
        capsys.readouterr()
        assert _pack(root) == 1
        err = capsys.readouterr().err
        assert "a2:w0003 está enmascarada por privacidad" in err and "808" not in err

    def test_correction_unmasks_a_word_nobody_covers_is_still_corrected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        _fix(root, "a2:w0000", "mi", "mí")
        assert _pack(root) == 0
        assert {r[0]: r for r in _tsv(root)[1:]}["a2:w0000"][9] == "mí"

    @pytest.mark.parametrize("heard", ["808", "cuatro", "nueve"])
    def test_alt_bridge_hidden_a_covered_word_is_one_star_whatever_it_said(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, heard: str
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch, heard)
        rows = {r[0]: r for r in _tsv(root)[1:]}
        assert [rows[f"a2:w000{n}"][7] for n in (2, 3, 4)] == ["*", "*", "*"]  # text, no length
        assert rows["a1:w0003"][8] == "*" and rows["a1:w0004"][8] == "*"  # alt, no length
        assert "y[≠*]" in "\n".join(_md(root))
        assert heard not in "\n".join(_md(root)) + (root / "edit" / "palabras.tsv").read_text(
            encoding="utf-8"
        )


def _flow(texts: list[str], start: int = 1000, step: int = 300) -> list[Spoken]:
    """Words one right after the other (no gaps), so a shift of half a word is easy to say."""
    return [(t, start + i * step, start + (i + 1) * step, 0.9) for i, t in enumerate(texts)]


class TestPiiAltStraddle:
    """001.18 point 1: a word of the member that sits under a mask (its own or another camera's)
    is `*` also when it is the alternative of ANOTHER master word, at the edge of the mask."""

    def test_alt_straddle_half_a_word_over_the_edge_of_the_mask(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # the master masks "972 y 3211" (1600-2500 ms); the member heard "972 808", six digits,
        # so alone it masks nothing, and its 808 sits half under the mask and half over "gracias"
        clips = [FakeClip("a1", LAYOUT), FakeClip("a2", LAYOUT * np.float32(0.9), slug="c2")]
        member: list[Spoken] = [
            ("mi", 1000, 1300, 0.9),
            ("numero", 1300, 1600, 0.9),
            ("972", 1600, 1900, 0.9),
            ("808", 2350, 2650, 0.9),  # 150 ms under the mask, 150 ms over "gracias"
            ("ya", 2800, 3100, 0.9),
        ]
        script = {"a1": _flow(MASTER), "a2": member}
        root = _ready(tmp_path, monkeypatch, clips, script, offsets={"a2": 0})
        assert _pack(root, "--json") == 0
        md = "\n".join(_md(root))
        tsv = (root / "edit" / "palabras.tsv").read_text(encoding="utf-8")
        assert "gracias[≠808]" not in md
        assert "808" not in md and "808" not in tsv
        rows = {r[0]: r for r in _tsv(root)[1:]}
        assert rows["a1:w0005"][6:9] == ["V", "gracias", "*"]  # voted, and the variant is hidden
        assert "gracias[≠*]" in md

    def test_alt_straddle_a_bridge_inside_the_members_own_mask_is_a_star(self) -> None:
        def word(clip: str, i: int, text: str, s: int, e: int) -> Word:
            return Word(f"{clip}:w{i:04d}", i, text, s, e, 0.9)

        master = [word("a1", 0, "porque", 1300, 1600)]
        member = [  # "972 y 808 3211": the `y` is a bridge inside the member's own number
            word("a2", 0, "972", 1000, 1300),
            word("a2", 1, "y", 1300, 1600),
            word("a2", 2, "808", 1600, 1900),
            word("a2", 3, "3211", 1900, 2200),
        ]
        result = tally(master, [(member, 0)])
        assert result.alternatives == {"a1:w0000": "y"}  # the vote itself runs on the raw words
        shown = displayed_alts(result, [member], (), True)
        assert shown == {"a1:w0000": "*"}
        assert displayed_alts(result, [member], (), False) == {"a1:w0000": "y"}  # masking off

    def test_alt_straddle_a_covered_word_is_a_star_as_the_alternative(self) -> None:
        def word(clip: str, i: int, text: str, s: int, e: int) -> Word:
            return Word(f"{clip}:w{i:04d}", i, text, s, e, 0.9)

        master = [word("a1", 0, "gracias", 2500, 2800)]
        member = [word("a2", 0, "808", 2350, 2650)]
        result = tally(master, [(member, 0)])
        assert displayed_alts(result, [member], (), True) == {"a1:w0000": "808"}  # nobody covers it
        covered = [{"a2:w0000"}]
        assert displayed_alts(result, [member], (), True, covered) == {"a1:w0000": "*"}
