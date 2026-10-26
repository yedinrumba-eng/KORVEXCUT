"""PII in `kcut pack`: the `[privacy]` config, corrections on masked words, the `P` flag."""

import json
from pathlib import Path

import numpy as np
import pytest

from kcut import cli
from kcut.config.load import parse_config
from kcut.config.template import render_template
from kcut.errors import ProjectError
from kcut.pack.pii import mask_text
from kcut.pack.votes import tally
from kcut.transcribe.model import Word
from tests.unit.pii_cases_covered import *  # noqa: F403
from tests.unit.pii_cases_pack import *  # noqa: F403  (001.17: collected here, 300-line rule)
from tests.unit.pii_cases_paths import *  # noqa: F403  (001.18)
from tests.unit.test_pack_command import HEADER_LINES, LAYOUT, _md, _pack, _ready, _tsv
from tests.unit.transcribe_fakes import (
    FakeClip,
    Spoken,
    build_project,
    install_fake_engine,
    tone,
)

UNMASKED = "PII sin enmascarar (privacy.mask_pii = false)"
PHONE: list[Spoken] = [
    ("llama", 1000, 1300, 0.9),
    ("972", 1300, 1600, 0.3),  # doubtful (p < 0.5) and masked
    ("808", 1600, 1900, 0.9),
    ("3211", 1900, 2400, 0.9),
    ("ya", 4500, 4800, 0.9),
]


def _fix(root: Path, word: str, expect: str, text: str) -> None:
    item = {"word": word, "expect": expect, "text": text, "why": "x"}
    (root / "edit").mkdir(exist_ok=True)
    document = {"schema": "kcut.correcciones/1", "items": [item]}
    (root / "edit" / "correcciones.json").write_text(json.dumps(document), encoding="utf-8")


def _row(root: Path, word_id: str) -> list[str]:
    return {r[0]: r for r in _tsv(root)[1:]}[word_id]


class TestPiiConfig:
    def test_pii_config_masks_by_default(self) -> None:
        assert parse_config("", default_name="x").privacy.mask_pii is True

    def test_pii_config_the_template_carries_the_section_and_parses_back(self) -> None:
        text = render_template("x", "9:16", 30, "es", "2026-10-25")
        assert "[privacy]\nmask_pii = true" in text
        assert parse_config(text, default_name="x").privacy.mask_pii is True

    def test_pii_config_can_be_turned_off(self) -> None:
        cfg = parse_config("[privacy]\nmask_pii = false\n", default_name="x")
        assert cfg.privacy.mask_pii is False

    @pytest.mark.parametrize(
        ("text", "path"),
        [
            ('[privacy]\nmask_pii = "si"\n', "privacy.mask_pii"),
            ("[privacy]\nmask_pii = 1\n", "privacy.mask_pii"),
            ("[privacy]\nmask = true\n", "privacy."),
        ],
        ids=["string", "integer", "unknown_key"],
    )
    def test_pii_config_rejects_bad_values(self, text: str, path: str) -> None:
        with pytest.raises(ProjectError) as info:
            parse_config(text, default_name="x")
        assert path in info.value.message_es

    def test_pii_config_off_masks_nothing_and_warns_on_every_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(
            tmp_path, monkeypatch, script={"a1": PHONE}, toml="[privacy]\nmask_pii = false\n"
        )
        for _ in range(2):  # a warning in each run, not only the first
            capsys.readouterr()
            assert _pack(root, "--json") == 0
            captured = capsys.readouterr()
            assert f"pii_unmasked: {UNMASKED}" in captured.err
            warnings = json.loads(captured.out)["warnings"]
            assert {"id": None, "code": "pii_unmasked", "message_es": UNMASKED} in warnings
        assert "llama 972? 808 3211" in "\n".join(_md(root)[HEADER_LINES:])
        assert _row(root, "a1:w0001")[6:8] == ["?", "972"]  # no P flag, no mask

    def test_pii_config_on_does_not_warn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": PHONE})
        capsys.readouterr()
        assert _pack(root, "--json") == 0
        captured = capsys.readouterr()
        assert "pii_unmasked" not in captured.err + captured.out


