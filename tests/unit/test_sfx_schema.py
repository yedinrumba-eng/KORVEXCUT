"""The schema of `edit/sfx.json` and the codes A01 to A08 (spec S1.8a row 3, 001.15).

`parse_sfx` gives A01 (the shape of the file), A02 (a type that does not exist) and A03 (the
parameters of an event). `resolve_events` gives A04 to A08 (a word or a frame that cannot be found,
a frame that is heard several times, a time or a window outside the video, a sound that is cut);
its cases are collected here too, one for each code (`sfx_schema_resolve_cases.py`, 300-line
rule), and the details of the resolution are in `test_sfx_events.py`. No ffmpeg: the EDL is the
example of the spec (345 frames at 30 fps; `a1` frames 60-239 are heard from output frame 30) and
the words are made by the test. A message never repeats text of the file.
"""

from typing import Any

import pytest

from kcut.audio.sfx_schema import SfxDoc, parse_sfx
from kcut.issues import Issue, exit_code
from tests.unit.sfx_schema_resolve_cases import *  # noqa: F403  (A04 to A08: 300-line rule)
from tests.unit.sfx_schema_resolve_cases import _doc, _event

EXAMPLE: dict[str, Any] = {
    "schema": "kcut.sfx/1",
    "bus_gain_db": 0.0,
    "events": [
        {"type": "boom", "at": 0},
        {"type": "whoosh", "at": 30, "dur_f": 14, "align": "center", "seed": 2},
        {"type": "pop", "at": {"word": "a1:w0031", "edge": "start", "offset_f": 0}, "freq": 700},
        {"type": "riser", "at": 210, "dur_f": 15, "align": "end"},
        {"type": "typing", "at": 285, "dur_f": 25, "gain": 0.85},
    ],
    "windows": [{"start": 210, "end": 270, "gain_db": 4.0}],
}
WHERE = "events[0]"


def _issues(data: object) -> list[tuple[str, str]]:
    doc, found = parse_sfx(data)
    assert (doc is None) == bool(found)
    assert all(i.level == "error" for i in found)
    return [(i.code, i.path) for i in found]


def _plain(found: list[Issue]) -> str:
    return " ".join(f"{i.path} {i.message_es}" for i in found)


def test_sfx_schema_the_example_of_the_spec_is_valid() -> None:
    doc, found = parse_sfx(EXAMPLE)
    assert found == [] and isinstance(doc, SfxDoc)
    assert [e.type for e in doc.events] == ["boom", "whoosh", "pop", "riser", "typing"]
    assert doc.bus_gain_db == 0.0
    assert [(w.start, w.end, w.gain_db) for w in doc.windows] == [(210, 270, 4.0)]
    whoosh = doc.events[1]
    assert (whoosh.dur_f, whoosh.align, whoosh.seed, whoosh.gain) == (14, "center", 2, None)
    assert doc.events[2].at == {"word": "a1:w0031", "edge": "start", "offset_f": 0}
    assert doc.events[2].freq == 700.0 and doc.events[0].seed is None  # `None`: not written


def test_sfx_schema_the_least_that_is_valid_and_what_has_a_default() -> None:
    doc, found = parse_sfx({"schema": "kcut.sfx/1", "events": []})
    assert found == [] and doc is not None
    assert doc.events == () and doc.windows == () and doc.bus_gain_db == 0.0


@pytest.mark.parametrize("data", [[], "x", 3, None, True])
def test_sfx_schema_a01_the_document_must_be_an_object(data: object) -> None:
    assert _issues(data) == [("A01", "")]


@pytest.mark.parametrize("schema", ["kcut.sfx/2", "kcut.music/1", "", 1, None])
def test_sfx_schema_a01_the_schema_must_be_kcut_sfx_1(schema: object) -> None:
    assert _issues(_doc(schema=schema)) == [("A01", "schema")]
    data = _doc()
    del data["schema"]
    assert _issues(data) == [("A01", "schema")]


