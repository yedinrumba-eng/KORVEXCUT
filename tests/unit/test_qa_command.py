"""`kcut qa`, the command (spec S1.9a): what it prints and what it exits with, with the audit
itself replaced by a finished report. `pass` and `incomplete` exit 0, `fail` exits 1, and `--json`
prints the report in all three cases. The audit is tested in `test_qa_*.py` and
`tests/integration/test_qa_synth.py`.
"""

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from kcut import cli
from kcut.commands import qa as qa_command
from kcut.qa.report import Check, QaReport, skipped

FRAMES = Check("frames", "pass", {"value": 345, "expected": 345})
STREAM = Check("video_stream", "pass", {"value": {"codec": "h264", "size": "1080x1920"}})
LOUD = Check(
    "loudness",
    "pass",
    {
        "I_LUFS": -14.4,
        "TP_dBTP": -4.0,
        "LRA": 2.7,
        "target": -14.0,
        "tolerance": 1.0,
        "max_tp": -1.0,
    },
)
LOUD_FAIL = Check(
    "loudness",
    "fail",
    {
        "I_LUFS": None,
        "TP_dBTP": None,
        "LRA": None,
        "target": -14.0,
        "tolerance": 1.0,
        "max_tp": -1.0,
    },
    "no se pudo medir la sonoridad: el audio está en silencio",
)
BLACK = Check("black", "pass", {"intervals": [{"start_f": 0, "end_f": 30, "expected": True}]})
FREEZE = Check("freeze", "fail", {"intervals": [{"start_f": 100, "end_f": 150, "expected": False}]})
SKIPPED = skipped("transcript", "el modelo de Whisper no está en esta máquina")


def _transcript(count: int) -> Check:
    diffs = [
        {"op": "replace", "expected": f"a{i}", "heard": f"b{i}", "at_f": i, "at_display": "00:00.0"}
        for i in range(count)
    ]
    data = {
        "match": 0.5,
        "min": 0.8,
        "language": "es",
        "expected_words": 9,
        "heard_words": 9,
        "diffs": diffs,
    }
    return Check("transcript", "fail", data)


def _report(*checks: Check, warnings: tuple[dict[str, str], ...] = ()) -> QaReport:
    return QaReport(
        "salida/v1.mp4",
        "edit/edl-v1.json",
        "2026-10-28T12:00:00",
        checks,
        4.1,
        "00:11.5",
        "qa/v1/contact.jpg",
        {"probe": 1.1},
        warnings,
    )


def _run(
    monkeypatch: pytest.MonkeyPatch,
    project: Path,
    report: QaReport,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
) -> tuple[int, str, str]:
    seen: list[tuple[str, str | None]] = []

    def fake(_project: Any, video: str, edl: str | None, _progress: Any, **_kw: Any) -> QaReport:
        seen.append((video, edl))
        return report

    monkeypatch.setattr(qa_command, "run_qa", fake)
    capsys.readouterr()
    code = cli.main(["qa", "salida/v1.mp4", "--project", str(project), *extra])
    shown = capsys.readouterr()
    assert seen == [
        ("salida/v1.mp4", extra[extra.index("--edl") + 1] if "--edl" in extra else None)
    ]
    return code, shown.out, shown.err


