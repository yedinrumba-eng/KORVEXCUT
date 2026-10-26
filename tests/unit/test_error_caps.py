"""Untrusted text in error messages is capped (spec 001.14, point 7).

Every untrusted value a message quotes is cut to 40 characters, and as a second wall `cli` cuts
the `message` of every error to 300 characters, in the human line and in `--json`. The complete
text stays in the log.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.commands import doctor
from kcut.config.load import parse_config
from kcut.errors import InternalError, ProjectError
from kcut.ingest.inventory import InventoryInvalid, load_inventory
from kcut.paths import resolve_in_project
from kcut.recursos.manifest import load_manifest
from kcut.schema_util import SchemaError, describe_value
from kcut.text.corrections import mismatch_message, parse_corrections
from kcut.transcribe.document import from_document
from tests.unit.cli_fakes import raiser
from tests.unit.inventory_fakes import written
from tests.unit.transcribe_fakes import FakeClip, build_project, tone

BIG = "S" * 5000


def _message(call: Any) -> str:
    with pytest.raises(ProjectError) as info:
        call()
    return info.value.message_es


class TestValueEchoCapped:
    def test_value_echo_capped_the_helper_cuts_at_40_characters(self) -> None:
        assert describe_value("hola") == "'hola'"
        shown = describe_value(BIG)
        assert len(shown) == 40 and shown.endswith("...") and shown.startswith("'SSS")
        assert describe_value("x" * 38) == repr("x" * 38)  # 40 characters fit exactly

    def test_value_echo_capped_schema_of_correcciones(self) -> None:
        message = _message(lambda: parse_corrections({"schema": BIG, "items": []}))
        assert "S" * 41 not in message and len(message) < 120

    def test_value_echo_capped_schema_of_the_inventory(self, tmp_path: Path) -> None:
        path = written(tmp_path / "p", lambda d: d.update(schema=BIG))
        with pytest.raises(InventoryInvalid) as info:
            load_inventory(path, tmp_path / "p")
        assert "S" * 41 not in info.value.message_es

    def test_value_echo_capped_schema_of_a_transcript(self) -> None:
        with pytest.raises(SchemaError) as info:
            from_document({"schema": BIG}, "a1", "k" * 64)
        assert "S" * 41 not in info.value.message_es

    def test_value_echo_capped_schema_of_the_manifest(self, tmp_path: Path) -> None:
        project = build_project(tmp_path / "p", [FakeClip("a1", tone(1.0))])
        project.layout.manifest.parent.mkdir(parents=True, exist_ok=True)
        project.layout.manifest.write_text(
            json.dumps({"schema": BIG, "items": []}), encoding="utf-8"
        )
        message = _message(lambda: load_manifest(project))
        assert "S" * 41 not in message

    @pytest.mark.parametrize(
        ("toml", "path"),
        [
            (f'[project]\nlanguage = "{BIG}"\n', "project.language"),
            (f'[project]\ncreated = "{BIG}"\n', "project.created"),
            (f'[sync]\nmaster = "{BIG}"\n', "sync.master"),
            (f'[sync.manual]\na2 = "{BIG}"\n', "sync.manual.a2"),
            (f"[transcribe]\nfillers = [[{', '.join(['1'] * 3000)}]]\n", "transcribe.fillers[0]"),
        ],
        ids=["language", "created", "master", "manual", "list_item"],
    )
    def test_value_echo_capped_in_kcut_toml(self, toml: str, path: str) -> None:
        message = _message(lambda: parse_config(toml, default_name="x"))
        assert path in message and "S" * 41 not in message and len(message) < 250

    def test_value_echo_capped_in_a_path_error(self, tmp_path: Path) -> None:
        message = _message(lambda: resolve_in_project(tmp_path, "C:" + BIG))
        assert "S" * 41 not in message


class TestErrorMessageCapped:
    def _run(self, root: Path, error: Exception, *flags: str) -> int:
        from unittest import mock

        with mock.patch.object(doctor, "run", raiser(error)):
            return cli.main(["doctor", "--project", str(root), *flags])

    def test_error_message_capped_human(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(project, ProjectError("x" * 1000)) == 3
        line = capsys.readouterr().err.strip()
        message = line.removeprefix("[ERROR] ")
        assert len(message) == 300 and message == "x" * 299 + "…"

    def test_error_message_capped_json(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(project, ProjectError("y" * 1000), "--json") == 3
        message = json.loads(capsys.readouterr().out)["error"]["message"]
        assert len(message) == 300 and message.endswith("…")

    def test_error_message_capped_a_short_message_is_untouched(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        text = "z" * 300
        assert self._run(project, ProjectError(text)) == 3
        assert capsys.readouterr().err.strip() == "[ERROR] " + text

    def test_error_message_capped_the_whole_text_goes_to_the_log(self, project: Path) -> None:
        assert self._run(project, ProjectError("w" * 1000 + "FIN")) == 3
        (log,) = (project / ".kcut" / "logs").glob("*.log")
        assert "w" * 1000 + "FIN" in log.read_text(encoding="utf-8")

    def test_error_message_capped_an_internal_error_too(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(project, RuntimeError("q" * 1000), "--json") == 10
        message = json.loads(capsys.readouterr().out)["error"]["message"]
        (log,) = (project / ".kcut" / "logs").glob("*.log")
        suffix = f". Detalle técnico en {log}"
        # 300 characters, unless the path of the log alone is longer: it is kept whole (001.16),
        # and the error's own text keeps 120 characters at least (001.17)
        assert message.endswith(suffix) and len(message) <= max(300, 120 + len(suffix))
        assert "q" * 1000 in log.read_text(encoding="utf-8")  # the traceback keeps everything

    def test_error_message_capped_the_cut_is_on_characters_not_escapes(
        self, project: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert self._run(project, ProjectError("\x1b" * 1000)) == 3
        line = capsys.readouterr().err
        assert "\x1b" not in line and len(line) < 3000

    def test_error_message_capped_the_orphan_list_fits_whole_with_its_tail(self) -> None:
        """20 ids and `(y N más)` are what the user needs: the cut must not eat the tail."""
        message = mismatch_message([f"a1:w{10_000 + i:05d}" for i in range(50_000)])
        assert len(message) <= 300 and message.endswith("(y 49980 más)")
        assert "a1:w10019" in message and "a1:w10020" not in message

    def test_error_message_capped_internal_error_class_is_unchanged(self) -> None:
        assert InternalError("x").exit_code == 10


class TestErrorCleanedWhole:
    """001.17 point 1: the text of an internal error is cleaned WHOLE (media metadata, PII) and only
    then cut, so no cut can leave half of a coordinate or of a number that nothing recognizes."""

    COORDINATES = "+18.4861-069.9312/"
    PHONE = "8095551234"

    def _message(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        log: Path,
        said: str,
    ) -> str:
        monkeypatch.setattr(cli, "_run_log", lambda explicit, command: log)
        monkeypatch.setattr(cli, "append_log", lambda target, text: True)  # it reached the log
        monkeypatch.setattr(doctor, "run", raiser(RuntimeError(said)))
        assert cli.main(["doctor", "--json"]) == 10
        return str(json.loads(capsys.readouterr().out)["error"]["message"])

    def test_error_message_long_root_no_piece_of_a_coordinate_for_any_length_of_the_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for size in range(150, 262):  # the head left for the text goes from 129 down to 17
            log = Path("C:/" + "d" * size + "/doctor-1.log")
            message = self._message(monkeypatch, capsys, log, f"ffmpeg dijo {self.COORDINATES} ok")
            assert not any(piece in message for piece in ("18.4", "+18", "069", "9312")), size
            assert message.endswith(f"Detalle técnico en {log}"), size
            assert "[ubicacion omitida]" in message, size  # the error keeps 120 characters at least

    def test_error_message_long_root_the_message_with_a_short_root_has_the_marker(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        log = Path("C:/p/.kcut/logs/doctor-1.log")
        message = self._message(monkeypatch, capsys, log, f"fallo en {self.COORDINATES} ok")
        assert "[ubicacion omitida]" in message and "18.4861" not in message

    def test_error_message_scrubbed_a_phone_number_in_an_internal_error_is_masked(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        log = Path("C:/p/.kcut/logs/doctor-1.log")
        message = self._message(monkeypatch, capsys, log, f"tel {self.PHONE} y 809 555 1234 ok")
        assert "8095551234" not in message and "555 1234" not in message
        assert "tel ********** y *** *** **34 ok" in message  # "y" bridges: one number of 20

    def test_error_message_long_root_no_piece_of_a_number_for_any_length_of_the_path(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for size in range(150, 262):
            log = Path("C:/" + "d" * size + "/doctor-1.log")
            message = self._message(monkeypatch, capsys, log, f"llama al {self.PHONE} ya")
            assert not any(piece in message for piece in ("8095", "9555", "5551", "1234")), size

    def test_error_message_scrubbed_the_log_keeps_the_whole_traceback_unmasked(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(doctor, "run", raiser(RuntimeError(f"tel {self.PHONE}")))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        assert self.PHONE not in capsys.readouterr().err
        (log,) = (project / ".kcut" / "logs").glob("*.log")
        assert f"RuntimeError: tel {self.PHONE}" in log.read_text(encoding="utf-8")

    def test_error_message_nolog_the_backup_traceback_is_scrubbed_and_masked(
        self, project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(cli, "create_run_log", lambda log: None)  # the log cannot be made
        said = f"tel {self.PHONE} ok {self.COORDINATES} fin"
        monkeypatch.setattr(doctor, "run", raiser(RuntimeError(said)))
        assert cli.main(["doctor", "--project", str(project)]) == 10
        err = capsys.readouterr().err
        assert self.PHONE not in err and "18.4861" not in err and "069.9312" not in err
        assert "tel ********34 ok" in err
