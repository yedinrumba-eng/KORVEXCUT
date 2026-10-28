"""`resolve_events` (spec S1.8a row 4, 001.15): the events of `sfx.json` in output frames, with what
each type has by default. The anchors are those of `kcut.anchors` (a word that the cut keeps, a
frame of a source), `align` is kept, and `dur_f`, `gain`, `seed`, `freq` and `rate` are the given
ones or the defaults of the type (`SFX`). No ffmpeg: the EDL is the example of the spec (345 frames
at 30 fps; `a1` frames 60-239 are heard from output frame 30) and the words are made by the test.
"""

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from kcut.audio.sfx_events import SfxEvent, resolve_events
from kcut.audio.sfx_library import SFX
from kcut.audio.sfx_schema import parse_sfx
from kcut.issues import Issue
from kcut.timebase import ms_to_f_round
from tests.fixtures.synth_audio import write_sfx_plan
from tests.unit.edl_fakes import parsed
from tests.unit.gfx_resolve_fakes import word

WORDS = [word(1, "hola", 40, 52), word(31, "mundo", 90, 100)]
DEFAULT_GAIN = {
    "whoosh": 0.45, "boom": 0.75, "pop": 0.6, "shimmer": 0.6, "key": 0.6, "click": 0.7,
    "kick": 0.9, "hat": 0.95, "pad": 0.55, "typing": 0.85, "riser": 0.45, "blip8": 0.7,
    "powerup": 0.7,
}  # fmt: skip


def _plan(*events: dict[str, Any], **top: Any) -> dict[str, Any]:
    return {"schema": "kcut.sfx/1", "events": list(events)} | top


def _resolve(
    *events: dict[str, Any], fps: int = 30, words: Any = WORDS
) -> tuple[list[SfxEvent], list[Issue]]:
    doc, found = parse_sfx(_plan(*events))
    assert doc is not None, found
    return resolve_events(doc, words, parsed(), fps)


def _one(event: dict[str, Any], fps: int = 30) -> SfxEvent:
    events, found = _resolve(event, fps=fps)
    assert len(events) == 1, found
    return events[0]


def test_sfx_events_the_resolved_event_has_exactly_the_fields_of_the_spec() -> None:
    names = [f.name for f in dataclasses.fields(SfxEvent)]
    assert names == ["type", "at_f", "align", "dur_f", "gain", "seed", "freq", "rate"]
    event = _one({"type": "boom", "at": 10})
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.at_f = 3  # type: ignore[misc]


def test_sfx_events_a_frame_is_that_frame_and_the_order_of_the_file_is_kept() -> None:
    events, found = _resolve(
        {"type": "kick", "at": 90}, {"type": "pop", "at": 5}, {"type": "hat", "at": 200}
    )
    assert found == [] and [(e.type, e.at_f) for e in events] == [
        ("kick", 90),
        ("pop", 5),
        ("hat", 200),
    ]


@pytest.mark.parametrize(
    ("anchor", "frame"),
    [
        ({"word": "a1:w0001", "edge": "start"}, 40),
        ({"word": "a1:w0001", "edge": "end"}, 52),
        ({"word": "a1:w0001", "edge": "start", "offset_f": 3}, 43),
        ({"word": "a1:w0001", "edge": "end", "offset_f": -2}, 50),
        ({"word": "a1:w0031", "edge": "start", "offset_f": 0}, 90),
    ],
)
def test_sfx_events_a_word_anchor_is_the_edge_of_the_kept_word_plus_the_offset(
    anchor: dict[str, Any], frame: int
) -> None:
    assert _one({"type": "pop", "at": anchor}).at_f == frame


