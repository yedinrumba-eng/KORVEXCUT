"""The two functions that `graphics check` and `mix` share to list their findings (spec S1.8b round
1, 001.37 point 13; row 36): `findings_json` (at most `MAX_SHOWN` errors and as many warnings, the
totals, whether something was left out) and `list_findings` (one line each and `... y N más`).
`edl check` keeps its own, with another ellipsis.
"""

from typing import Literal

import pytest

from kcut.commands import edl, graphics, listing, mix
from kcut.commands.listing import findings_json, list_findings
from kcut.console import Out
from kcut.issues import MAX_SHOWN, Issue, issue_json


def _issues(count: int, level: Literal["error", "warning"] = "error") -> list[Issue]:
    return [Issue("A01", level, f"events[{i}]", f"mensaje {i}") for i in range(count)]


def test_listing_findings_json_cuts_to_max_shown_and_keeps_the_totals() -> None:
    errors = [issue_json(i) for i in _issues(MAX_SHOWN + 3)]
    warnings = [issue_json(i) for i in _issues(2, "warning")]
    found = findings_json(errors, warnings)
    assert found["errors"] == errors[:MAX_SHOWN] and found["warnings"] == warnings
    assert found["errors_total"] == MAX_SHOWN + 3 and found["warnings_total"] == 2
    assert found["truncated"] is True


def test_listing_findings_json_with_few_findings_is_not_truncated() -> None:
    found = findings_json([issue_json(i) for i in _issues(2)], [])
    assert found == {
        "errors": [issue_json(i) for i in _issues(2)],
        "warnings": [],
        "errors_total": 2,
        "warnings_total": 0,
        "truncated": False,
    }


def test_listing_list_findings_prints_a_line_each_and_how_many_more(
    capsys: pytest.CaptureFixture[str],
) -> None:
    list_findings(Out(json_mode=False), "ERROR", _issues(MAX_SHOWN + 2))
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "[ERROR] A01 events[0]: mensaje 0"
    assert len(lines) == MAX_SHOWN + 1 and lines[-1] == "[ERROR] ... y 2 más"


def test_listing_list_findings_a_finding_without_a_path_has_no_double_space(
    capsys: pytest.CaptureFixture[str],
) -> None:
    list_findings(Out(json_mode=False), "AVISO", [Issue("G11", "warning", "", "algo")])
    assert capsys.readouterr().out == "[AVISO] G11: algo\n"


def test_listing_graphics_check_and_mix_use_the_shared_functions_and_edl_keeps_its_own() -> None:
    assert graphics.findings_json is listing.findings_json is mix.findings_json
    assert graphics.list_findings is listing.list_findings is mix.list_findings
    for module in (graphics, mix):
        assert not hasattr(module, "_list") and not hasattr(module, "_findings_json")
    assert hasattr(edl, "_list")  # its lines are cut with another ellipsis
