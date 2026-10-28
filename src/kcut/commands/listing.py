"""How the commands that judge a file list their findings (spec 001.37, point 13): `graphics check`
and `mix` print the first `MAX_SHOWN` errors and warnings one line each, and give them in `--json`
with their totals. They had a copy of these two functions each. `edl check` keeps its own: its
lines are cut with another ellipsis.
"""

from collections.abc import Sequence

from kcut.console import Out
from kcut.issues import MAX_SHOWN, Issue


def findings_json(
    errors: Sequence[dict[str, str]], warnings: Sequence[dict[str, str]]
) -> dict[str, object]:
    """The findings as `--json` lists them, like `edl check --json` (001.30 point 1): at most
    `MAX_SHOWN` errors and as many warnings, the totals, and whether anything was left out. A
    file with thousands of findings costs a page, not a log. `errors` and `warnings` are the
    findings already as dicts (`issue_json`, or a notice made into one)."""
    return {
        "errors": list(errors[:MAX_SHOWN]),
        "warnings": list(warnings[:MAX_SHOWN]),
        "errors_total": len(errors),
        "warnings_total": len(warnings),
        "truncated": len(errors) > MAX_SHOWN or len(warnings) > MAX_SHOWN,
    }


def list_findings(out: Out, tag: str, issues: Sequence[Issue]) -> None:
    """The first `MAX_SHOWN` findings, one line each, and how many more there are."""
    for issue in issues[:MAX_SHOWN]:
        where = f" {issue.path}" if issue.path else ""
        out.line(tag, f"{issue.code}{where}: {issue.message_es}")
    if len(issues) > MAX_SHOWN:
        out.line(tag, f"... y {len(issues) - MAX_SHOWN} más")
