"""The errors of Playwright, told and recognised (spec S1.6b 001.31 point 11, 001.33 point 6).
Split from `capture.py` by the 300-line rule; `capture` is what the rest of the code calls.

Playwright is imported where it is first needed, never at the top: `kcut doctor` has to start
without it, and a package that is not there is a MissingDependency (exit 7), not an internal error.
"""

from kcut.errors import MissingDependency
from kcut.pack.pii import mask_text

_MAX_ERROR_CHARS = 200


def playwright_error() -> type[Exception]:
    """The base class of the errors of Playwright (imported here, when it is first needed). If the
    package is not there, that is a MissingDependency (exit 7), not an internal error."""
    try:
        from playwright.sync_api import Error
    except ImportError:
        raise MissingDependency(
            "falta el paquete playwright; corre kcut doctor para ver qué falta"
        ) from None
    return Error


def short(exc: Exception) -> str:
    """The first line of what `exc` says, or the name of its class if it says nothing."""
    return str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__


def clean(text: str) -> str:
    """`text` of a page error as one line, cut, with the numbers masked: it is text of a page that
    drew a transcript."""
    return mask_text(text.strip().replace("\n", " ")[:_MAX_ERROR_CHARS], parts=False)
