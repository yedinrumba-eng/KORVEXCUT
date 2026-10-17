"""Console hygiene (spec 001.8, point 1): untrusted text never reaches the terminal raw."""

import json
import unicodedata
from pathlib import Path

import pytest

from kcut import cli, console
from kcut.commands import doctor
from kcut.errors import ProjectError
from tests.unit.cli_fakes import raiser

_ESCAPED_CATEGORIES = {"Cc", "Cf", "Zl", "Zp", "Cs"}
_TITLE = "\x1b]0;pwned\x07\x1b[2J"
_TITLE_SAFE = "\\x1b]0;pwned\\x07\\x1b[2J"


class TestSafeText:
    @pytest.mark.parametrize(
        ("raw", "safe"),
        [
            ("\x1b", "\\x1b"),
            ("\x07", "\\x07"),
            ("\x7f", "\\x7f"),
            ("\x00", "\\x00"),
            ("\r", "\\x0d"),
            ("\t", "\\x09"),
            ("\x85", "\\x85"),
            ("\x9b", "\\x9b"),
            ("\xad", "\\xad"),
            ("\u200b", "\\u200b"),
            ("\u202e", "\\u202e"),
            ("\u2028", "\\u2028"),
            ("\u2029", "\\u2029"),
            ("\ufeff", "\\ufeff"),
            ("\ud800", "\\ud800"),
            ("\U000e0001", "\\U000e0001"),
        ],
    )
    def test_safe_text_swaps_each_character_for_its_visible_escape(
        self, raw: str, safe: str
    ) -> None:
        assert console.safe_text(f"a{raw}b") == f"a{safe}b"

    def test_safe_text_defangs_a_terminal_title_and_clear_screen(self) -> None:
        assert console.safe_text(_TITLE) == _TITLE_SAFE

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "ñandú áéíóú üÜ ¿qué? ¡hola!",
            "emoji 😀 🎬",
            "日本語 العربية",
            "linea 1\nlinea 2\n",
            "[OK] a1: video_voz - crudo/cam a.mp4 - 12.5 s",
            "ruta C:\\Users\\Yedin\\proyecto ñandú\\crudo",
        ],
    )
    def test_safe_text_leaves_clean_text_byte_identical(self, text: str) -> None:
        assert console.safe_text(text) == text

    def test_safe_text_keeps_the_newline_but_not_the_carriage_return(self) -> None:
        assert console.safe_text("a\r\nb\n") == "a\\x0d\nb\n"

    def test_safe_text_leaves_no_escaped_category_in_the_output(self) -> None:
        sweep = "".join(chr(c) for c in (*range(0x20000), *range(0xE0000, 0xE1000)))
        out = console.safe_text(sweep)
        left = {c for c in out if unicodedata.category(c) in _ESCAPED_CATEGORIES}
        assert left <= {"\n"}
        assert console.safe_text(out) == out  # applying it twice changes nothing


class TestOut:
    def test_console_hygiene_line_goes_through_the_sink(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        console.Out(json_mode=False).line("INFO", "sincronía: maestro a1 (ñandú)")  # clean: same
        console.Out(json_mode=False).line("OK", f"a1: {_TITLE}")
        captured = capsys.readouterr()
        assert captured.out == f"[INFO] sincronía: maestro a1 (ñandú)\n[OK] a1: {_TITLE_SAFE}\n"
        assert captured.err == ""

    def test_console_hygiene_warn_goes_through_the_sink(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        console.Out(json_mode=False).warn("a2: hdr — ñ")  # clean: same
        console.Out(json_mode=False).warn(f"cache_rebuilt: {_TITLE}")
        captured = capsys.readouterr()
        assert captured.err == f"[AVISO] a2: hdr — ñ\n[AVISO] cache_rebuilt: {_TITLE_SAFE}\n"
        assert captured.out == ""

    def test_console_hygiene_json_escapes_every_key_and_value(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        document = {
            f"k{_TITLE}": [f"\x9b{_TITLE}", {"n": "ñ\u202e"}, ("t\x7f", 3)],
            "plain": {"ok": True, "none": None, "n": 7, "f": 1.5, "name": "ñandú\nlínea"},
        }
        console.Out(json_mode=True).result(document)
        out = capsys.readouterr().out
        assert not [c for c in out if c in "\x1b\x07\x7f\u202e" or "\x80" <= c <= "\x9f"]
        assert '"name": "ñandú\\nlínea"' in out and "\\u00f1" not in out  # accents stay as typed
        assert json.loads(out) == {
            f"k{_TITLE_SAFE}": [f"\\x9b{_TITLE_SAFE}", {"n": "ñ\\u202e"}, ["t\\x7f", 3]],
            "plain": {"ok": True, "none": None, "n": 7, "f": 1.5, "name": "ñandú\nlínea"},
        }

    def test_console_hygiene_progress_line_goes_through_the_sink(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        progress = console.Progress(f"ingest{_TITLE}", 2, "pasos")
        progress.update(1)
        progress.close()
        err = capsys.readouterr().err
        assert err.startswith(f"ingest{_TITLE_SAFE}: 1/2 pasos (50%)")
        assert "\x1b" not in err and "\x07" not in err


class TestCli:
    def test_console_hygiene_human_error_message(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", raiser(ProjectError(f"clips[d1{_TITLE}] mal")))
        assert cli.main(["doctor"]) == 3
        assert capsys.readouterr().err == f"[ERROR] clips[d1{_TITLE_SAFE}] mal\n"

    def test_console_hygiene_json_error_message(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", raiser(ProjectError(f"clave {_TITLE} \x9b mal")))
        assert cli.main(["doctor", "--json"]) == 3
        out = capsys.readouterr().out
        assert "\x1b" not in out and "\x9b" not in out and "\x07" not in out
        assert json.loads(out)["error"]["message"] == f"clave {_TITLE_SAFE} \\x9b mal"

    def test_console_hygiene_traceback_printed_with_verbose(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", raiser(RuntimeError(f"kaboom {_TITLE}")))
        assert cli.main(["doctor", "-v"]) == 10
        err = capsys.readouterr().err
        assert "Traceback (most recent call last)" in err
        assert f"RuntimeError: kaboom {_TITLE_SAFE}" in err
        assert "\x1b" not in err and "\x07" not in err

    def test_console_hygiene_system_exit_text(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", raiser(SystemExit(f"adiós {_TITLE}")))
        assert cli.main(["doctor"]) == 1
        assert capsys.readouterr().err == f"adiós {_TITLE_SAFE}\n"

    def test_console_hygiene_log_creation_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        folder = tmp_path / "proy\u202eecto\x9b"  # a folder name may hold these on Windows
        folder.mkdir()
        (folder / "kcut.toml").write_text("", encoding="utf-8")
        monkeypatch.setattr(cli, "create_run_log", lambda _path: None)
        monkeypatch.setattr(doctor, "run", lambda _args: 0)
        assert cli.main(["doctor", "--project", str(folder)]) == 0
        err = capsys.readouterr().err
        assert "no pude crear el log" in err
        assert "\u202e" not in err and "\x9b" not in err
        assert "proy\\u202eecto\\x9b" in err

    def test_console_hygiene_the_log_on_disk_keeps_the_raw_text(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", raiser(RuntimeError(f"kaboom {_TITLE}")))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        err = capsys.readouterr().err
        assert "\x1b" not in err and "\x07" not in err
        assert f"kaboom {_TITLE_SAFE}" in err
        (log,) = (project / ".kcut" / "logs").glob("*.log")
        assert f"RuntimeError: kaboom {_TITLE}" in log.read_text(encoding="utf-8")  # untouched
