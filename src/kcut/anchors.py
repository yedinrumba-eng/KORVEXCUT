"""Time anchors: a moment of the output given as a frame, as a kept word or as a frame of a source
clip (spec S1.6a, 001.15 T1, DS7).

Neutral on purpose: `gfx` (graphics) and `audio/sfx_events.py` (sound effects) both use it, and it
only imports from `edl`. The caller puts its own code on a problem (G01/G04/G05/G06 for graphics,
A01/A04/A05/A06 for sfx) and its own path. Anchors survive a new EDL: a word or a frame of the
source is found again wherever the new cut puts it.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from kcut.edl.model import Edl
from kcut.edl.timeline import source_to_output
from kcut.edl.words import KeptWord

Problem = Literal["shape", "word_not_kept", "src_not_heard"]
_WORD_KEYS = frozenset({"word", "edge", "offset_f"})
_SRC_KEYS = frozenset({"src", "f", "offset_f"})
_EDGES = ("start", "end")


@dataclass(frozen=True)
class Resolved:
    """The output frame an anchor points at (`None` if it could not be found, and then `problem`
    says why) and in how many output frames a source anchor is heard (`repeats`; 1 for a frame or
    a word, 0 when there is a problem)."""

    frame: int | None
    problem: Problem | None
    repeats: int


def _is_whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def has_time_shape(v: object) -> bool:
    """Does `v` have one of the three forms of a moment: a whole number (no `bool`), a word anchor
    `{"word": str, "edge": "start"|"end", "offset_f": int}` or a source anchor
    `{"src": str, "f": int, "offset_f": int}`? `offset_f` is optional; no other key is allowed.
    Only the shape: nothing is looked up (that is `resolve_time`)."""
    if _is_whole(v):
        return True
    if not isinstance(v, dict):
        return False
    keys = set(v)
    if "word" in v:
        ok = {"word", "edge"} <= keys <= _WORD_KEYS
        return ok and isinstance(v["word"], str) and v["edge"] in _EDGES and _offset_ok(v)
    if "src" in v:
        ok = {"src", "f"} <= keys <= _SRC_KEYS
        return ok and isinstance(v["src"], str) and _is_whole(v["f"]) and _offset_ok(v)
    return False


def _offset_ok(v: dict[str, object]) -> bool:
    return "offset_f" not in v or _is_whole(v["offset_f"])


def resolve_time(v: object, kept: Sequence[KeptWord], edl: Edl) -> Resolved:
    """The output frame of the moment `v`.

    - a whole number (no `bool`) is that frame;
    - a word anchor is the `out_s_f` or `out_e_f` of the kept word with that id, plus `offset_f`
      (0 if absent); an id that is not among `kept` is `word_not_kept`;
    - a source anchor is the first output frame where frame `f` of `src` is heard
      (`source_to_output`), plus `offset_f`, and `repeats` says how many there are; none is
      `src_not_heard`;
    - any other form, or a key that is not part of it, is `shape`."""
    if isinstance(v, int) and not isinstance(v, bool):
        return Resolved(v, None, 1)
    if not isinstance(v, dict) or not has_time_shape(v):
        return Resolved(None, "shape", 0)
    offset: int = v.get("offset_f", 0)
    if "word" in v:
        word = next((w for w in kept if w.id == v["word"]), None)
        if word is None:
            return Resolved(None, "word_not_kept", 0)
        edge = word.out_s_f if v["edge"] == "start" else word.out_e_f
        return Resolved(edge + offset, None, 1)
    heard = source_to_output(edl, str(v["src"]), int(v["f"]))
    if not heard:
        return Resolved(None, "src_not_heard", 0)
    return Resolved(heard[0] + offset, None, len(heard))
