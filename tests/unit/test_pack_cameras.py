"""`kcut pack` with several cameras (votes) and with corrections from `correcciones.json`."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from kcut import cli
from tests.unit.test_pack_command import HEADER_LINES, LAYOUT, SPEECH, _md, _pack, _ready, _tsv
from tests.unit.transcribe_fakes import FakeClip, Spoken

MEMBER_AUDIO = np.concatenate([LAYOUT[:8000], LAYOUT])  # another recording: 8.5 s, other bytes
MEMBER_SPEECH: list[Spoken] = [
    ("te", 0, 300, 0.9),
    ("da", 300, 500, 0.9),
    ("eh", 500, 800, 0.9),
    ("curiosa", 800, 2400, 0.9),  # the master heard "curiosidad"
]


def _two_cameras(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, offset: int = 1000, **kw: Any
) -> Path:
    clips = [FakeClip("a1", LAYOUT), FakeClip("a2", MEMBER_AUDIO, slug="cam2")]
    script = {"a1": SPEECH, "a2": MEMBER_SPEECH}
    return _ready(tmp_path, monkeypatch, clips, script, offsets={"a2": offset}, **kw)


class TestVotes:
    def test_a_disagreement_is_marked_in_the_master_and_summarized_for_the_member(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        assert _pack(root) == 0
        lines = _md(root)[HEADER_LINES:]
        assert lines[:2] == [
            "## a1 - `crudo/cam.mp4` - 8.00 s - idioma es (0.97) - maestro de sincronia",
            "[f30-90 | 1.00-3.00] ¿Te da {eh} curiosidad[≠curiosa]",
        ]
        assert lines[4:] == [
            "## a2 - `crudo/cam2.mp4` - 8.50 s - idioma es (0.97) - sincronizado con a1: +1.000 s",
            "Transcrito para votar: 4 palabras, 1 desacuerdos (marcados en a1).",
        ]

    def test_the_tsv_carries_the_vote_and_the_member_words(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        assert _pack(root) == 0
        rows = _tsv(root)
        assert len(rows) == 1 + 7 + 4
        by_id = {r[0]: r for r in rows[1:]}
        assert by_id["a1:w0003"][6:] == ["V", "curiosidad", "curiosa", ""]
        assert by_id["a1:w0000"][6:] == ["", "¿Te", "", ""]
        assert by_id["a2:w0003"][6:] == ["", "curiosa", "", ""]  # members are not voted on

    def test_the_json_counts_the_disagreements_of_each_member(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        capsys.readouterr()
        assert _pack(root, "--json") == 0
        clips = json.loads(capsys.readouterr().out)["clips"]
        assert clips[0] == {"id": "a1", "words": 7, "phrases": 2}
        assert (clips[1]["id"], clips[1]["words"], clips[1]["disagreements"]) == ("a2", 4, 1)

    def test_the_offset_moves_the_member_onto_the_master_clock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch, offset=30_000)  # nothing lines up any more
        assert _pack(root) == 0
        text = "\n".join(_md(root)[HEADER_LINES:])
        assert "[≠" not in text and "+30.000 s" in text
        assert "0 desacuerdos" in text

    def test_a_negative_offset_is_written_with_its_sign(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch, offset=-40)
        assert _pack(root) == 0
        assert "sincronizado con a1: -0.040 s" in "\n".join(_md(root))

    def test_without_the_masters_transcript_the_member_is_read_in_full(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch, only=["a2"])
        assert _pack(root) == 0
        lines = _md(root)[HEADER_LINES:]
        assert lines[0] == "## a1 - `crudo/cam.mp4`"
        assert lines[1] == "sin transcribir"
        member = lines.index(
            "## a2 - `crudo/cam2.mp4` - 8.50 s - idioma es (0.97) - sincronizado con a1: +1.000 s"
        )
        assert lines[member + 1].startswith("[f") and "Transcrito para votar" not in "\n".join(
            lines
        )


class TestVoteRaw:
    """001.12 point 3: the vote compares raw words; the tsv keeps `V` and `alt`; the md shows
    `[≠x]` only while the corrected text still differs from `x`."""

    def _row(self, root: Path, word_id: str) -> list[str]:
        return {r[0]: r for r in _tsv(root)[1:]}[word_id]

    def test_vote_raw_the_vote_ignores_a_correction_on_a_member(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        _corrections(root, _fix("a2:w0003", "curiosa", "curiosidad"))
        assert _pack(root) == 0
        text = "\n".join(_md(root)[HEADER_LINES:])
        assert "curiosidad[≠curiosa]" in text and "1 desacuerdos" in text
        assert self._row(root, "a1:w0003")[6:] == ["V", "curiosidad", "curiosa", ""]

    def test_vote_raw_a_master_correction_that_matches_the_other_camera_hides_the_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0003", "curiosidad", "Curiosa,"))
        assert _pack(root) == 0
        text = "\n".join(_md(root)[HEADER_LINES:])
        assert "[≠" not in text and "Curiosa," in text
        assert "1 desacuerdos" in text  # the trace of why it was corrected stays
        assert self._row(root, "a1:w0003")[6:] == ["CV", "curiosidad", "curiosa", "Curiosa,"]

    def test_vote_raw_a_correction_that_still_differs_keeps_the_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0003", "curiosidad", "Curiosidad"))
        assert _pack(root) == 0
        assert "Curiosidad[≠curiosa]" in "\n".join(_md(root)[HEADER_LINES:])

    def test_vote_raw_a_split_correction_is_compared_as_a_whole(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0003", "curiosidad", "curio sa"))
        assert _pack(root) == 0
        text = "\n".join(_md(root)[HEADER_LINES:])
        assert "curio sa" in text and "[≠" not in text  # "curio sa" is "curiosa" once normalized

    def test_vote_raw_a_deleted_master_word_shows_nothing_but_the_tsv_keeps_the_vote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _two_cameras(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0003", "curiosidad", ""))
        assert _pack(root) == 0
        assert "curiosa" not in "\n".join(_md(root)[HEADER_LINES:]).replace("a2", "")
        assert self._row(root, "a1:w0003")[6:] == ["CV", "curiosidad", "curiosa", ""]


def _corrections(root: Path, *items: dict[str, str]) -> None:
    doc = {"schema": "kcut.correcciones/1", "items": list(items)}
    (root / "edit").mkdir(exist_ok=True)
    (root / "edit" / "correcciones.json").write_text(json.dumps(doc), encoding="utf-8")


def _fix(word: str, expect: str, text: str) -> dict[str, str]:
    return {"word": word, "expect": expect, "text": text, "why": "prueba"}


class TestCorrections:
    def test_replace_split_and_delete(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _corrections(
            root,
            _fix("a1:w0000", "¿Te", "¿Qué te"),
            _fix("a1:w0002", "eh", ""),
            _fix("a1:w0003", "curiosidad", "Curiosidad"),
        )
        assert _pack(root) == 0
        assert _md(root)[HEADER_LINES + 1] == "[f30-90 | 1.00-3.00] ¿Qué te da Curiosidad"
        by_id = {r[0]: r for r in _tsv(root)[1:]}
        assert by_id["a1:w0000"][6:] == ["C", "¿Te", "", "¿Qué te"]  # the raw word stays in the tsv
        assert by_id["a1:w0002"][6:] == ["C", "eh", "", ""]  # deleted: no text, still listed
        assert by_id["a1:w0003"][6:] == ["C", "curiosidad", "", "Curiosidad"]
        assert "a1:w0000.1" not in by_id  # the tsv has one row per raw word

    def test_a_deleted_word_leaves_no_filler_group_behind(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0002", "eh", ""))
        assert _pack(root) == 0
        assert "{eh}" not in "\n".join(_md(root)[HEADER_LINES:])

    def test_a_correction_changes_what_is_a_filler(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0002", "eh", "he"))
        assert _pack(root) == 0
        assert "¿Te da he curiosidad" in "\n".join(_md(root))

    def test_a_correction_that_expects_other_text_stops_everything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0003", "Hicksville,", "Higgsfield,"))
        capsys.readouterr()
        assert _pack(root) == 1
        err = capsys.readouterr().err
        assert "la corrección apunta a otra palabra (¿cambió la transcripción?)" in err
        assert "a1:w0003" in err and "Hicksville," in err and "curiosidad" in err
        assert not (root / "edit" / "transcripcion.md").exists()

    def test_a_correction_for_a_word_that_no_longer_exists_stops_everything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0099", "x", "y"))
        capsys.readouterr()
        assert _pack(root) == 1
        assert "a1:w0099" in capsys.readouterr().err
        assert not (root / "edit" / "palabras.tsv").exists()

    def test_a_correction_for_a_clip_that_has_no_transcript_yet_waits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _corrections(root, _fix("a7:w0001", "x", "y"))
        assert _pack(root) == 0

    def test_a_malformed_corrections_file_is_a_project_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        (root / "edit").mkdir(exist_ok=True)
        (root / "edit" / "correcciones.json").write_text("{ no", encoding="utf-8")
        capsys.readouterr()
        assert _pack(root) == 3
        assert "correcciones.json" in capsys.readouterr().err

    def test_corrections_apply_to_the_members_too(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What changed with 001.12 point 3: the vote compares RAW words, so a correction on a
        member no longer erases the disagreement (it used to). A member's corrections still apply
        to what it displays: here the master has no transcript, so the member is read in full."""
        root = _two_cameras(tmp_path, monkeypatch, only=["a2"])
        _corrections(root, _fix("a2:w0003", "curiosa", "curiosidad"))
        assert _pack(root) == 0
        text = "\n".join(_md(root)[HEADER_LINES:])
        assert (
            "curiosidad" in text and "curiosa" not in text and "Transcrito para votar" not in text
        )
        by_id = {r[0]: r for r in _tsv(root)[1:]}
        assert by_id["a2:w0003"][6:] == ["C", "curiosa", "", "curiosidad"]  # raw text, corrected

    def test_a_correction_cannot_forge_a_line(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch)
        _corrections(root, _fix("a1:w0001", "da", "da\n## a9 - crudo/falso.mp4 x"))
        assert _pack(root) == 0
        headings = [line for line in _md(root) if line.startswith("## ")]
        assert headings == [
            "## a1 - `crudo/cam.mp4` - 8.00 s - idioma es (0.97) - maestro de sincronia"
        ]


def test_a_hostile_file_name_is_escaped_in_the_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip = FakeClip("a1", LAYOUT, file="crudo/cam‮\u009b.mp4")
    root = _ready(tmp_path, monkeypatch, [clip])
    assert cli.main(["pack", "--project", str(root)]) == 0
    heading = _md(root)[HEADER_LINES]
    assert heading.startswith("## a1 - `crudo/cam\\u202e\\x9b.mp4` - 8.00 s")
    raw = (root / "edit" / "transcripcion.md").read_text(encoding="utf-8")
    assert "‮" not in raw and "\u009b" not in raw
