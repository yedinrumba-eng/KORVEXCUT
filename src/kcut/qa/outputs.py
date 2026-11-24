"""What `kcut qa` writes: the contact sheet and the report (spec S1.9a; 001.41, points 4 and 5).

Both targets passed `assert_writable` (T4) before anything was measured. The ear takes minutes, and
in that time `qa/vN` can become a junction to somebody else's folder, so each target goes through
`assert_writable` AGAIN right before it is written (or deleted): the path it gives is the one that
is used. A sheet that was not made (`None`, 001.40) deletes the one an earlier run left: an old
sheet next to a report that says `contact_sheet: null` is a sheet nobody vouched for, and with
`privacy.mask_pii = false` in that old run it has the raw text.
"""

from kcut.errors import ProjectError
from kcut.jsonio import write_bytes_atomic, write_json_atomic
from kcut.project import Project, assert_writable
from kcut.qa.report import QaReport


def write_sheet(project: Project, rel: str, sheet: bytes | None) -> None:
    """Write `sheet` to `rel` (`qa/vN/contact.jpg`), or delete the file that is there if `sheet`
    is `None`. A file that cannot be deleted is a ProjectError: leaving it is the thing to avoid."""
    path = assert_writable(project, rel)
    if sheet is not None:
        write_bytes_atomic(path, sheet)
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        reason = exc.strerror or type(exc).__name__
        raise ProjectError(f"no pude borrar la hoja de contacto vieja {rel} ({reason})") from None


def write_report(project: Project, rel: str, report: QaReport) -> None:
    """Write `report` to `rel` (`qa/vN/report.json`), its texts through `safe_text` (`to_json`)."""
    write_json_atomic(assert_writable(project, rel), report.to_json())
