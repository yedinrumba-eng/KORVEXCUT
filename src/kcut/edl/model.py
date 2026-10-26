"""The dataclasses of an `edit/edl-vN.json` (spec S1.5). Reading and checking it live elsewhere:
`edl.parse` reads the JSON, `edl.files` finds the file, `edl.refs` and `edl.ranges` check it.

Every `*_f` is a whole number of frames at the project's fps. Nothing here is validated: a value
out of range is an `edl.ranges` finding, not a failure to read.
"""

from dataclasses import dataclass, field

SCHEMA = "kcut.edl/1"
ANCHORS = ("top", "center", "bottom")
DEFAULT_LOOK = "neutro"


@dataclass(frozen=True)
class VoiceClip:
    """Audio of `src`, frames `[in_f, out_f)` of its clock, placed at `at_f` of the output."""

    at_f: int
    src: str
    in_f: int
    out_f: int
    why: str

    @property
    def dur_f(self) -> int:
        return self.out_f - self.in_f


@dataclass(frozen=True)
class GapClip:
    """Silence: `dur_f` frames with no voice."""

    at_f: int
    dur_f: int
    why: str


Clip = VoiceClip | GapClip


@dataclass(frozen=True, kw_only=True)
class SpanCommon:
    """What every span has. `look` is `None` for the global one."""

    at_f: int
    dur_f: int
    look: str | None = None
    fade_in_f: int = 0
    fade_out_f: int = 0
    why: str = ""


@dataclass(frozen=True, kw_only=True)
class CamSpan(SpanCommon):
    """A camera shot. Without `src_f` it is synchronized to the voice; with it, it plays `src`
    from `src_f` at 1x."""

    src: str
    zoom: float = 1.0
    cx: float = 0.5
    cy: float = 0.5
    anchor: str = "center"
    push: float = 0.0
    src_f: int | None = None


@dataclass(frozen=True, kw_only=True)
class BrollSpan(SpanCommon):
    """Cover footage played from `src_f`, with a slow push-in."""

    src: str
    src_f: int
    push: float = 0.07
    cx: float = 0.5
    cy: float = 0.5
    dim: float = 1.0
    sharpen: float = 0.0


@dataclass(frozen=True)
class ScreenKey:
    """A key of a screen insert: at frame `at_f` of the span, crop `(cx, cy, cw)` of the source
    (normalized) shown on a card of `card = (w, h)` output pixels."""

    at_f: int
    crop: tuple[float, float, float]
    card: tuple[int, int]


@dataclass(frozen=True)
class RemapPoint:
    """From frame `at_f` of the span the source plays from `src_f` at `speed` times."""

    at_f: int
    src_f: int
    speed: float = 1.0


@dataclass(frozen=True, kw_only=True)
class ScreenSpan(SpanCommon):
    src: str
    src_f: int
    keys: tuple[ScreenKey, ...]
    remap: tuple[RemapPoint, ...] = ()
    card_y: float = 0.47


@dataclass(frozen=True, kw_only=True)
class ColorSpan(SpanCommon):
    color: str


Span = CamSpan | BrollSpan | ScreenSpan | ColorSpan


@dataclass(frozen=True)
class Edl:
    """A whole EDL. `sources` maps each clip id to the `qhash` the EDL was written for."""

    version: int
    fps: int
    out_w: int
    out_h: int
    frames: int
    look: str
    sources: dict[str, str]
    clips: tuple[Clip, ...]
    spans: tuple[Span, ...]
    schema: str = field(default=SCHEMA)


def span_src(span: Span) -> str | None:
    """The clip a span reads, or `None` for a color span."""
    return None if isinstance(span, ColorSpan) else span.src
