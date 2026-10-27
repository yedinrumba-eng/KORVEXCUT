"""The numbers of one span (spec S1.5a): ranges (E13), the order of keys and remap (E15) and the
remap that disagrees with `src_f` (E18). Pure; called by `edl.ranges` for each span.
"""

from kcut.edl.model import BrollSpan, CamSpan, ScreenSpan, Span
from kcut.edl.shown import shown_number
from kcut.issues import Issue

CARD_SIDE_MARGIN = 16  # a card is at most `W - 16` wide...
CARD_TOP_MARGIN = 120  # ...and `H - 120` tall
CARD_MAX_ASPECT = 8  # the long side of a card is at most this many times the short one (001.25)


def check_fields(span: Span, path: str, out_w: int, out_h: int) -> list[Issue]:
    """E13, E15 and E18 for `span`, which is `path` (`spans[3]`)."""
    issues: list[Issue] = []
    _within(issues, path, "fade_in_f", span.fade_in_f, 0, None)
    _within(issues, path, "fade_out_f", span.fade_out_f, 0, None)
    if isinstance(span, CamSpan):
        _within(issues, path, "zoom", span.zoom, 1.0, 3.0)
        _within(issues, path, "cx", span.cx, 0.0, 1.0)
        _within(issues, path, "cy", span.cy, 0.0, 1.0)
        _within(issues, path, "push", span.push, 0.0, 0.5)
    elif isinstance(span, BrollSpan):
        _within(issues, path, "push", span.push, 0.0, 0.5)
        _within(issues, path, "cx", span.cx, 0.0, 1.0)
        _within(issues, path, "cy", span.cy, 0.0, 1.0)
        _within(issues, path, "dim", span.dim, 0.0, 1.5)
        _within(issues, path, "sharpen", span.sharpen, 0.0, 1.0)
    elif isinstance(span, ScreenSpan):
        _within(issues, path, "card_y", span.card_y, 0.0, 1.0)
        _screen(issues, span, path, out_w, out_h)
    return issues


def _within(
    issues: list[Issue], path: str, name: str, value: float, low: float, high: float | None
) -> None:
    """E13 if `value` is below `low` or above `high` (`None`: no top)."""
    if value < low or (high is not None and value > high):
        span = f"de {low:g} a {high:g}" if high is not None else f"desde {low:g}"
        issues.append(Issue("E13", "error", f"{path}.{name}", f"{name} va {span} (vino {value:g})"))


def _screen(issues: list[Issue], span: ScreenSpan, path: str, out_w: int, out_h: int) -> None:
    for i, key in enumerate(span.keys):
        where = f"{path}.keys[{i}]"
        _within(issues, where, "crop[0]", key.crop[0], 0.0, 1.0)
        _within(issues, where, "crop[1]", key.crop[1], 0.0, 1.0)
        _within(issues, where, "crop[2]", key.crop[2], 0.05, 1.0)
        width, height = key.card
        card = f"{shown_number(width)}x{shown_number(height)}"
        if width < 1 or height < 1:
            issues.append(
                Issue("E13", "error", f"{where}.card", "la tarjeta tiene que medir 1 px o más")
            )
        elif width > out_w - CARD_SIDE_MARGIN or height > out_h - CARD_TOP_MARGIN:
            found = (
                f"la tarjeta de {card} no cabe: como mucho "
                f"{out_w - CARD_SIDE_MARGIN}x{out_h - CARD_TOP_MARGIN}"
            )
            issues.append(Issue("E13", "error", f"{where}.card", found))
        elif max(width, height) > CARD_MAX_ASPECT * min(width, height):
            found = (
                f"la tarjeta de {card} es demasiado alargada: "
                f"el lado largo es como mucho {CARD_MAX_ASPECT} veces el corto"
            )
            issues.append(Issue("E13", "error", f"{where}.card", found))
    for i, point in enumerate(span.remap):
        _within(issues, f"{path}.remap[{i}]", "speed", point.speed, 0.25, 4.0)
    _order(issues, f"{path}.keys", [k.at_f for k in span.keys], span.dur_f, required=True)
    _order(issues, f"{path}.remap", [p.at_f for p in span.remap], span.dur_f, required=False)
    if span.remap and span.src_f != span.remap[0].src_f:
        found = (
            f"src_f ({shown_number(span.src_f)}) no es el de remap[0] "
            f"({shown_number(span.remap[0].src_f)}); con remap manda remap"
        )
        issues.append(Issue("E18", "error", f"{path}.src_f", found))


def _order(
    issues: list[Issue], path: str, starts: list[int], dur_f: int, *, required: bool
) -> None:
    """E15: the first `at_f` is 0, each one is bigger than the last, all fall inside the span.
    With `required` (the keys) there has to be at least one; no remap is simply no remap."""
    if not starts:
        if required:
            issues.append(Issue("E15", "error", path, "necesita al menos una clave"))
        return
    if starts[0] != 0:
        issues.append(Issue("E15", "error", f"{path}[0]", "la primera tiene que estar en at_f = 0"))
    for i, at_f in enumerate(starts):
        if i and at_f <= starts[i - 1]:
            found = (
                f"at_f ({shown_number(at_f)}) tiene que ser mayor que el de la anterior "
                f"({shown_number(starts[i - 1])})"
            )
            issues.append(Issue("E15", "error", f"{path}[{i}]", found))
        if at_f < 0 or at_f >= dur_f:
            found = (
                f"at_f ({shown_number(at_f)}) cae fuera del tramo "
                f"(de 0 a {shown_number(dur_f - 1)})"
            )
            issues.append(Issue("E15", "error", f"{path}[{i}]", found))
