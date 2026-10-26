"""What a check found, and the exit code it asks for (spec S1.5a, 001.15 T1).

Neutral on purpose: it imports nothing from `kcut`, so `edl`, `gfx`, `audio` and `storyboard` can
all use it without one package having to import another.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

# Codes whose error ends in exit 5 (`GateError`) and not in exit 1: G10 (graphics.json asks for a
# resource that is not approved) and M04 (the same for music.json).
GATE_CODES = frozenset({"G10", "M04"})


@dataclass(frozen=True)
class Issue:
    """One finding: `code` (`E06`, `W03`...), its `level`, where it is (`clips[4]`) and what it
    says (Spanish, safe to print: it never quotes a key or a text of the file whole)."""

    code: str
    level: Literal["error", "warning"]
    path: str
    message_es: str


def exit_code(issues: Sequence[Issue]) -> int:
    """5 if an error has a code in `GATE_CODES`; else 1 if there is any error; else 0.
    Warnings never change the exit code."""
    errors = [issue for issue in issues if issue.level == "error"]
    if any(issue.code in GATE_CODES for issue in errors):
        return 5
    return 1 if errors else 0


def issue_json(issue: Issue) -> dict[str, str]:
    """The issue as the `--json` documents list it."""
    return {"code": issue.code, "path": issue.path, "message": issue.message_es}
