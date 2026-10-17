"""The `reason` text each sync rejection stores, the pure map from a stored reason back to its
motive, and the fixed texts the console shows for it (spec 001.7, points 1, 6, 11 and 12).

The per-clip warning is derived from the *stored* reason, never from side data such as whether
`refine_corr` is present. The console never prints a `reason` or a `method` as it came from
`inventory.json` (a hostile file could carry terminal escape sequences): it prints the fixed text
of the motive. The stored texts below are what `sync.py` has always written; they do not change.
"""

from typing import Literal

REASON_SCORE = "pico de correlacion bajo"
REASON_RATIO = "pico ambiguo (hay otro casi igual de alto)"
REASON_WEAK_REFINE = "sync_weak_refine"  # prefix: the stored text goes on with the numbers
REASON_AMBIGUOUS = "sync_ambiguous"  # prefix: same style as `sync_weak_refine`

# The only `method` values kcut writes; any other one is never printed.
SYNC_METHODS = ("envelope+raw", "manual")
# Range accepted for a stored lag (12 h, like the other time fields) and the longest stored text.
MAX_LAG_MS = 43_200_000
MAX_TEXT_LEN = 300

Motive = Literal["score", "ratio", "weak_refine", "ambiguous"]

_FIXED_TEXT: dict[Motive, str] = {
    "score": "el pico de correlación es bajo",
    "ratio": "hay otro pico casi igual de alto",
    "weak_refine": "el audio fino no coincide lo bastante",
}
_AMBIGUOUS_NO_LAGS = "sincronía ambigua: clip corto con dos desfases posibles; revísalo a mano"


def rejection_motive(reason: str) -> Motive | None:
    """Why a pair was rejected, from the `reason` stored in `sync.rejected`.

    `None` for a text this version does not write (an old or hand-made inventory): the clip then
    only gets the generic `sync_rejected` warning.
    """
    if reason == REASON_SCORE:
        return "score"
    if reason == REASON_RATIO:
        return "ratio"
    if reason.startswith(REASON_WEAK_REFINE):
        return "weak_refine"
    if reason.startswith(REASON_AMBIGUOUS):
        return "ambiguous"
    return None


def rejection_text(reason: str, lag_a_ms: int | None, lag_b_ms: int | None) -> str | None:
    """The fixed console text for a stored rejection, or `None` when the reason is not one kcut
    writes. Nothing of `reason` itself is ever returned."""
    motive = rejection_motive(reason)
    if motive is None:
        return None
    if motive == "ambiguous":
        return ambiguity_message(lag_a_ms, lag_b_ms)
    return _FIXED_TEXT[motive]


def ambiguity_message(lag_a_ms: int | None, lag_b_ms: int | None) -> str:
    """The user-facing text of a `sync_ambiguous` rejection: the two lags, in seconds.

    Never raises: a lag that is missing, not an integer or outside `MAX_LAG_MS` (a hostile or
    damaged inventory) gives the text without numbers.
    """
    first, second = _seconds(lag_a_ms), _seconds(lag_b_ms)
    if first is None or second is None:
        return _AMBIGUOUS_NO_LAGS
    return (
        "sincronía ambigua: clip corto con dos desfases posibles "
        f"({first} s y {second} s); revísalo a mano"
    )


def _seconds(ms: object) -> str | None:
    """Milliseconds as seconds with integer arithmetic only (no float division of a huge int)."""
    if isinstance(ms, bool) or not isinstance(ms, int) or abs(ms) > MAX_LAG_MS:
        return None
    whole, millis = divmod(abs(ms), 1000)
    text = f"{whole}.{millis:03d}".rstrip("0").rstrip(".")
    return f"-{text}" if ms < 0 else text
