"""InternalError: full traceback to the project log, never to --json, stderr only with -v."""

import argparse
import json
import os
from pathlib import Path

import pytest

from kcut import cli, errors, proc
from kcut.commands import doctor
from tests.unit.cli_fakes import LOG_NAME
from tests.unit.cli_fakes import base_python as _python
from tests.unit.cli_fakes import logs_of as _logs
from tests.unit.cli_fakes import raiser as _raiser


class TestInsideAProject:
    def test_traceback_goes_to_the_log_and_not_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        captured = capsys.readouterr()
        assert "Traceback" not in captured.err
        assert "Traceback" not in captured.out
        (log,) = _logs(project)
        assert LOG_NAME.match(log.name)
        text = log.read_text(encoding="utf-8")
        assert "Traceback (most recent call last)" in text
        assert "RuntimeError: kaboom" in text
        assert str(log) in captured.err
        assert "kaboom" in captured.err

    def test_verbose_does_not_change_where_the_traceback_goes(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "--project", str(project), "-v"]) == 10
        assert "Traceback" not in capsys.readouterr().err
        assert len(_logs(project)) == 1

    def test_json_has_the_short_message_and_never_the_traceback(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "--json", "--project", str(project)]) == 10
        captured = capsys.readouterr()
        error = json.loads(captured.out)["error"]
        assert (error["exit_code"], error["kind"]) == (10, "InternalError")
        assert "kaboom" in error["message"]
        assert str(_logs(project)[0]) in error["message"]
        assert "Traceback" not in captured.out
        assert "Traceback" not in captured.err
        assert "File " not in captured.out

    def test_the_project_is_found_by_climbing_from_the_cwd(
        self, monkeypatch: pytest.MonkeyPatch, project: Path
    ) -> None:
        deep = project / "crudo" / "sub"
        deep.mkdir(parents=True)
        monkeypatch.chdir(deep)
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor"]) == 10
        assert len(_logs(project)) == 1

    def test_an_explicit_internal_error_is_treated_the_same_way(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(errors.InternalError("invariante rota")))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        err = capsys.readouterr().err
        assert "invariante rota" in err
        assert "Traceback" not in err
        assert "InternalError: invariante rota" in _logs(project)[0].read_text(encoding="utf-8")

    def test_other_errors_leave_no_traceback_in_the_log(
        self, monkeypatch: pytest.MonkeyPatch, project: Path
    ) -> None:
        def run(args: argparse.Namespace) -> int:
            assert args.log is not None and args.log.is_file()  # `main` reserved it, still empty
            assert args.log.stat().st_size == 0
            raise errors.ProjectError("falta algo")

        monkeypatch.setattr(doctor, "run", run)
        assert cli.main(["doctor", "--project", str(project)]) == 3
        assert _logs(project) == []  # 001.7: no traceback was written, so the empty log is gone

    def test_location_and_device_data_are_scrubbed_from_the_log(
        self, monkeypatch: pytest.MonkeyPatch, project: Path
    ) -> None:
        leak = RuntimeError(
            "ffmpeg dijo +18.4861-069.9312/ y\n    com.apple.quicktime.model: iPhone15"
        )
        monkeypatch.setattr(doctor, "run", _raiser(leak))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        text = _logs(project)[0].read_text(encoding="utf-8")
        assert "18.4861" not in text
        assert "iPhone15" not in text
        assert "RuntimeError" in text

    def test_a_failure_before_the_command_runs_still_reaches_the_log(
        self, monkeypatch: pytest.MonkeyPatch, project: Path
    ) -> None:
        monkeypatch.setattr(cli, "COMMAND_MODULES", ("kcut.commands.no_existe",))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        (log,) = _logs(project)
        assert log.name.startswith("kcut-")
        assert "ModuleNotFoundError" in log.read_text(encoding="utf-8")

    @pytest.mark.parametrize("log_ok", [True, False])
    def test_detail_hint_only_when_the_traceback_reached_the_log(
        self,
        monkeypatch: pytest.MonkeyPatch,
        project: Path,
        capsys: pytest.CaptureFixture[str],
        log_ok: bool,
    ) -> None:
        def run(args: argparse.Namespace) -> int:
            if not log_ok:  # the log stops being a regular file: the append falls back to stderr
                args.log.unlink()
                args.log.mkdir()
            raise RuntimeError("kaboom")

        monkeypatch.setattr(doctor, "run", run)
        assert cli.main(["doctor", "--json", "--project", str(project)]) == 10
        captured = capsys.readouterr()
        assert ("Detalle técnico en" in json.loads(captured.out)["error"]["message"]) is log_ok
        assert ("Traceback" in captured.err) is not log_ok

    def test_unwritable_log_falls_back_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (project / ".kcut").write_text("soy un archivo, no una carpeta", encoding="utf-8")
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        assert "Traceback" in capsys.readouterr().err


