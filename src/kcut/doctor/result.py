"""The result type shared by every doctor check."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckResult:
    """One line of the doctor report."""

    id: str
    required: bool
    ok: bool
    detail: str
    fix_es: str | None
