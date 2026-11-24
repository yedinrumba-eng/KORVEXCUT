"""How a list of findings is written, line by line (spec 001.37 point 13; 001.52 point 5).

`kcut mix`, `kcut graphics check` and `kcut build` show the findings of a file the same way:
`<code> <path>: <message>` (the path only when the finding has one), at most `MAX_SHOWN` of them,
and a last line `... y N más` with how many were left out. The format lives here, and not in
`commands/`, because `kcut build` is in `pipeline/` and a module outside `commands/` cannot import a
command (`tests/unit/test_layers.py`). Findings are never merged: two with the same text and
different paths are two lines.
"""

from collections.abc import Sequence

from kcut.issues import MAX_SHOWN, Issue


def finding_line(issue: Issue) -> str:
    """`<code> <path>: <message>`; without the path if the finding has none."""
    where = f" {issue.path}" if issue.path else ""
    return f"{issue.code}{where}: {issue.message_es}"


def finding_lines(issues: Sequence[Issue]) -> list[str]:
    """The first `MAX_SHOWN` findings, one line each, and `... y N más` if there are more."""
    lines = [finding_line(issue) for issue in issues[:MAX_SHOWN]]
    if len(issues) > MAX_SHOWN:
        lines.append(f"... y {len(issues) - MAX_SHOWN} más")
    return lines