class TestPiiCorrection:
    def test_pii_correction_on_a_masked_word_is_check_failed_and_not_applied(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": PHONE})
        _fix(root, "a1:w0002", "808", "ochocientos")
        capsys.readouterr()
        assert _pack(root) == 1
        err = capsys.readouterr().err
        assert (
            "la palabra a1:w0002 está enmascarada por privacidad; no se corrige desde aquí" in err
        )
        assert "808" not in err and "3211" not in err  # the message never shows the raw text
        assert not (root / "edit" / "transcripcion.md").exists()

    def test_pii_correction_message_in_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": PHONE})
        _fix(root, "a1:w0003", "3211", "x")
        capsys.readouterr()
        assert _pack(root, "--json") == 1
        error = json.loads(capsys.readouterr().out)["error"]
        assert (error["exit_code"], error["kind"]) == (1, "CheckFailed")
        assert error["message"].startswith("la palabra a1:w0003 está enmascarada")

    def test_pii_correction_on_a_word_that_is_not_masked_still_applies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": PHONE})
        _fix(root, "a1:w0000", "llama", "llámame")
        assert _pack(root) == 0
        assert "llámame ***? *** **11" in "\n".join(_md(root)[HEADER_LINES:])

    def test_pii_correction_with_masking_off_the_same_correction_applies(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(
            tmp_path, monkeypatch, script={"a1": PHONE}, toml="[privacy]\nmask_pii = false\n"
        )
        _fix(root, "a1:w0002", "808", "ochocientos")
        assert _pack(root) == 0
        assert "ochocientos" in "\n".join(_md(root)[HEADER_LINES:])


class TestPiiFlag:
    def test_pii_flag_comes_after_the_marks_and_before_the_vote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        member = np.concatenate([LAYOUT[:8000], LAYOUT])
        clips = [FakeClip("a1", LAYOUT), FakeClip("a2", member, slug="cam2")]
        script = {
            "a1": [*PHONE, ("heat", 5000, 5300, 0.9)],
            "a2": [("803", 600, 900, 0.9), ("hit", 4000, 4300, 0.9)],  # the other camera differs
        }
        root = _ready(tmp_path, monkeypatch, clips, script, offsets={"a2": 1000})
        _fix(root, "a1:w0005", "heat", "9728083211")  # a correction that makes PII
        assert _pack(root) == 0
        assert _row(root, "a1:w0001")[6:] == ["?P", "***", "", ""]  # doubtful and masked
        assert _row(root, "a1:w0002")[6:] == ["PV", "***", "*", ""]  # voted: variant hidden
        assert _row(root, "a1:w0005")[6:] == ["CPV", "heat", "*", "********11"]
        assert _row(root, "a1:w0000")[6:] == ["", "llama", "", ""]

    def test_pii_flag_the_markdown_has_no_extra_mark(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = _ready(tmp_path, monkeypatch, script={"a1": PHONE})
        assert _pack(root) == 0
        lines = _md(root)[HEADER_LINES:]
        assert lines[1] == "[f30-72 | 1.00-2.40] llama ***? *** **11"  # only the usual doubt mark


def _say(texts: list[str], start: int = 1000, step: int = 330) -> list[Spoken]:
    return [(t, start + i * step, start + i * step + 300, 0.9) for i, t in enumerate(texts)]


class TestPiiAltNeverLeaks:
    """001.16 point 1: the other camera's text is masked with its whole transcript around it."""

    def _pack_two(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        master: list[str],
        member: list[str],
        toml: str = "",
    ) -> Path:
        clips = [FakeClip("a1", tone(8.0)), FakeClip("a2", tone(8.0, 0.4), slug="cam2")]
        script = {"a1": _say(master), "a2": _say(member)}
        root = _ready(tmp_path, monkeypatch, clips, script, toml=toml, offsets={"a2": 0})
        assert _pack(root) == 0
        return root

    def test_alt_never_leaks_the_digits_the_master_did_not_hear(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        master = ["mi", "numero", "972", "y", "3211", "gracias"]
        member = ["mi", "numero", "972", "808", "3211", "gracias"]
        root = self._pack_two(tmp_path, monkeypatch, master, member)
        md = "\n".join(_md(root))
        tsv = (root / "edit" / "palabras.tsv").read_text(encoding="utf-8")
        assert "808" not in md and "808" not in tsv
        assert "y[≠*]" in md  # the member's word, masked inside its own number: one star
        assert _row(root, "a1:w0003")[6:] == ["V", "y", "*", ""]

    def test_alt_never_leaks_a_number_the_master_heard_as_syllables(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        syllables = ["wa", "ti", "ku", "mo", "ne", "po", "ra", "li", "so", "tu"]
        digits = ["8", "0", "9", "5", "5", "5", "1", "2", "3", "4"]
        root = self._pack_two(tmp_path, monkeypatch, ["mi", *syllables], ["mi", *digits])
        rows = [r for r in _tsv(root)[1:] if r[1] == "a1"]
        # 001.17: the master's syllables sit under the member's number, so they are masked and
        # their alternatives hidden whole (before, the last two digits of the member showed)
        assert [r[8] for r in rows[1:]] == ["*"] * 10
        md = "\n".join(_md(root))
        assert not any(f"[≠{d}]" in md for d in "80955512")

    def test_alt_never_leaks_a_word_masked_down_to_nothing_shows_a_star(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        master = ["escribe", "a", "x", "y", "z", "w", "k", "fin"]
        member = ["escribe", "a", "juan", "arroba", "gmail", "punto", "com", "fin"]
        root = self._pack_two(tmp_path, monkeypatch, master, member)
        alts = [r[8] for r in _tsv(root)[1:] if r[1] == "a1"]
        assert alts == ["", "", "*", "*", "*", "*", "*", ""]  # hidden whole: one star (001.17)
        text = "\n".join(_md(root)) + (root / "edit" / "palabras.tsv").read_text(encoding="utf-8")
        assert "juan" not in text and "gmail" not in text and "arroba" not in text

    def test_alt_never_leaks_a_number_written_in_one_word(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        master, member = ["es", "ocho", "ya"], ["es", "8095551234", "ya"]
        root = self._pack_two(tmp_path, monkeypatch, master, member)
        assert _tsv(root)[2][8] == "*"  # under the member's mask: hidden whole (001.17)

    def test_alt_never_leaks_with_masking_off_the_raw_text_is_shown(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        master = ["mi", "numero", "972", "y", "3211", "gracias"]
        member = ["mi", "numero", "972", "808", "3211", "gracias"]
        toml = "[privacy]\nmask_pii = false\n"
        root = self._pack_two(tmp_path, monkeypatch, master, member, toml=toml)
        assert _row(root, "a1:w0003")[6:] == ["V", "y", "808", ""]

    def test_alt_never_leaks_the_vote_reports_the_member_word_of_each_alternative(self) -> None:
        def word(clip: str, i: int, text: str, s: int, e: int) -> Word:
            return Word(f"{clip}:w{i:04d}", i, text, s, e, 0.9)

        master = [word("a1", 0, "casa", 1000, 2000), word("a1", 1, "mesa", 2000, 3000)]
        near = [word("a2", 0, "caza", 1000, 1600), word("a2", 1, "cosa", 1000, 1900)]
        far = [word("a3", 0, "pesa", 2000, 3000)]
        result = tally(master, [(near, 0), (far, 0)])
        assert result.alternatives == {"a1:w0000": "cosa", "a1:w0001": "pesa"}
        assert result.sources == {"a1:w0000": (0, "a2:w0001"), "a1:w0001": (1, "a3:w0000")}


class TestPiiHeadingMasked:
    """001.16 point 6: the clip's file name and the project name are text Claude reads too."""

    def test_heading_masked_text_keeps_its_spaces_and_masks_the_numbers(self) -> None:
        # 001.17: a path is read by parts (`/ _ . -`), the extension apart: 7 digits in a part
        # 001.20: the hyphens join the groups, so only the last two digits of the ID stay
        assert mask_text("Juan Perez 001-1234567-8.mp4") == "Juan Perez ***-******7-8.mp4"
        assert mask_text("  crudo/cam  a.mp4 ") == "  crudo/cam  a.mp4 "
        assert mask_text("") == ""
        assert mask_text("Casa 8095551234") == "Casa ********34"

    def test_heading_masked_in_the_title_and_in_the_clip_heading(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clips = [FakeClip("a1", LAYOUT, file="crudo/Juan Perez 001-1234567-8.mp4")]
        toml = '[project]\nname = "Casa 8095551234"\n'
        root = build_project(tmp_path / "p", clips, toml=toml, master="a1").root
        install_fake_engine(monkeypatch, {"a1": PHONE})
        assert cli.main(["transcribe", "--project", str(root)]) == 0
        assert _pack(root) == 0
        md = "\n".join(_md(root))
        assert "# Transcripcion - Casa ********34" in md
        assert "## a1 - `crudo/Juan Perez ***-******7-8.mp4`" in md  # 001.20
        assert "1234567" not in md and "8095551234" not in md

    def test_heading_masked_with_masking_off_the_names_are_as_they_are(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        clips = [FakeClip("a1", LAYOUT, file="crudo/Juan Perez 001-1234567-8.mp4")]
        toml = '[privacy]\nmask_pii = false\n[project]\nname = "Casa 8095551234"\n'
        root = build_project(tmp_path / "p", clips, toml=toml, master="a1").root
        install_fake_engine(monkeypatch, {"a1": PHONE})
        assert cli.main(["transcribe", "--project", str(root)]) == 0
        assert _pack(root) == 0
        md = "\n".join(_md(root))
        assert "# Transcripcion - Casa 8095551234" in md and "001-1234567-8.mp4" in md
