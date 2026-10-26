"""Messages that fit what the console allows (spec 001.16, point 10).

The orphan list fills the room that is left and keeps its "(y N más)", an internal error keeps the
whole path of its log, and with no log the backup traceback is cut to 300 characters.
"""

import json
from pathlib import Path

import pytest

from kcut import cli
from kcut.commands import doctor
from kcut.errors import MAX_MESSAGE
from kcut.text.corrections import MAX_NAMED, mismatch_message
from tests.unit.cli_fakes import raiser


class TestOrphanFit:
    @pytest.mark.parametrize("length", [8, 9, 12, 16, 24, 32, 40])
    def test_orphan_fit_never_passes_the_limit_and_keeps_the_count(self, length: int) -> None:
        ids = [f"a1:w{'0' * (length - 5 - len(str(n)))}{n}" for n in range(500)]
        message = mismatch_message(ids)
        named = message.count(":w")
        assert len(message) <= MAX_MESSAGE and 1 <= named <= MAX_NAMED
        assert message.endswith(f"(y {500 - named} más)")

    def test_orphan_fit_long_ids_name_fewer_than_20_but_the_tail_survives(self) -> None:
        ids = [f"a123456:w{1_000_000 + n}" for n in range(500)]  # 17 characters each
        message = mismatch_message(ids)
        named = message.count(":w")
        assert named < MAX_NAMED and message.endswith(f"(y {500 - named} más)")
        assert ids[named - 1] in message and ids[named] not in message

    def test_orphan_fit_the_room_is_filled_up_to_the_last_id_that_fits(self) -> None:
        ids = [f"a123456:w{1_000_000 + n}" for n in range(500)]
        message = mismatch_message(ids)
        named = message.count(":w")
        body = message[: message.rindex(" (y ")]
        one_more = f"{body}, {ids[named]} (y {500 - named - 1} más)"
        assert len(one_more) > MAX_MESSAGE  # the next id would have broken the limit

    def test_orphan_fit_when_everything_fits_there_is_no_tail(self) -> None:
        assert "más)" not in mismatch_message(["a1:w0001", "a1:w0002"])

    def test_orphan_fit_the_cap_of_20_still_holds_with_short_ids(self) -> None:
        message = mismatch_message([f"a1:w{n:04d}" for n in range(21)])
        assert message.endswith("(y 1 más)") and "a1:w0019" in message and "a1:w0020" not in message


class TestNologTracebackCapped:
    def test_nolog_traceback_capped_the_backup_traceback_is_cut(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cli, "create_run_log", lambda log: None)  # the log cannot be made
        said = "tel " + "8095551234 " * 60 + "FIN"
        monkeypatch.setattr(doctor, "run", raiser(RuntimeError(said)))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        err = capsys.readouterr().err
        backup = err[err.index("Traceback") : err.index("[ERROR]")]
        assert len(backup.removesuffix("\n")) <= 300 and "Traceback (most recent call" in backup
        assert said not in err  # the error quotes 60 numbers; the backup keeps a few of them

    def test_nolog_traceback_capped_to_exactly_300_characters(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.chdir(tmp_path)  # no project here
        monkeypatch.setattr(doctor, "run", raiser(RuntimeError("x" * 2000)))
        assert cli.main(["doctor", "-v"]) == 10
        err = capsys.readouterr().err
        traceback = err[err.index("Traceback") : err.index("[ERROR]")].removesuffix("\n")
        assert len(traceback) == 300 and traceback.startswith("Traceback (most recent call last)")
        assert "…\n" in traceback and traceback.rstrip().endswith("x" * 100)  # the error's end
        assert "x" * 2000 not in err


class TestInternalKeepsLogPath:
    def _message(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        log: Path,
        error: Exception,
    ) -> str:
        monkeypatch.setattr(cli, "_run_log", lambda explicit, command: log)
        monkeypatch.setattr(cli, "append_log", lambda target, text: True)  # it reached the log
        monkeypatch.setattr(doctor, "run", raiser(error))
        assert cli.main(["doctor", "--json"]) == 10
        return str(json.loads(capsys.readouterr().out)["error"]["message"])

    def test_internal_keeps_log_path_a_long_root_does_not_cut_it(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        log = Path("C:/") / "/".join(["carpeta-larga-del-proyecto"] * 14) / "doctor-1.log"
        assert len(str(log)) > MAX_MESSAGE
        message = self._message(monkeypatch, capsys, log, RuntimeError("kaboom"))
        assert message.endswith(f"Detalle técnico en {log}")
        assert message.startswith("Error interno (RuntimeError): kaboom")

    def test_internal_keeps_log_path_a_long_error_gives_way_not_the_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        log = Path("C:/proyecto con espacios/.kcut/logs/doctor-20261025-101500-4242.log")
        message = self._message(monkeypatch, capsys, log, RuntimeError("k" * 1000))
        assert message.endswith(f"Detalle técnico en {log}")
        assert len(message) == MAX_MESSAGE  # the error's text fills what the path leaves free
        assert "…" in message  # and it is the error's own text that was cut

    def test_internal_keeps_log_path_a_short_error_is_not_touched(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        log = Path("C:/p/.kcut/logs/doctor-1.log")
        message = self._message(monkeypatch, capsys, log, RuntimeError("kaboom"))
        assert message == f"Error interno (RuntimeError): kaboom. Detalle técnico en {log}"
