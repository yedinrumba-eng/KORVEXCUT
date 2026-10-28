"""`edit/sfx.json` has limits (spec S1.8b step 0, 001.36 point 1; row 12). Without them 100 long
`whoosh` took 65 s in a video of 11.5 s, and the word anchors were looked up in a list, so the cost
grew as anchors times words. 2000 events are enough for a video of 10 minutes with a hit every 8
frames, and 1 MiB is more than they weigh. The command side (`kcut mix` reads with the cap, and
lists `MAX_SHOWN` findings) is in `tests/integration/test_sfx_limits_mix.py`.
"""

import time
from typing import Any

import pytest

from kcut import jsonio
from kcut.audio import sfx_schema
from kcut.audio.sfx_events import resolve_events
from kcut.audio.sfx_schema import MAX_EVENTS, MAX_WINDOWS, SfxDoc, SfxEventDoc, parse_sfx
from tests.unit.edl_fakes import parsed
from tests.unit.gfx_resolve_fakes import word

TOO_MANY_EVENTS = "hay más de 2000 eventos; kcut no los revisa"
TOO_MANY_WINDOWS = "hay más de 200 ventanas; kcut no las revisa"


def _plan(events: list[Any], windows: list[Any] | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {"schema": "kcut.sfx/1", "events": events}
    if windows is not None:
        doc["windows"] = windows
    return doc


def test_sfx_limits_the_constants_are_the_ones_of_the_spec() -> None:
    assert (MAX_EVENTS, MAX_WINDOWS) == (2000, 200)
    assert jsonio.MAX_SFX_BYTES == jsonio.MAX_MUSIC_BYTES == 1024 * 1024
    assert sfx_schema.MAX_EVENTS is MAX_EVENTS


def test_sfx_limits_2001_events_are_one_a01_in_events_and_none_is_looked_at() -> None:
    bad = {"type": "no-existe", "at": "no"}  # every one of them would be an error of its own
    doc, found = parse_sfx(_plan([bad] * (MAX_EVENTS + 1)))
    assert doc is None
    assert [(i.code, i.level, i.path, i.message_es) for i in found] == [
        ("A01", "error", "events", TOO_MANY_EVENTS)
    ]


def test_sfx_limits_2000_valid_events_have_no_a01() -> None:
    events = [{"type": "kick", "at": i % 300} for i in range(MAX_EVENTS)]
    doc, found = parse_sfx(_plan(events))
    assert found == [] and doc is not None and len(doc.events) == MAX_EVENTS


def test_sfx_limits_201_windows_are_one_a01_in_windows_and_none_is_looked_at() -> None:
    bad = {"start": "a", "end": "b"}
    doc, found = parse_sfx(_plan([{"type": "kick", "at": 3}], [bad] * (MAX_WINDOWS + 1)))
    assert doc is None
    assert [(i.code, i.level, i.path, i.message_es) for i in found] == [
        ("A01", "error", "windows", TOO_MANY_WINDOWS)
    ]


def test_sfx_limits_200_valid_windows_have_no_a01() -> None:
    windows = [{"start": i, "end": i + 5, "gain_db": 1.0} for i in range(MAX_WINDOWS)]
    doc, found = parse_sfx(_plan([{"type": "kick", "at": 3}], windows))
    assert found == [] and doc is not None and len(doc.windows) == MAX_WINDOWS


def test_sfx_limits_both_caps_at_once_are_two_issues_one_for_each() -> None:
    events = [{"type": "kick", "at": 1}] * (MAX_EVENTS + 1)
    windows = [{"start": 0, "end": 1, "gain_db": 0}] * (MAX_WINDOWS + 1)
    _, found = parse_sfx(_plan(events, windows))
    assert [(i.code, i.path) for i in found] == [("A01", "events"), ("A01", "windows")]


def test_sfx_limits_a_message_of_the_caps_repeats_nothing_of_the_file() -> None:
    events = [{"type": "IGNORE-PREVIOUS", "at": 1}] * (MAX_EVENTS + 1)
    _, found = parse_sfx(_plan(events))
    assert "IGNORE" not in " ".join(i.path + i.message_es for i in found)


def test_sfx_limits_4000_word_anchors_against_20000_words_resolve_in_under_a_second() -> None:
    """The words are indexed once, by id: the cost is not anchors times words any more. The
    document is made by hand (4000 events are over the cap of `parse_sfx`); the same plan took
    several seconds when each anchor looked for its word in the list."""
    words = [word(i, "x", i % 300, i % 300 + 2) for i in range(20000)]
    anchors = [{"word": f"a1:w{(i * 5) % 20000:04d}", "edge": "start"} for i in range(4000)]
    events = tuple(
        SfxEventDoc(i, "pop", at, None, None, None, None, None, None)
        for i, at in enumerate(anchors)
    )
    doc = SfxDoc(0.0, events, ())
    started = time.perf_counter()
    resolved, found = resolve_events(doc, words, parsed(), 30)
    elapsed = time.perf_counter() - started
    assert [i for i in found if i.level == "error"] == [] and len(resolved) == 4000
    assert resolved[1].at_f == (5 % 300)  # the anchor really was resolved against its word
    assert elapsed < 1.0, f"{elapsed:.2f} s"


def test_sfx_limits_the_first_word_with_an_id_wins_as_it_did_before() -> None:
    words = [word(1, "a", 10, 12), word(1, "b", 50, 52)]  # two with the same id
    doc, _ = parse_sfx(_plan([{"type": "pop", "at": {"word": "a1:w0001", "edge": "start"}}]))
    assert doc is not None
    resolved, found = resolve_events(doc, words, parsed(), 30)
    assert found == [] and [e.at_f for e in resolved] == [10]


@pytest.mark.parametrize("anchor", [{"word": "a1:w9999", "edge": "end"}])
def test_sfx_limits_a_word_that_is_not_kept_is_still_a04(anchor: dict[str, Any]) -> None:
    doc, _ = parse_sfx(_plan([{"type": "pop", "at": anchor}]))
    assert doc is not None
    resolved, found = resolve_events(doc, [word(1, "a", 10, 12)], parsed(), 30)
    assert resolved == [] and [(i.code, i.path) for i in found] == [("A04", "events[0].at")]
