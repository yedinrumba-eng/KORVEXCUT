"""Gate 1, the strategy (spec S1.5a, 001.4): `si` and `sí` approve; anything doubtful does not.

The front-matter is read line by line with a strict pattern: a Unicode line separator cannot hide a
second `aprobado: si` behind an `aprobado: no`, and the answer at the least doubt is "no".
"""

from pathlib import Path

import pytest

from kcut.edl.gate import MAX_STRATEGY_BYTES, read_front_matter, strategy_approved
from kcut.errors import GateError
from kcut.project import open_project

FILE = "edit/estrategia.md"


def _project(tmp_path: Path, text: str | bytes | None) -> Path:
    root = tmp_path / "proyecto ñandú"
    (root / "edit").mkdir(parents=True, exist_ok=True)
    (root / "kcut.toml").write_text("", encoding="utf-8")
    if text is not None:
        data = text if isinstance(text, bytes) else text.encode("utf-8")
        (root / FILE).write_bytes(data)
    return root


def _approved(tmp_path: Path, text: str | bytes | None) -> bool:
    return strategy_approved(open_project(str(_project(tmp_path, text)))).approved


class TestApproval:
    @pytest.mark.parametrize("word", ["si", "sí", "Sí", "SI", "Si", " si ", "sí."])
    def test_gate_si_and_si_with_an_accent_approve(self, tmp_path: Path, word: str) -> None:
        assert _approved(tmp_path, f"---\naprobado: {word}\n---\n# x\n")

    @pytest.mark.parametrize("word", ["no", "", "nop", "siii", "yes", "sí no", "true", "1"])
    def test_gate_anything_else_does_not(self, tmp_path: Path, word: str) -> None:
        assert not _approved(tmp_path, f"---\naprobado: {word}\n---\n# x\n")

    def test_gate_the_file_that_kcut_new_writes_is_not_approved(self, tmp_path: Path) -> None:
        text = (
            "---\nvideo: demo\nformato: 9:16 · 1080x1920 · 30 fps\naprobado: no\n"
            "aprobado_por:\n---\n# Estrategia de corte - demo\n"
        )
        assert not _approved(tmp_path, text)
        assert _approved(tmp_path, text.replace("aprobado: no", "aprobado: si"))

    def test_gate_no_front_matter_or_no_file_is_not_approved(self, tmp_path: Path) -> None:
        assert not _approved(tmp_path, "aprobado: si\n")
        assert not _approved(tmp_path, "# Estrategia\n\naprobado: si\n")
        assert not _approved(tmp_path / "otro", None)
        assert not _approved(tmp_path / "vacio", "")

    def test_gate_the_status_says_why_and_which_file(self, tmp_path: Path) -> None:
        missing = strategy_approved(open_project(str(_project(tmp_path / "a", None))))
        assert (missing.approved, missing.file) == (False, FILE) and "falta" in missing.reason_es
        no = strategy_approved(
            open_project(str(_project(tmp_path / "b", "---\naprobado: no\n---\n")))
        )
        assert not no.approved and "aprobado: 'no'" in no.reason_es
        yes = strategy_approved(
            open_project(str(_project(tmp_path / "c", "---\naprobado: si\n---\n")))
        )
        assert yes.approved and yes.reason_es

    def test_gate_without_the_key_is_not_approved(self, tmp_path: Path) -> None:
        assert not _approved(tmp_path, "---\nvideo: x\n---\n")

    def test_gate_crlf_files_work(self, tmp_path: Path) -> None:
        assert _approved(tmp_path, "---\r\naprobado: si\r\naprobado_por: yo\r\n---\r\n# x\r\n")

    def test_gate_the_rest_of_the_document_is_not_read_as_front_matter(
        self, tmp_path: Path
    ) -> None:
        assert not _approved(tmp_path, "---\naprobado: no\n---\naprobado: si\n")
        assert _approved(tmp_path, "---\naprobado: si\n---\naprobado: no\n")


