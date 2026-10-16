"""`kcut doctor` end to end with ffmpeg simulated: JSON document, human lines, exit codes."""

import json

import pytest

from kcut import proc
from kcut.doctor import checks
from tests.unit.doctor_fakes import FakeFfmpeg


class TestDoctorCommand:
    def test_missing_filter_gives_ok_false_and_exit_1(
        self,
        monkeypatch: pytest.MonkeyPatch,
        light_checks: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from kcut import cli

        present = tuple(f for f in checks.REQUIRED_FILTERS if f != "zscale")
        monkeypatch.setattr(proc, "run", FakeFfmpeg(filters=present))
        assert cli.main(["doctor", "--json"]) == 1
        doc = json.loads(capsys.readouterr().out)
        assert doc["schema"] == "kcut.doctor/1"
        assert doc["ok"] is False
        by_id = {c["id"]: c for c in doc["checks"]}
        assert by_id["filters"]["ok"] is False
        assert "zscale" in by_id["filters"]["detail"]
        assert by_id["ffmpeg"]["ok"] is True

    def test_everything_present_gives_ok_true_and_exit_0(
        self,
        monkeypatch: pytest.MonkeyPatch,
        light_checks: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from kcut import cli

        monkeypatch.setattr(proc, "run", FakeFfmpeg())
        assert cli.main(["doctor", "--json"]) == 0
        doc = json.loads(capsys.readouterr().out)
        assert doc["ok"] is True
        assert set(doc["checks"][0]) == {"id", "required", "ok", "detail", "fix_es"}

    def test_optional_failure_does_not_fail_doctor(
        self,
        monkeypatch: pytest.MonkeyPatch,
        light_checks: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from kcut import cli

        monkeypatch.setattr(proc, "run", FakeFfmpeg(filters=checks.REQUIRED_FILTERS))
        assert cli.main(["doctor", "--json"]) == 0
        doc = json.loads(capsys.readouterr().out)
        optional = next(c for c in doc["checks"] if c["id"] == "filters_optional")
        assert optional["ok"] is False
        assert doc["ok"] is True

    def test_human_output_tags(
        self,
        monkeypatch: pytest.MonkeyPatch,
        light_checks: None,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from kcut import cli

        monkeypatch.setattr(proc, "run", FakeFfmpeg(filters=checks.REQUIRED_FILTERS[1:]))
        assert cli.main(["doctor"]) == 1
        out = capsys.readouterr().out
        assert "[OK] python:" in out
        assert "[FALTA] filters: 21/22 faltan: zscale - usa el build full de gyan.dev" in out
        assert "[AVISO] filters_optional:" in out
