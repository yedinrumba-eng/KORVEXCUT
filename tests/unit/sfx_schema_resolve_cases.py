"""The A04 to A08 cases of `test_sfx_schema.py` (spec S1.8a row 3, 001.15), the codes that
`resolve_events` gives: a word or a frame that cannot be found, a frame that is heard several times,
a time or a window outside the video and a sound that is cut. Collected by that module (300-line
rule), which also takes `_doc` and `_event` from here. No ffmpeg: the EDL is the example of the spec
(345 frames at 30 fps; `a1` frames 60-239 are heard from output frame 30).
"""

import copy
from typing import Any

import pytest

from kcut.audio.sfx_events import resolve_events
from kcut.audio.sfx_schema import parse_sfx
from kcut.issues import Issue, exit_code
from tests.unit.edl_fakes import edit, parsed
from tests.unit.gfx_resolve_fakes import word


def _doc(change: Any = None, **top: Any) -> dict[str, Any]:
    document = copy.deepcopy({"schema": "kcut.sfx/1", "events": [{"type": "boom", "at": 10}]})
    document.update(top)
    if change is not None:
        change(document)
    return document


def _event(**fields: Any) -> dict[str, Any]:
    return _doc(lambda d: d["events"][0].update(fields))


def _resolve(
    data: dict[str, Any], words: Any = None, edl: Any = None
) -> tuple[list[Any], list[Issue]]:
    doc, found = parse_sfx(data)
    assert doc is not None, found
    return resolve_events(doc, words or [], edl or parsed(), 30)


def _codes(found: list[Issue]) -> list[tuple[str, str, str]]:
    return [(i.code, i.level, i.path) for i in found]


def test_sfx_schema_a04_a_word_that_the_cut_does_not_keep() -> None:
    at = {"word": "a1:w0099", "edge": "start"}
    events, found = _resolve(_event(at=at), [word(1, "hola", 40, 52)])
    assert _codes(found) == [("A04", "error", "events[0].at")] and events == []
    assert exit_code(found) == 1


def test_sfx_schema_a05_a_frame_of_a_source_that_is_not_heard() -> None:
    events, found = _resolve(_event(at={"src": "a1", "f": 10}))  # a1 frames 0-59 were cut
    assert _codes(found) == [("A05", "error", "events[0].at")] and events == []


def test_sfx_schema_a06_a_frame_heard_in_several_places_is_a_warning_and_the_first_is_used() -> (
    None
):
    clips = [
        {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 60, "out_f": 120, "why": "x"},
        {"kind": "voice", "at_f": 100, "src": "a1", "in_f": 90, "out_f": 150, "why": "x"},
    ]
    twice = parsed(edit(lambda d: d.update(clips=clips)))
    events, found = _resolve(_event(at={"src": "a1", "f": 100}), edl=twice)
    assert _codes(found) == [("A06", "warning", "events[0].at")]
    assert [e.at_f for e in events] == [40]  # the first: 0 + (100 - 60)
    assert exit_code(found) == 0  # a warning never changes the exit code


@pytest.mark.parametrize("at", [-1, 345, 400])
def test_sfx_schema_a07_a_time_outside_the_video(at: int) -> None:
    events, found = _resolve(_event(at=at))
    assert _codes(found) == [("A07", "error", "events[0].at")] and events == []


@pytest.mark.parametrize(("start", "end"), [(10, 10), (20, 10), (-1, 10), (0, 346), (346, 400)])
def test_sfx_schema_a07_a_window_has_to_fit_in_the_video(start: int, end: int) -> None:
    data = _doc(windows=[{"start": start, "end": end, "gain_db": 3.0}])
    events, found = _resolve(data)
    assert _codes(found) == [("A07", "error", "windows[0]")]
    assert [e.type for e in events] == ["boom"]  # the events are not the window's problem


def test_sfx_schema_a07_the_whole_video_is_a_window_that_fits() -> None:
    events, found = _resolve(_doc(windows=[{"start": 0, "end": 345, "gain_db": 3.0}]))
    assert found == [] and len(events) == 1


def test_sfx_schema_a08_part_of_the_sound_falls_outside_and_is_cut() -> None:
    late = _event(at=340)  # a boom of 27 frames, with 5 left
    events, found = _resolve(late)
    assert _codes(found) == [("A08", "warning", "events[0]")] and len(events) == 1
    early = _event(at=0, align="center")
    assert _codes(_resolve(early)[1]) == [("A08", "warning", "events[0]")]
    end = _event(type="kick", at=3, align="end")
    assert _codes(_resolve(end)[1]) == [("A08", "warning", "events[0]")]
    assert exit_code(_resolve(late)[1]) == 0


def test_sfx_schema_a08_a_sound_that_fits_has_no_warning() -> None:
    for at, align in ((0, "start"), (100, "center"), (100, "end"), (318, "start")):
        events, found = _resolve(_event(at=at, align=align))  # a boom: 27 frames long
        assert found == [] and len(events) == 1, (at, align)


def test_sfx_schema_a03_a_duration_over_the_frames_of_the_video_is_resolved_here() -> None:
    data = _doc(events=[{"type": "pad", "at": 0, "dur_f": 346}])
    events, found = _resolve(data)
    assert _codes(found) == [("A03", "error", "events[0].dur_f")] and events == []
    assert _resolve(_doc(events=[{"type": "pad", "at": 0, "dur_f": 345}]))[1] == []
