"""The document of `kcut qa` (spec S1.9a, format `kcut.qa/1`): the verdict and the order of the
fields. `fail` if any check fails, `incomplete` if none fails and any was skipped, else `pass`; the
exit is 1 for `fail` and 0 for the rest. `warnings` is only in the document when there are some.
"""

import json
from pathlib import Path

import pytest

from kcut.qa.outputs import write_report
from kcut.qa.report import Check, QaReport, skipped, verdict_of
from tests.unit.gfx_resolve_fakes import make_project

PASS = Check("frames", "pass", {"value": 345, "expected": 345})
FAIL = Check("loudness", "fail", {"I_LUFS": -20.0})
SKIP = skipped("transcript", "no hay modelo")


def _report(*checks: Check, warnings: tuple[dict[str, str], ...] = ()) -> QaReport:
    return QaReport(
        "salida/v1.mp4", "edit/edl-v1.json", "2026-10-28T12:00:00", checks, 4.1, "00:11.5",
        "qa/v1/contact.jpg", {"probe": 1.1, "contact": 0.6}, warnings,
    )  # fmt: skip


@pytest.mark.parametrize(
    ("checks", "verdict", "exit_code"),
    [
        ([PASS], "pass", 0),
        ([], "pass", 0),
        ([PASS, SKIP], "incomplete", 0),
        ([PASS, FAIL], "fail", 1),
        ([SKIP, FAIL], "fail", 1),  # a failure wins over a skipped check
        ([FAIL, PASS, SKIP], "fail", 1),
    ],
)
def test_qa_report_the_verdict_and_the_exit_code(
    checks: list[Check], verdict: str, exit_code: int
) -> None:
    assert verdict_of(checks) == verdict
    report = _report(*checks)
    assert report.verdict == verdict and report.exit_code == exit_code


def test_qa_report_a_skipped_check_has_its_reason_and_no_figures() -> None:
    assert SKIP.to_json() == {"id": "transcript", "status": "skipped", "reason_es": "no hay modelo"}


def test_qa_report_the_fields_come_in_the_order_of_the_spec() -> None:
    document = _report(PASS, SKIP).to_json()
    assert list(document) == [
        "schema", "video", "edl", "generated", "verdict", "checks",
        "file_mb", "duration_display", "contact_sheet", "timings_s",
    ]  # fmt: skip
    assert document["schema"] == "kcut.qa/1" and document["verdict"] == "incomplete"


def test_qa_report_warnings_are_in_the_document_only_when_there_are_some() -> None:
    warning = {
        "code": "pii_unmasked",
        "message_es": "PII sin enmascarar (privacy.mask_pii = false)",
    }
    document = _report(PASS, warnings=(warning,)).to_json()
    assert list(document)[5:7] == ["checks", "warnings"] and document["warnings"] == [warning]
    assert "warnings" not in _report(PASS).to_json()


def test_qa_report_the_check_fields_follow_id_and_status() -> None:
    assert list(PASS.to_json()) == ["id", "status", "value", "expected"]
    with_reason = Check("loudness", "fail", {"I_LUFS": None}, "no se pudo medir")
    assert list(with_reason.to_json()) == ["id", "status", "I_LUFS", "reason_es"]


# 001.41, point 8: the report on disk has the texts `safe_text` gives, as what is printed has.
# Built with chr() so that no invisible character sits in this source: bidi override, zero width
# space, line separator, two characters of the "tag" zone and ESC.
_BAD = [chr(0x202E), chr(0x200B), chr(0x2028), chr(0xE0020), chr(0xE007F), chr(0x1B)]
HOSTILE = f"oído{_BAD[0]}{_BAD[1]}{_BAD[3]}{_BAD[4]}{_BAD[5]}[31m{_BAD[2]}fin"
FORBIDDEN = [*_BAD, *(chr(c) for c in range(0xE0020, 0xE0080))]


def _hostile_report() -> QaReport:
    diffs = [{"op": "replace", "expected": HOSTILE, "heard": HOSTILE, "at_f": 3, "at_display": "x"}]
    transcript = Check("transcript", "fail", {"match": 0.5, "diffs": diffs}, HOSTILE)
    warning = {"code": "cache_rebuilt", "message_es": HOSTILE}
    return _report(PASS, transcript, warnings=(warning,))


def test_qa_report_safe_text_every_text_of_the_document_is_escaped() -> None:
    document = _hostile_report().to_json()
    text = json.dumps(document, ensure_ascii=False)
    assert [c for c in FORBIDDEN if c in text] == []
    diff = document["checks"][1]["diffs"][0]  # type: ignore[index]
    assert diff["heard"] == "oído\\u202e\\u200b\\U000e0020\\U000e007f\\x1b[31m\\u2028fin"
    assert document["warnings"][0]["message_es"] == diff["heard"]  # type: ignore[index]


def test_qa_report_safe_text_leaves_numbers_accents_and_plain_text_as_they_are() -> None:
    document = _report(PASS, SKIP).to_json()
    plain = {"id": "frames", "status": "pass", "value": 345, "expected": 345}
    assert document["checks"][0] == plain  # type: ignore[index]
    assert document["file_mb"] == 4.1 and document["contact_sheet"] == "qa/v1/contact.jpg"
    accent = Check("loudness", "fail", {"I_LUFS": None}, "sonoridad: ñandú, óídos")
    assert accent.to_json()["reason_es"] == "sonoridad: ñandú, óídos"
    assert _report(accent).to_json()["checks"][0]["reason_es"] == "sonoridad: ñandú, óídos"  # type: ignore[index]


def test_qa_report_safe_text_the_file_on_disk_has_none_of_them(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    write_report(project, "qa/v1/report.json", _hostile_report())
    text = (project.root / "qa" / "v1" / "report.json").read_text(encoding="utf-8")
    assert [c for c in FORBIDDEN if c in text] == []
    assert json.loads(text) == _hostile_report().to_json()  # and it is the same document