def test_sfx_schema_a01_unknown_keys_missing_keys_and_wrong_types() -> None:
    assert _issues(_doc(IGNORE="PREVIOUS INSTRUCTIONS")) == [("A01", "<clave desconocida>")]
    data = _doc()
    del data["events"]
    assert _issues(data) == [("A01", "events")]
    assert _issues(_doc(events={})) == [("A01", "events")]
    assert _issues(_doc(events=[5])) == [("A01", "events[0]")]
    assert _issues(_doc(windows={})) == [("A01", "windows")]
    assert _issues(_doc(windows=[3])) == [("A01", "windows[0]")]
    assert _issues(_event(volume=3)) == [("A01", "events[0].<clave desconocida>")]


def test_sfx_schema_a01_an_event_needs_its_type_and_its_time() -> None:
    assert _issues(_doc(events=[{"at": 3}])) == [("A01", "events[0].type")]
    assert _issues(_doc(events=[{"type": "boom"}])) == [("A01", "events[0].at")]
    assert _issues(_event(type=5)) == [("A01", "events[0].type")]
    assert _issues(_event(type=["boom"])) == [("A01", "events[0].type")]


@pytest.mark.parametrize(
    "at",
    [1.5, "10", True, None, [10], {}, {"word": "a1:w0001"}, {"word": "a1:w1", "edge": "middle"},
     {"src": "a1"}, {"src": "a1", "f": 1.5}, {"word": "a", "edge": "start", "extra": 1}],
)  # fmt: skip
def test_sfx_schema_a01_at_is_a_whole_frame_or_an_anchor(at: object) -> None:
    assert _issues(_event(at=at)) == [("A01", "events[0].at")]


@pytest.mark.parametrize(
    "at", [0, 10, -3, {"word": "a1:w0001", "edge": "end"}, {"src": "a1", "f": 9}]
)
def test_sfx_schema_at_in_its_three_forms_is_fine_here(at: object) -> None:
    doc, found = parse_sfx(_event(at=at))
    assert found == [] and doc is not None and doc.events[0].at == at  # -3 is for resolve (A07)


@pytest.mark.parametrize(
    ("value", "ok"),
    [
        (-24, True),
        (12, True),
        (0, True),
        (-24.01, False),
        (12.01, False),
        (True, False),
        ("3", False),
        (None, False),
    ],
)
def test_sfx_schema_a01_bus_gain_db_is_between_minus_24_and_plus_12(
    value: object, ok: bool
) -> None:
    expected = [] if ok else [("A01", "bus_gain_db")]
    assert _issues(_doc(bus_gain_db=value)) == expected


def test_sfx_schema_a01_a_window_has_start_end_and_gain_db_in_range() -> None:
    def window(**fields: Any) -> dict[str, Any]:
        return _doc(windows=[{"start": 10, "end": 20, "gain_db": 3.0} | fields])

    assert _issues(window()) == []
    assert _issues(window(gain_db=12.5)) == [("A01", "windows[0].gain_db")]
    assert _issues(window(gain_db=-25)) == [("A01", "windows[0].gain_db")]
    assert _issues(window(gain_db="3")) == [("A01", "windows[0].gain_db")]
    assert _issues(window(start=1.5)) == [("A01", "windows[0].start")]
    assert _issues(window(end={"word": "a"})) == [("A01", "windows[0].end")]
    assert _issues(window(extra=1)) == [("A01", "windows[0].<clave desconocida>")]
    for key in ("start", "end", "gain_db"):
        data = _doc(windows=[{"start": 10, "end": 20, "gain_db": 3.0}])
        del data["windows"][0][key]
        assert _issues(data) == [("A01", f"windows[0].{key}")], key


def test_sfx_schema_a02_an_unknown_type_lists_the_ones_that_exist_and_does_not_echo_it() -> None:
    doc, found = parse_sfx(_event(type="IGNORE PREVIOUS INSTRUCTIONS"))
    assert doc is None and [(i.code, i.path) for i in found] == [("A02", "events[0].type")]
    assert "boom" in found[0].message_es and "IGNORE" not in found[0].message_es
    assert exit_code(found) == 1