@pytest.mark.parametrize(
    ("anchor", "frame"),
    [
        ({"src": "a1", "f": 60}, 30),  # a1 frame 60 is the first one heard, at output frame 30
        ({"src": "a1", "f": 100}, 70),
        ({"src": "a1", "f": 100, "offset_f": 5}, 75),
        ({"src": "a1", "f": 239}, 209),
    ],
)
def test_sfx_events_a_source_anchor_is_the_frame_where_it_is_heard_plus_the_offset(
    anchor: dict[str, Any], frame: int
) -> None:
    assert _one({"type": "pop", "at": anchor}).at_f == frame


def test_sfx_events_align_is_kept_and_is_start_by_default() -> None:
    assert _one({"type": "boom", "at": 50}).align == "start"
    for align in ("start", "center", "end"):
        assert _one({"type": "boom", "at": 100, "align": align}).align == align


@pytest.mark.parametrize("kind", ["boom", "pop", "key", "click", "kick", "hat", "blip8", "powerup"])
def test_sfx_events_dur_f_is_none_in_the_types_of_a_fixed_length(kind: str) -> None:
    assert _one({"type": kind, "at": 100}).dur_f is None


@pytest.mark.parametrize(("fps", "whoosh", "shimmer"), [(24, 11, 26), (30, 14, 33), (60, 27, 66)])
def test_sfx_events_whoosh_and_shimmer_last_what_their_default_milliseconds_are_in_frames(
    fps: int, whoosh: int, shimmer: int
) -> None:
    assert _one({"type": "whoosh", "at": 10}, fps).dur_f == whoosh == ms_to_f_round(450, fps)
    assert _one({"type": "shimmer", "at": 10}, fps).dur_f == shimmer == ms_to_f_round(1100, fps)


def test_sfx_events_dur_f_the_given_one_wins_and_the_required_ones_have_it() -> None:
    assert _one({"type": "whoosh", "at": 10, "dur_f": 20}).dur_f == 20
    assert _one({"type": "shimmer", "at": 10, "dur_f": 1}).dur_f == 1
    for kind in ("pad", "typing", "riser"):
        assert _one({"type": kind, "at": 10, "dur_f": 25}).dur_f == 25


def test_sfx_events_gain_is_the_given_one_or_the_default_of_the_type() -> None:
    assert sorted(DEFAULT_GAIN) == sorted(SFX)
    for kind, gain in DEFAULT_GAIN.items():
        extra = {"dur_f": 10} if SFX[kind].requires_dur else {}
        assert _one({"type": kind, "at": 100, **extra}).gain == gain, kind
    assert _one({"type": "boom", "at": 100, "gain": 1.5}).gain == 1.5
    assert _one({"type": "boom", "at": 100, "gain": 0}).gain == 0.0  # 0 is given, not missing
    assert _one({"type": "boom", "at": 100, "gain": 2}).gain == 2.0


@pytest.mark.parametrize(
    ("kind", "seed"),
    [("whoosh", 1), ("boom", 7), ("key", 0), ("hat", 0), ("typing", 55), ("riser", 77)],
)
def test_sfx_events_seed_is_the_given_one_or_the_default_of_the_types_that_have_one(
    kind: str, seed: int
) -> None:
    extra = {"dur_f": 10} if SFX[kind].requires_dur else {}
    event = _one({"type": kind, "at": 100, **extra})
    assert event.seed == seed and isinstance(event.seed, int)
    assert _one({"type": kind, "at": 100, "seed": 99, **extra}).seed == 99
    assert _one({"type": kind, "at": 100, "seed": 0, **extra}).seed == 0  # 0 is given


def test_sfx_events_seed_is_none_in_the_types_that_have_none() -> None:
    for kind in ("pop", "shimmer", "click", "kick", "pad", "blip8", "powerup"):
        extra = {"dur_f": 10} if SFX[kind].requires_dur else {}
        assert _one({"type": kind, "at": 100, **extra}).seed is None, kind


