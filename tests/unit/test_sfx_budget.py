"""The synthesis has a budget (spec S1.8b step 0, 001.36 point 2; row 13). A `dur_f` could last
as long as the video: a `pad` of 20 minutes asks for about 2.5 GB. 30 s are enough for "a short
cushion" and "a rise before a hit", and the 1200 s of the whole plan keep the CPU to about 70 s
(001.37, point 9: it was 600 s, and 2000 `kick` last about 615 s, which the spec says is enough for
a video of 10 minutes). An event of a type with `dur_f` that lasts more than 30 s is an A03; if all
the events together last more than 1200 s it is one A03 in `events` and nothing is made. The
`MemoryError` of the synthesis is in `tests/integration/test_sfx_budget_mix.py` (it needs
`kcut mix`).
"""

import dataclasses
from typing import Any

import pytest

from kcut.audio import sfx_events
from kcut.audio.sfx_events import MAX_SFX_DUR_S, MAX_SFX_TOTAL_S, SfxEvent, resolve_events
from kcut.audio.sfx_library import SFX
from kcut.audio.sfx_schema import parse_sfx
from kcut.edl.model import Edl
from kcut.issues import Issue
from tests.unit.edl_fakes import parsed

LONG = 30 * 30  # 30 s at 30 fps
DUR_TEXT = "dura más de 30 s; un efecto va hasta 30 s"
TOTAL_TEXT = "los efectos suman más de 1200 s de audio"  # 001.37: was 600


def _edl(frames: int = 3000) -> Edl:
    return dataclasses.replace(parsed(), frames=frames)


def _resolve(*events: dict[str, Any], frames: int = 3000) -> tuple[list[SfxEvent], list[Issue]]:
    doc, found = parse_sfx({"schema": "kcut.sfx/1", "events": list(events)})
    assert doc is not None, found
    return resolve_events(doc, [], _edl(frames), 30)


def test_sfx_budget_the_constants_are_the_ones_of_the_spec() -> None:
    assert (MAX_SFX_DUR_S, MAX_SFX_TOTAL_S) == (30, 1200)  # 001.37: the total was 600
    assert sfx_events.MAX_SFX_DUR_S == 30


def test_sfx_budget_a_pad_of_30_seconds_is_fine_and_30_seconds_and_a_frame_is_a03() -> None:
    events, found = _resolve({"type": "pad", "at": 10, "dur_f": LONG})
    assert found == [] and [e.dur_f for e in events] == [LONG]
    events, found = _resolve({"type": "pad", "at": 10, "dur_f": LONG + 1})
    assert events == []
    assert [(i.code, i.level, i.path, i.message_es) for i in found] == [
        ("A03", "error", "events[0].dur_f", DUR_TEXT)
    ]


@pytest.mark.parametrize("kind", ["pad", "typing", "riser", "whoosh", "shimmer"])
def test_sfx_budget_every_type_with_a_dur_f_has_the_same_limit(kind: str) -> None:
    assert _resolve({"type": kind, "at": 10, "dur_f": LONG})[1] == []
    _, found = _resolve({"type": kind, "at": 10, "dur_f": LONG + 1})
    assert [(i.code, i.path, i.message_es) for i in found] == [("A03", "events[0].dur_f", DUR_TEXT)]


def test_sfx_budget_whoosh_and_shimmer_with_no_dur_f_are_never_over() -> None:
    events, found = _resolve({"type": "whoosh", "at": 10}, {"type": "shimmer", "at": 20})
    assert found == [] and [e.dur_f for e in events] == [14, 33]


