"""CLI: version, exit codes (spec 0.5), JSON error documents, console helpers."""

import argparse
import json
from collections.abc import Callable

import pytest

from kcut import __version__, cli, errors
from kcut.commands import doctor
from kcut.console import Out, Progress
from tests.conftest import run_kcut


def _raiser(exc: BaseException) -> Callable[[argparse.Namespace], int]:
    def run(_args: argparse.Namespace) -> int:
        raise exc

    return run


class TestVersion:
    def test_in_process(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["--version"]) == 0
        assert capsys.readouterr().out == f"kcut {__version__}\n"

    def test_as_python_module(self) -> None:
        result = run_kcut("--version")
        assert result.returncode == 0
        assert result.stdout.strip() == "kcut 0.1.0"


class TestUsageErrors:
    def test_unknown_subcommand_exits_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["no-existe"]) == 2
        assert "[ERROR]" in capsys.readouterr().err

    def test_missing_subcommand_exits_2(self) -> None:
        assert cli.main([]) == 2

    def test_unknown_option_exits_2(self) -> None:
        assert cli.main(["doctor", "--no-existe"]) == 2

    def test_json_mode_prints_one_json_error_document(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert cli.main(["--json", "no-existe"]) == 2
        doc = json.loads(capsys.readouterr().out)
        assert doc["ok"] is False
        assert doc["error"]["exit_code"] == 2
        assert doc["error"]["kind"] == "UsageError"

    def test_exit_code_of_the_real_process(self) -> None:
        assert run_kcut("no-existe").returncode == 2

    def test_common_options_come_after_the_subcommand(self) -> None:
        args = cli._build_parser().parse_args(["doctor", "--json", "--project", "x", "-v"])
        assert (args.json, args.project, args.verbose) == (True, "x", True)


class TestErrorMapping:
    def test_project_error_exits_3_with_json_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        boom = errors.ProjectError("no encuentro kcut.toml")
        monkeypatch.setattr(doctor, "run", _raiser(boom))
        assert cli.main(["doctor", "--json"]) == 3
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {
            "ok": False,
            "error": {"exit_code": 3, "kind": "ProjectError", "message": "no encuentro kcut.toml"},
        }
        assert captured.err == ""

    def test_human_mode_prints_error_line_on_stderr(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(errors.ProjectError("falta kcut.toml")))
        assert cli.main(["doctor"]) == 3
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "[ERROR] falta kcut.toml\n"

    @pytest.mark.parametrize(
        ("exc_type", "code"),
        [
            (errors.CheckFailed, 1),
            (errors.UsageError, 2),
            (errors.ProjectError, 3),
            (errors.ToolError, 4),
            (errors.GateError, 5),
            (errors.LockedError, 6),
            (errors.MissingDependency, 7),
            (errors.InternalError, 10),
        ],
    )
    def test_each_error_class_maps_to_its_exit_code(
        self, monkeypatch: pytest.MonkeyPatch, exc_type: type[errors.KcutError], code: int
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(exc_type("mensaje")))
        assert exc_type.exit_code == code
        assert cli.main(["doctor"]) == code

    def test_unexpected_exception_exits_10_with_json(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "--json"]) == 10
        error = json.loads(capsys.readouterr().out)["error"]
        assert error["kind"] == "InternalError"
        assert "kaboom" in error["message"]

    def test_verbose_prints_the_traceback_for_unexpected_exceptions(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "-v"]) == 10
        assert "Traceback" in capsys.readouterr().err

    def test_ctrl_c_exits_130(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(KeyboardInterrupt()))
        assert cli.main(["doctor"]) == 130

    def test_message_is_kept_on_the_exception(self) -> None:
        exc = errors.GateError("estrategia sin aprobar")
        assert exc.message_es == "estrategia sin aprobar"
        assert isinstance(exc, errors.KcutError)


class TestConsole:
    def test_line_is_silent_in_json_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        Out(json_mode=True).line("OK", "hola")
        assert capsys.readouterr().out == ""

    def test_line_prefix_in_human_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        Out(json_mode=False).line("FALTA", "ffmpeg")
        assert capsys.readouterr().out == "[FALTA] ffmpeg\n"

    def test_unknown_tag_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            Out(json_mode=False).line("WAT", "x")

    def test_result_prints_one_utf8_document_in_json_mode(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        Out(json_mode=True).result({"ok": True, "nombre": "ñandú"})
        out = capsys.readouterr().out
        assert json.loads(out) == {"ok": True, "nombre": "ñandú"}
        assert "ñandú" in out

    def test_result_is_silent_in_human_mode(self, capsys: pytest.CaptureFixture[str]) -> None:
        Out(json_mode=False).result({"ok": True})
        assert capsys.readouterr().out == ""

    def test_warn_goes_to_stderr_in_both_modes(self, capsys: pytest.CaptureFixture[str]) -> None:
        Out(json_mode=True).warn("cuidado")
        Out(json_mode=False).warn("cuidado")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "[AVISO] cuidado\n[AVISO] cuidado\n"

    def test_progress_prints_at_most_every_two_seconds(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        now = [100.0]
        monkeypatch.setattr("time.monotonic", lambda: now[0])
        progress = Progress("render v1", 1469, "frames")
        now[0] = 101.0
        progress.update(100)
        assert capsys.readouterr().err == ""
        now[0] = 135.2
        progress.update(640)
        line = capsys.readouterr().err
        assert line.startswith("render v1: 640/1469 frames (43%) - ")
        assert "fps" in line
        assert "faltan" in line
        now[0] = 136.0
        progress.update(700)
        assert capsys.readouterr().err == ""
        progress.close()
        assert "700/1469" in capsys.readouterr().err