def test_sfx_events_freq_and_rate_are_the_given_or_the_default_or_none() -> None:
    pop = _one({"type": "pop", "at": 100})
    assert (pop.freq, pop.rate) == (820.0, None) and isinstance(pop.freq, float)
    assert _one({"type": "pop", "at": 100, "freq": 700}).freq == 700.0
    typing = _one({"type": "typing", "at": 100, "dur_f": 20})
    assert (typing.rate, typing.freq, typing.seed) == (13.0, None, 55)
    assert _one({"type": "typing", "at": 100, "dur_f": 20, "rate": 8}).rate == 8.0
    for kind in ("boom", "whoosh", "riser", "kick"):
        extra = {"dur_f": 10} if SFX[kind].requires_dur else {}
        event = _one({"type": kind, "at": 100, **extra})
        assert event.freq is None and event.rate is None, kind


def test_sfx_events_a_seed_in_a_pop_is_an_a03_and_there_is_no_document() -> None:
    doc, found = parse_sfx(_plan({"type": "pop", "at": 10, "seed": 3}))
    assert doc is None and [(i.code, i.path) for i in found] == [("A03", "events[0].seed")]


def test_sfx_events_an_event_with_an_error_is_left_out_and_the_others_stay() -> None:
    events, found = _resolve(
        {"type": "kick", "at": 30},
        {"type": "pop", "at": {"word": "a1:w0099", "edge": "start"}},  # A04
        {"type": "hat", "at": 500},  # A07
        {"type": "pad", "at": 10, "dur_f": 400},  # A03
        {"type": "click", "at": 60},
    )
    assert [e.type for e in events] == ["kick", "click"]
    assert [(i.code, i.path) for i in found] == [
        ("A04", "events[1].at"),
        ("A07", "events[2].at"),
        ("A03", "events[3].dur_f"),
    ]


def test_sfx_events_the_messages_say_which_event_by_position_and_do_not_repeat_the_file() -> None:
    events, found = _resolve({"type": "pop", "at": {"word": "IGNORE-PREVIOUS", "edge": "start"}})
    assert events == [] and "IGNORE" not in " ".join(i.path + i.message_es for i in found)
    assert all(i.message_es for i in found)


def test_sfx_events_no_words_are_needed_for_frames_and_source_anchors() -> None:
    doc, _ = parse_sfx(
        _plan({"type": "pop", "at": 10}, {"type": "pop", "at": {"src": "a1", "f": 70}})
    )
    assert doc is not None
    events, found = resolve_events(doc, [], parsed(), 30)
    assert found == [] and [e.at_f for e in events] == [10, 40]


def test_sfx_events_the_plan_of_the_synthetic_project_is_valid_and_resolves_clean(
    tmp_path: Path,
) -> None:
    """`write_sfx_plan`: the example of the spec with whole frames, and a kick and a hi-hat that
    alternate every 8 frames from 210 to 270: 13 events, with no issue at all."""
    document = write_sfx_plan(tmp_path)
    data = json.loads((tmp_path / "edit" / "sfx.json").read_text(encoding="utf-8"))
    assert data == document and len(data["events"]) == 13 and len(data["windows"]) == 1
    doc, found = parse_sfx(data)
    assert doc is not None and found == []
    events, issues = resolve_events(doc, [], parsed(), 30)
    assert issues == [] and len(events) == 13
    beats = events[5:]
    assert [e.type for e in beats] == ["kick", "hat"] * 4
    assert [e.at_f for e in beats] == list(range(210, 270, 8))


def test_sfx_events_dur_f_huge_the_a03_does_not_carry_the_whole_number() -> None:
    """001.36, point 3: a `dur_f` of 10**300 is an A03 like any other, whose message gives the
    number as `describe_value` does (its first digits and how many it has), not its 301 digits."""
    events, found = _resolve({"type": "pad", "at": 10, "dur_f": 10**300})
    assert events == [] and [(i.code, i.path) for i in found] == [("A03", "events[0].dur_f")]
    message = found[0].message_es
    assert len(message) <= 120, len(message)
    assert "0" * 30 not in message and "301" in message  # how many digits it has