class TestInjection:
    """Row 6 of S1.5a (001.4): a trick in the front-matter closes the gate."""

    @pytest.mark.parametrize("separator", [" ", " ", "\u0085"])
    def test_gate_injection_a_line_separator_does_not_hide_a_second_aprobado(
        self, tmp_path: Path, separator: str
    ) -> None:
        text = f"---\naprobado: no{separator}aprobado: si\n---\n# x\n"
        assert not _approved(tmp_path, text)

    @pytest.mark.parametrize("separator", [" ", " ", "\u0085"])
    def test_gate_injection_the_separator_in_front_of_a_value_that_would_approve(
        self, tmp_path: Path, separator: str
    ) -> None:
        assert not _approved(tmp_path, f"---\naprobado: si{separator}\n---\n")
        assert not _approved(tmp_path, f"---\nvideo: x{separator}aprobado: si\n---\n")

    def test_gate_injection_aprobado_twice_is_not_approved_whatever_the_order(
        self, tmp_path: Path
    ) -> None:
        assert not _approved(tmp_path, "---\naprobado: no\naprobado: si\n---\n")
        assert not _approved(tmp_path, "---\naprobado: si\naprobado: no\n---\n")
        assert not _approved(tmp_path, "---\naprobado: si\naprobado: si\n---\n")

    @pytest.mark.parametrize(
        "line",
        [
            "aprobado = si",
            "aprobado si",
            ": si",
            "1aprobado: si",
            "aprobado : si",
            " aprobado: si",
            "- aprobado: si",
            "",
            "# aprobado: no",
            "aprobado: si​",
            "aprobado: s​i",
            "aprobado: si\x07",
            "aprobado: s\ti",
        ],
    )
    def test_gate_injection_a_line_that_is_not_key_colon_value_closes_the_gate(
        self, tmp_path: Path, line: str
    ) -> None:
        assert not _approved(tmp_path, f"---\naprobado: si\n{line}\n---\n")

    def test_gate_injection_a_single_bad_line_alone_is_not_approval_either(
        self, tmp_path: Path
    ) -> None:
        assert not _approved(tmp_path, "---\naprobado = si\n---\n")

    def test_gate_injection_the_front_matter_has_to_open_and_close(self, tmp_path: Path) -> None:
        assert not _approved(tmp_path, "---\naprobado: si\n")
        assert not _approved(tmp_path, "\n---\naprobado: si\n---\n")
        assert not _approved(tmp_path, "--- \naprobado: si\n---\n")
        assert not _approved(tmp_path, "﻿---\naprobado: si\n---\n")  # a BOM is a doubt

    def test_gate_injection_text_that_is_not_utf8_or_too_big_is_not_approved(
        self, tmp_path: Path
    ) -> None:
        assert not _approved(tmp_path, b"---\naprobado: si\n\xff\xfe\n---\n")
        big = b"---\naprobado: si\n---\n" + b"x" * MAX_STRATEGY_BYTES
        assert not _approved(tmp_path / "grande", big)

    def test_gate_injection_a_very_long_line_is_refused_quickly(self, tmp_path: Path) -> None:
        assert not _approved(tmp_path, "---\naprobado: si\nnota: " + " x" * 20000 + "\n---\n")

    def test_gate_injection_a_folder_where_the_file_goes_is_not_approved(
        self, tmp_path: Path
    ) -> None:
        root = _project(tmp_path, None)
        (root / FILE).mkdir()
        assert not strategy_approved(open_project(str(root))).approved


class TestReadFrontMatter:
    def test_gate_front_matter_pairs(self) -> None:
        text = "---\nvideo: Mi video\nnota:  con  espacios  \nvacio:\n---\ncuerpo: no\n"
        assert read_front_matter(text) == {
            "video": "Mi video",
            "nota": "con  espacios",
            "vacio": "",
        }

    def test_gate_front_matter_the_value_keeps_its_colons(self) -> None:
        assert read_front_matter("---\nformato: 9:16 · 1080x1920\n---\n") == {
            "formato": "9:16 · 1080x1920"
        }

    def test_gate_front_matter_the_last_of_a_repeated_key_wins_except_aprobado(self) -> None:
        assert read_front_matter("---\na: 1\na: 2\n---\n") == {"a": "2"}
        with pytest.raises(GateError, match="más de una vez"):
            read_front_matter("---\naprobado: no\naprobado: no\n---\n")

    def test_gate_front_matter_splits_only_at_newlines_not_at_unicode_separators(self) -> None:
        with pytest.raises(GateError, match="caracteres de control"):
            read_front_matter("---\nvideo: a b: c\n---\n")
        with pytest.raises(GateError, match="caracteres de control"):
            read_front_matter("---\nvideo: a\u0085b\n---\n")

    def test_gate_front_matter_errors_say_which_line(self) -> None:
        with pytest.raises(GateError, match="línea 3"):
            read_front_matter("---\nvideo: a\nroto\n---\n")
        with pytest.raises(GateError, match="no empieza"):
            read_front_matter("hola\n---\n")
        with pytest.raises(GateError, match="no cierra"):
            read_front_matter("---\na: b\n")

    def test_gate_front_matter_a_carriage_return_in_the_middle_is_a_control_character(self) -> None:
        with pytest.raises(GateError, match="caracteres de control"):
            read_front_matter("---\nvideo: a\rb\n---\n")