def test_sfx_budget_the_limit_goes_by_seconds_and_not_by_frames() -> None:
    """At 60 fps 30 s are 1800 frames (`dur_f * spf` against `30 * 48000`)."""
    doc, _ = parse_sfx(
        {"schema": "kcut.sfx/1", "events": [{"type": "pad", "at": 0, "dur_f": 1800}]}
    )
    assert doc is not None
    _, found = resolve_events(doc, [], dataclasses.replace(parsed(), frames=4000, fps=60), 60)
    assert found == []
    doc, _ = parse_sfx(
        {"schema": "kcut.sfx/1", "events": [{"type": "pad", "at": 0, "dur_f": 1801}]}
    )
    assert doc is not None
    _, found = resolve_events(doc, [], dataclasses.replace(parsed(), frames=4000, fps=60), 60)
    assert [i.message_es for i in found] == [DUR_TEXT]


def test_sfx_budget_41_events_of_30_seconds_are_one_a03_in_events_and_nothing_is_made() -> None:
    # 001.37: was 21 events (630 s) against 600 s
    events, found = _resolve(*[{"type": "pad", "at": i, "dur_f": LONG} for i in range(41)])
    assert events == []  # 1230 s: nothing is left to synthesize
    assert [(i.code, i.level, i.path, i.message_es) for i in found] == [
        ("A03", "error", "events", TOTAL_TEXT)
    ]


def test_sfx_budget_40_events_of_30_seconds_are_exactly_1200_s_and_pass() -> None:
    # 001.37: was 20 events (600 s)
    events, found = _resolve(*[{"type": "pad", "at": i, "dur_f": LONG} for i in range(40)])
    assert found == [] and len(events) == 40


def test_sfx_budget_the_fixed_types_count_in_the_total_with_their_own_length() -> None:
    """39 pads of 30 s are 1170 s; a `boom` is 0.9 s (43200 samples): 100 of them make 90 s."""
    pads = [{"type": "pad", "at": i, "dur_f": LONG} for i in range(39)]  # 001.37: was 19
    booms = [{"type": "boom", "at": i} for i in range(100)]
    events, found = _resolve(*pads, *booms)
    assert [i.message_es for i in found] == [TOTAL_TEXT] and events == []
    events, found = _resolve(*pads, *booms[:20])  # 1170 s + 18 s
    assert found == [] and len(events) == 59  # 001.37: was 39


def test_sfx_budget_2000_kicks_are_over_the_old_total_and_inside_the_budget() -> None:
    """001.37, point 9: the spec says 2000 events are enough for a video of 10 minutes, and 2000
    `kick` (15360 samples, 0.32 s each: 640 s, "about 615 s" in the spec) are over the old total of
    600 s and under the new one."""
    kicks = [{"type": "kick", "at": i} for i in range(2000)]
    events, found = _resolve(*kicks)
    assert found == [] and len(events) == 2000
    fixed = SFX["kick"].fixed_n
    assert fixed is not None and 600 < 2000 * fixed / 48000 < MAX_SFX_TOTAL_S


def test_sfx_budget_an_event_with_an_error_does_not_count_in_the_total() -> None:
    good = [{"type": "pad", "at": i, "dur_f": LONG} for i in range(40)]  # 001.37: was 20
    bad = {"type": "pad", "at": 5, "dur_f": LONG + 1}  # an A03 of its own, left out of the sum
    events, found = _resolve(*good, bad)
    assert len(events) == 40  # 001.37: was 20
    assert [(i.code, i.path) for i in found] == [("A03", "events[40].dur_f")]  # 001.37: was [20]


def test_sfx_budget_the_other_errors_of_the_events_stay_with_the_total() -> None:
    far = {"type": "kick", "at": 99999}  # an A07
    pads = [{"type": "pad", "at": i, "dur_f": LONG} for i in range(41)]  # 001.37: was 21
    events, found = _resolve(far, *pads)
    assert events == []
    assert [(i.code, i.path) for i in found] == [("A07", "events[0].at"), ("A03", "events")]


def test_sfx_budget_a_dur_f_over_the_frames_of_the_video_keeps_its_own_message() -> None:
    _, found = _resolve({"type": "pad", "at": 10, "dur_f": 5000}, frames=3000)
    assert [(i.code, i.path) for i in found] == [("A03", "events[0].dur_f")]
    assert "entre 1 y 3000" in found[0].message_es  # not the 30 s one: the first reason wins