def test_qa_command_a_pass_is_exit_0_and_every_check_has_its_line(
    monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(monkeypatch, project, _report(FRAMES, STREAM, LOUD, BLACK), capsys)
    assert code == 0
    assert "[OK] frames: 345 frames de 345 esperados" in out
    assert "[OK] video_stream: h264 1080x1920" in out
    assert "[OK] loudness: -14.4 LUFS (objetivo -14.0 +/- 1.0), pico -4.0 dBTP (máximo -1.0)" in out
    assert "[OK] black: 1 intervalos, 0 no esperados" in out
    assert out.splitlines()[-1].startswith("[OK] veredicto pass - 00:11.5, 4.1 MB - reporte en ")
    assert "qa/v1/report.json, hoja en qa/v1/contact.jpg" in out


def test_qa_command_an_incomplete_is_exit_0_with_a_warning_line(
    monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(monkeypatch, project, _report(FRAMES, SKIPPED), capsys)
    assert code == 0
    assert "[AVISO] transcript: omitido - el modelo de Whisper no está en esta máquina" in out
    assert out.splitlines()[-1].startswith("[AVISO] veredicto incomplete")


def test_qa_command_a_fail_is_exit_1(
    monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(monkeypatch, project, _report(FRAMES, FREEZE, LOUD_FAIL), capsys)
    assert code == 1
    assert "[ERROR] freeze: 1 intervalos, 1 no esperados" in out
    assert "[ERROR] loudness: sin dato LUFS (objetivo -14.0 +/- 1.0), pico sin dato dBTP" in out
    assert "no se pudo medir la sonoridad" in out
    assert out.splitlines()[-1].startswith("[ERROR] veredicto fail")


@pytest.mark.parametrize("checks", [[FRAMES], [FRAMES, SKIPPED], [FRAMES, FREEZE]])
def test_qa_command_json_is_the_report_whatever_the_verdict(
    monkeypatch: pytest.MonkeyPatch,
    project: Path,
    capsys: pytest.CaptureFixture[str],
    checks: list[Check],
) -> None:
    report = _report(*checks)
    code, out, _ = _run(monkeypatch, project, report, capsys, "--json")
    assert json.loads(out) == report.to_json()
    assert code == report.exit_code


def test_qa_command_the_transcript_lists_five_differences_and_says_how_many_more(
    monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = _run(monkeypatch, project, _report(_transcript(7)), capsys)
    infos = [line for line in out.splitlines() if line.startswith("[INFO]")]
    assert infos[0] == "[INFO] 00:00.0 replace: esperado 'a0', oído 'b0'"
    assert len(infos) == 6 and infos[-1] == "[INFO] ... y 2 más (están en el reporte)"
    assert "coincidencia 0.5 (mínimo 0.8), idioma es, 7 diferencias" in out


def test_qa_command_the_warnings_go_to_stderr(
    monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    warning = {"code": "cache_rebuilt", "message_es": "x.json: el oído guardado no era válido"}
    code, out, err = _run(monkeypatch, project, _report(FRAMES, warnings=(warning,)), capsys)
    assert code == 0 and "[AVISO] cache_rebuilt: x.json: el oído guardado no era válido" in err
    assert "cache_rebuilt" not in out


def test_qa_command_the_edl_option_is_passed_on(
    monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _, _ = _run(monkeypatch, project, _report(FRAMES), capsys, "--edl", "edit/edl-v2.json")
    assert code == 0


def test_qa_command_without_a_video_is_exit_2(
    project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    capsys.readouterr()
    assert cli.main(["qa", "--project", str(project), "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["kind"] == "UsageError"


def _without_sheet(*checks: Check) -> QaReport:
    """The report of a run that wrote no contact sheet (001.40): `contact_sheet` is None."""
    warning = {"code": "contact_skipped", "message_es": "la hoja de contacto no se escribió"}
    return dataclasses.replace(_report(*checks, warnings=(warning,)), contact_sheet=None)


def test_qa_command_contact_masked_a_report_without_the_sheet_says_so_in_the_last_line(
    monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(monkeypatch, project, _without_sheet(FRAMES, LOUD), capsys)
    assert code == 0
    assert out.splitlines()[-1].startswith("[OK] veredicto pass - 00:11.5, 4.1 MB - reporte en ")
    assert out.splitlines()[-1].endswith("qa/v1/report.json, sin hoja de contacto")
    assert "[AVISO] contact_skipped: la hoja de contacto no se escribió" in err


def test_qa_command_contact_masked_the_json_of_a_report_without_the_sheet_has_null(
    monkeypatch: pytest.MonkeyPatch, project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _without_sheet(FRAMES)
    code, out, _ = _run(monkeypatch, project, report, capsys, "--json")
    document = json.loads(out)
    assert code == 0 and document["contact_sheet"] is None and "contact_sheet" in document
    assert document == report.to_json()