class TestOutsideAProject:
    def test_traceback_is_not_printed_without_verbose(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor"]) == 10
        err = capsys.readouterr().err
        assert "Traceback" not in err
        assert "kaboom" in err
        assert "-v" in err
        assert not (lonely / ".kcut").exists()

    def test_verbose_prints_the_traceback_to_stderr(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "-v"]) == 10
        assert "Traceback (most recent call last)" in capsys.readouterr().err
        assert not (lonely / ".kcut").exists()

    def test_json_never_carries_the_traceback_even_with_verbose(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "--json", "-v"]) == 10
        captured = capsys.readouterr()
        doc = json.loads(captured.out)
        assert doc["ok"] is False
        assert "Traceback" not in captured.out
        assert "Traceback (most recent call last)" in captured.err

    def test_json_without_verbose_has_no_traceback_anywhere(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "--json"]) == 10
        captured = capsys.readouterr()
        assert "Traceback" not in captured.out + captured.err

    def test_an_explicit_folder_that_is_not_a_project_counts_as_no_project(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(RuntimeError("kaboom")))
        assert cli.main(["doctor", "--project", str(lonely)]) == 10
        assert "Traceback" not in capsys.readouterr().err
        assert not (lonely / ".kcut").exists()


class TestSameLog:
    def test_traceback_is_appended_to_the_same_log_the_children_wrote(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        seen: list[Path | None] = []

        def run(args: argparse.Namespace) -> int:
            seen.append(args.log)
            code = "import sys; sys.stderr.write('linea-del-hijo\\n')"
            proc.run([_python(), "-c", code], log=args.log)
            raise RuntimeError("kaboom")

        monkeypatch.setattr(doctor, "run", run)
        assert cli.main(["doctor", "--project", str(project)]) == 10
        (log,) = _logs(project)
        assert seen == [log]
        text = log.read_text(encoding="utf-8")
        assert text.startswith("$ ")
        assert "linea-del-hijo" in text
        assert "[exit 0" in text
        assert text.index("linea-del-hijo") < text.index("Traceback (most recent call last)")
        assert "RuntimeError: kaboom" in text
        assert str(log) in capsys.readouterr().err

    def test_one_log_path_is_chosen_per_invocation(
        self, monkeypatch: pytest.MonkeyPatch, project: Path
    ) -> None:
        paths: list[Path | None] = []

        def run(args: argparse.Namespace) -> int:
            paths.extend([args.log, args.log])
            assert args.log.is_file() and args.log.stat().st_size == 0  # created, exclusive, empty
            return 0

        monkeypatch.setattr(doctor, "run", run)
        assert cli.main(["doctor", "--project", str(project)]) == 0
        assert paths[0] is not None and paths[0] == paths[1]
        assert LOG_NAME.match(paths[0].name) and paths[0].name.endswith(f"-{os.getpid()}.log")
        assert not paths[0].exists()  # 001.7: left empty, removed when the run ends

    def test_the_log_is_none_without_a_project(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path
    ) -> None:
        paths: list[Path | None] = []

        def run(args: argparse.Namespace) -> int:
            paths.append(args.log)
            return 0

        monkeypatch.setattr(doctor, "run", run)
        assert cli.main(["doctor"]) == 0
        assert paths == [None]

    def test_an_existing_log_is_never_truncated(
        self, monkeypatch: pytest.MonkeyPatch, project: Path
    ) -> None:
        def run(args: argparse.Namespace) -> int:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            args.log.write_text("lo que ya habia\n", encoding="utf-8")
            raise RuntimeError("kaboom")

        monkeypatch.setattr(doctor, "run", run)
        assert cli.main(["doctor", "--project", str(project)]) == 10
        text = _logs(project)[0].read_text(encoding="utf-8")
        assert text.startswith("lo que ya habia\n")
        assert "Traceback (most recent call last)" in text


class TestScrubbedMessage:
    def test_the_short_message_is_scrubbed_of_coordinates_in_stderr(
        self, monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            doctor, "run", _raiser(RuntimeError("ffmpeg dijo +18.4861-069.9312/ ok"))
        )
        assert cli.main(["doctor", "--project", str(project)]) == 10
        err = capsys.readouterr().err
        assert "18.4861" not in err
        assert "[ubicacion omitida]" in err
        assert "RuntimeError" in err

    def test_the_short_message_is_scrubbed_in_the_json_document(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        leak = errors.InternalError(
            "fallo en +18.4861-069.9312/\n    com.apple.quicktime.model: iPhone15\nfin"
        )
        monkeypatch.setattr(doctor, "run", _raiser(leak))
        assert cli.main(["doctor", "--json"]) == 10
        out = capsys.readouterr().out
        message = json.loads(out)["error"]["message"]
        assert "18.4861" not in message
        assert "iPhone15" not in message
        assert "fallo en" in message

    def test_a_message_that_scrubs_to_nothing_still_says_something(
        self, monkeypatch: pytest.MonkeyPatch, lonely: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", _raiser(errors.InternalError("location: secreto")))
        assert cli.main(["doctor", "--json"]) == 10
        message = json.loads(capsys.readouterr().out)["error"]["message"]
        assert message.strip()
        assert "secreto" not in message
