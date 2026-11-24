"""The document `qa/vN/report.json` (spec S1.9a, format `kcut.qa/1`).

A check is `pass`, `fail` or `skipped`; the verdict of the report is `fail` if any check fails,
`incomplete` if none fails and any was skipped, and `pass` otherwise. `kcut qa` exits 1 on `fail`
and 0 on the rest. Nothing here is read from the file under test: every figure was measured and
every text is fixed (the words of the diff, the one thing that comes from the speech, are masked
before they get here). The document goes through `safe_text` (001.41, point 8) on its way to the
disk as it does on its way to the terminal: the words that were heard are not trusted either.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from kcut.console import clean, safe_text

SCHEMA = "kcut.qa/1"
Status = Literal["pass", "fail", "skipped"]
Verdict = Literal["pass", "fail", "incomplete"]


@dataclass(frozen=True)
class Check:
    """One line of the report. `data` are the fields after `id` and `status`, in the order the
    report prints them; `reason_es` says why a check was skipped (or why it failed, when the
    numbers alone do not say it)."""

    id: str
    status: Status
    data: dict[str, object] = field(default_factory=dict)
    reason_es: str | None = None

    def to_json(self) -> dict[str, object]:
        out: dict[str, object] = {"id": self.id, "status": self.status, **self.data}
        if self.reason_es is not None:
            out["reason_es"] = self.reason_es
        return out


def skipped(check_id: str, reason_es: str) -> Check:
    """A check that was not made, and why."""
    return Check(check_id, "skipped", {}, reason_es)


def verdict_of(checks: Sequence[Check]) -> Verdict:
    """`fail` if any check failed; `incomplete` if none failed and any was skipped; else `pass`."""
    if any(check.status == "fail" for check in checks):
        return "fail"
    if any(check.status == "skipped" for check in checks):
        return "incomplete"
    return "pass"


@dataclass(frozen=True)
class QaReport:
    """The whole report. `warnings` are `{"code", "message_es"}` and are only in the JSON when
    there are any (`pii_unmasked`, `cache_rebuilt`, `contact_skipped`...). `contact_sheet` is
    `None` (`null` in the JSON) when the sheet was not written (001.40)."""

    video: str
    edl: str
    generated: str
    checks: tuple[Check, ...]
    file_mb: float
    duration_display: str
    contact_sheet: str | None
    timings_s: dict[str, float]
    warnings: tuple[dict[str, str], ...] = ()

    @property
    def verdict(self) -> Verdict:
        return verdict_of(self.checks)

    @property
    def exit_code(self) -> int:
        return 1 if self.verdict == "fail" else 0

    def to_json(self) -> dict[str, object]:
        """The document, every string of it (keys too) through `safe_text`: what is written to
        `qa/vN/report.json` and what `--json` prints are the same."""
        return {safe_text(key): clean(value) for key, value in self._document().items()}

    def _document(self) -> dict[str, object]:
        out: dict[str, object] = {
            "schema": SCHEMA,
            "video": self.video,
            "edl": self.edl,
            "generated": self.generated,
            "verdict": self.verdict,
            "checks": [check.to_json() for check in self.checks],
        }
        if self.warnings:
            out["warnings"] = [dict(item) for item in self.warnings]
        out.update(
            {
                "file_mb": self.file_mb,
                "duration_display": self.duration_display,
                "contact_sheet": self.contact_sheet,
                "timings_s": dict(self.timings_s),
            }
        )
        return out
