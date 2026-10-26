"""Console hygiene through `cli.main`: error messages, tracebacks and the log warning."""

import json
from pathlib import Path

import pytest

from kcut import cli
from kcut.commands import doctor
from kcut.errors import ProjectError
from tests.unit.cli_fakes import raiser
from tests.unit.test_console_hygiene import _TITLE, _TITLE_SAFE


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
