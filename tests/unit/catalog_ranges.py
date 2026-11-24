"""Ties the ranges that the catalog lists for the camera and the transitions to the ones the engine
enforces (spec S1.9a row 29; 001.41, point 9; D8: one source of truth).

`catalog/static_items.py` writes the `lo` and `hi` of each camera and transition parameter by hand,
and the checks of the engine (`edl/fields.py`, E13) have their own numbers. `refused(item, param,
value)` builds a span of the kind that has that parameter, sets it to `value` and says whether E13
complains about exactly that field: so a number that changes in one place and not in the other is a
test that fails. `RANGED` is the table of every parameter with a range: a new one that is not in it
fails too.
"""

from typing import Any

from kcut.edl.fields import check_fields
from kcut.edl.model import BrollSpan, CamSpan, ScreenKey, ScreenSpan, Span

CAM, BROLL, SCREEN = "cam", "broll", "screen"
RANGED: dict[tuple[str, str], str] = {  # (catalog id, parameter) -> the kind of span that has it
    ("zoom", "zoom"): CAM,
    ("push", "push"): CAM,
    ("reframe", "cx"): CAM,
    ("reframe", "cy"): CAM,
    ("screen_card", "card_y"): SCREEN,
    ("broll_push", "push"): BROLL,
    ("broll_push", "dim"): BROLL,
    ("fade_black", "fade_in_f"): CAM,
    ("fade_black", "fade_out_f"): CAM,
}
_KEY = ScreenKey(0, (0.5, 0.5, 1.0), (1040, 476))


def _span(kind: str, name: str, value: float) -> Span:
    common: dict[str, Any] = {"at_f": 0, "dur_f": 60, name: value}
    if kind == CAM:
        return CamSpan(src="a1", **common)
    if kind == BROLL:
        return BrollSpan(src="a2", src_f=0, **common)
    return ScreenSpan(src="b1", src_f=0, keys=(_KEY,), **common)


def refused(item_id: str, name: str, value: float) -> bool:
    """True if E13 says `name` is out of range when the span has `value` there."""
    span = _span(RANGED[item_id, name], name, value)
    issues = check_fields(span, "spans[0]", 1080, 1920)
    return any(i.code == "E13" and i.path == f"spans[0].{name}" for i in issues)