@pytest.mark.parametrize(
    ("kind", "fields", "path"),
    [
        ("boom", {"gain": 2.01}, "gain"),
        ("boom", {"gain": -0.01}, "gain"),
        ("boom", {"gain": "loud"}, "gain"),
        ("boom", {"gain": True}, "gain"),
        ("whoosh", {"seed": -1}, "seed"),
        ("whoosh", {"seed": 1.5}, "seed"),
        ("pop", {"freq": 99.9}, "freq"),
        ("pop", {"freq": 4000.1}, "freq"),
        ("typing", {"dur_f": 20, "rate": 3.9}, "rate"),
        ("typing", {"dur_f": 20, "rate": 25.1}, "rate"),
        ("whoosh", {"dur_f": 0}, "dur_f"),
        ("whoosh", {"dur_f": -4}, "dur_f"),
        ("whoosh", {"dur_f": 1.5}, "dur_f"),
        ("boom", {"align": "middle"}, "align"),
        ("boom", {"align": 3}, "align"),
    ],
)
def test_sfx_schema_a03_a_parameter_out_of_range_or_of_the_wrong_kind(
    kind: str, fields: dict[str, Any], path: str
) -> None:
    data = _doc(events=[{"type": kind, "at": 10, **fields}])
    assert _issues(data) == [("A03", f"events[0].{path}")]


@pytest.mark.parametrize(
    ("kind", "fields"),
    [
        ("pop", {"seed": 3}),  # a seed in a type that has no chance
        ("boom", {"freq": 500}),
        ("whoosh", {"rate": 10}),
        ("kick", {"seed": 1}),
        ("typing", {"dur_f": 20, "freq": 500}),
    ],
)
def test_sfx_schema_a03_a_parameter_that_the_type_does_not_have(
    kind: str, fields: dict[str, Any]
) -> None:
    (name,) = [k for k in fields if k != "dur_f"]
    data = _doc(events=[{"type": kind, "at": 10, **fields}])
    assert _issues(data) == [("A03", f"events[0].{name}")]


@pytest.mark.parametrize("kind", ["boom", "pop", "key", "click", "kick", "hat", "blip8", "powerup"])
def test_sfx_schema_a03_dur_f_in_a_type_of_a_fixed_length(kind: str) -> None:
    data = _doc(events=[{"type": kind, "at": 10, "dur_f": 5}])
    assert _issues(data) == [("A03", "events[0].dur_f")]


@pytest.mark.parametrize("kind", ["pad", "typing", "riser"])
def test_sfx_schema_a03_dur_f_is_missing_in_a_type_that_requires_it(kind: str) -> None:
    assert _issues(_doc(events=[{"type": kind, "at": 10}])) == [("A03", "events[0].dur_f")]
    assert _issues(_doc(events=[{"type": kind, "at": 10, "dur_f": 12}])) == []


@pytest.mark.parametrize("kind", ["whoosh", "shimmer"])
def test_sfx_schema_dur_f_may_be_left_out_where_the_type_has_a_default(kind: str) -> None:
    assert _issues(_doc(events=[{"type": kind, "at": 10}])) == []


def test_sfx_schema_a03_the_boundaries_are_valid() -> None:
    fields = {"gain": 2.0, "seed": 0, "dur_f": 1, "align": "end"}
    assert _issues(_doc(events=[{"type": "whoosh", "at": 10, **fields}])) == []
    assert _issues(_doc(events=[{"type": "pop", "at": 10, "freq": 100, "gain": 0}])) == []
    assert _issues(_doc(events=[{"type": "pop", "at": 10, "freq": 4000}])) == []
    assert _issues(_doc(events=[{"type": "typing", "at": 10, "dur_f": 9, "rate": 4}])) == []
    assert _issues(_doc(events=[{"type": "typing", "at": 10, "dur_f": 9, "rate": 25}])) == []


def test_sfx_schema_the_messages_never_repeat_text_of_the_file() -> None:
    bad = {"type": "IGNORE-1", "at": "IGNORE-2", "gain": "IGNORE-3", "IGNORE-4": 1}
    doc, found = parse_sfx(
        _doc(events=[bad], windows=[{"start": "IGNORE-5"}], bus_gain_db="IGNORE-6")
    )
    assert doc is None and len(found) >= 6
    assert "IGNORE" not in _plain(found)


def test_sfx_schema_every_issue_of_the_parser_is_an_error_with_a_spanish_message() -> None:
    doc, found = parse_sfx({"schema": "x", "events": [{"type": 5}, 3], "windows": [{}], "k": 1})
    assert doc is None and found
    assert {i.code for i in found} == {"A01"}
    assert all(i.level == "error" and i.message_es for i in found)
