"""What a command says when the EDL it was given has errors (spec 001.31, point 12). It was
`render._refuse`, a private name that `graphics_capture` imported from another command; here every
user imports it by its own name. It lives in `edl/`, not in `commands/`, so that `qa/run.py` can
call it too (001.44: nothing outside `commands/` imports a command).
"""

from __future__ import annotations

from typing import NoReturn

from kcut.console import Out
from kcut.errors import CheckFailed
from kcut.issues import Issue

MAX_NAMED = 5  # findings of the check that are printed when an EDL is refused


REMEDY_ES = "corre kcut edl check y corrígelos"  # what the message ends with, unless told otherwise


def refuse_edl(out: Out, rel: str, errors: list[Issue], *, remedy: str = REMEDY_ES) -> NoReturn:
    """The EDL has errors: print the first ones and stop with exit 1, before any frame is made.
    `remedy` is the end of the message: the snapshot of a build is cured with `kcut build`, not
    with `kcut edl check` (001.47, point 8)."""
    for issue in errors[:MAX_NAMED]:
        out.line("ERROR", f"{issue.code} {issue.path}: {issue.message_es}")
    named = ", ".join(sorted({issue.code for issue in errors}))
    raise CheckFailed(f"{rel} tiene {len(errors)} errores ({named}); {remedy}")
