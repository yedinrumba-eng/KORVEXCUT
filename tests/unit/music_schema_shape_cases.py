"""The shape of `edit/music.json` against the schema (spec S1.8b row 3, 001.15): the example of the
spec, the defaults of what the file leaves out, M01 (the shape, `duck`, `windows`) and M02 (the
`synth`). Collected from `test_music_schema.py` (300-line rule); `project` is its fixture.
"""

from typing import Any

import pytest

from kcut.audio.music_model import DEFAULT_DUCK
from kcut.project import Project
from tests.fixtures.synth_audio import music_plan_document
from tests.unit.music_schema_helpers import codes as _codes
from tests.unit.music_schema_helpers import parse as _parse
from tests.unit.music_schema_helpers import synth_doc as _synth_doc
from tests.unit.music_schema_helpers import with_synth as _with_synth

__all__ = [
    "test_music_schema_a_section_that_is_there_is_checked_whatever_the_mode",
    "test_music_schema_m01_a_lot_of_windows_are_one_issue_and_none_is_looked_at",
    "test_music_schema_m01_the_shape_of_the_file",
    "test_music_schema_m01_the_types_of_the_synth",
    "test_music_schema_m02_a_missing_progression_is_m01",
    "test_music_schema_m02_the_limits_themselves_are_fine",
    "test_music_schema_m02_the_synth",
    "test_music_schema_only_schema_and_mode_are_needed_and_the_rest_has_the_defaults",
    "test_music_schema_the_example_of_the_spec_is_good",
    "test_music_schema_the_values_that_are_zero_are_kept_and_not_replaced_by_the_default",
]
NONE = {"schema": "kcut.music/1", "mode": "none"}


def test_music_schema_the_example_of_the_spec_is_good(project: Project) -> None:
    doc, found = _parse(project, music_plan_document())
    assert found == [] and doc is not None
    assert doc.mode == "synth" and doc.gain_db == -8.0 and doc.file is None
    assert doc.synth is not None
    assert (doc.synth.bpm, doc.synth.progression) == (120.0, ("Am", "F", "C", "G"))
    assert doc.synth.mute_drums == ((210, 270),) and doc.synth.stop_drums_f == 330
    assert doc.synth.drums is True and doc.synth.origin_f == 0
    assert doc.duck == DEFAULT_DUCK and doc.duck.knee == 2.828
    assert [(w.start, w.end, w.gain_db) for w in doc.windows] == [(0, 30, 3.0)]


def test_music_schema_only_schema_and_mode_are_needed_and_the_rest_has_the_defaults(
    project: Project,
) -> None:
    doc, found = _parse(project, NONE)
    assert found == [] and doc is not None
    assert (doc.mode, doc.gain_db, doc.synth, doc.file) == ("none", -8.0, None, None)
    assert doc.duck == DEFAULT_DUCK and doc.windows == ()
    doc, found = _parse(
        project, {"schema": "kcut.music/1", "mode": "synth", "synth": {"progression": ["Em"]}}
    )
    assert found == [] and doc is not None and doc.synth is not None
    assert (doc.synth.bpm, doc.synth.drums, doc.synth.origin_f) == (120.0, True, 0)
    assert (doc.synth.mute_drums, doc.synth.stop_drums_f) == ((), None)


def test_music_schema_the_values_that_are_zero_are_kept_and_not_replaced_by_the_default(
    project: Project,
) -> None:
    doc, found = _parse(project, _synth_doc(gain_db=0))
    assert found == [] and doc is not None and doc.gain_db == 0.0
    doc, found = _parse(project, _with_synth(origin_f=0, stop_drums_f=0))
    assert found == [] and doc is not None and doc.synth is not None
    assert (doc.synth.origin_f, doc.synth.stop_drums_f) == (0, 0)


def _windows(*items: Any) -> dict[str, Any]:
    return {**NONE, "windows": list(items)}


def _duck(**given: Any) -> dict[str, Any]:
    return {**NONE, "duck": given}


@pytest.mark.parametrize(
    ("data", "path"),
    [
        ([], ""),
        ({"mode": "none"}, "schema"),
        ({"schema": "kcut.music/2", "mode": "none"}, "schema"),
        ({"schema": "kcut.music/1"}, "mode"),
        ({"schema": "kcut.music/1", "mode": "loud"}, "mode"),
        ({"schema": "kcut.music/1", "mode": 3}, "mode"),
        ({**NONE, "extra": 1}, "<clave desconocida>"),
        ({**NONE, "gain_db": 7}, "gain_db"),
        ({**NONE, "gain_db": -41}, "gain_db"),
        ({**NONE, "gain_db": "alto"}, "gain_db"),
        ({**NONE, "gain_db": True}, "gain_db"),
        ({"schema": "kcut.music/1", "mode": "synth"}, "synth"),
        ({"schema": "kcut.music/1", "mode": "synth", "synth": None}, "synth"),
        ({"schema": "kcut.music/1", "mode": "file"}, "file"),
        ({"schema": "kcut.music/1", "mode": "file", "file": None}, "file"),
        ({**NONE, "windows": "no"}, "windows"),
        (_windows(3), "windows[0]"),
        (_windows({"start": 0, "end": 5}), "windows[0].gain_db"),
        (_windows({"start": 0, "end": 5, "gain_db": 13}), "windows[0].gain_db"),
        (_windows({"start": 0.5, "end": 5, "gain_db": 1}), "windows[0].start"),
        ({**NONE, "duck": 3}, "duck"),
        (_duck(threshold=0), "duck.threshold"),
        (_duck(threshold=1.1), "duck.threshold"),
        (_duck(ratio=0.5), "duck.ratio"),
        (_duck(ratio=21), "duck.ratio"),
        (_duck(attack_ms=0.5), "duck.attack_ms"),
        (_duck(attack_ms=201), "duck.attack_ms"),
        (_duck(release_ms=9), "duck.release_ms"),
        (_duck(release_ms=2001), "duck.release_ms"),
        (_duck(makeup=0.9), "duck.makeup"),
        (_duck(makeup=4.1), "duck.makeup"),
        (_duck(knee=0.5), "duck.knee"),
        (_duck(knee=9), "duck.knee"),
        (_duck(enabled=1), "duck.enabled"),
        (_duck(other=1), "duck.<clave desconocida>"),
    ],
)
def test_music_schema_m01_the_shape_of_the_file(project: Project, data: Any, path: str) -> None:
    doc, found = _parse(project, data)
    assert doc is None
    assert (("M01", path) in _codes(found)) and all(i.code == "M01" for i in found), found


def test_music_schema_m01_a_lot_of_windows_are_one_issue_and_none_is_looked_at(
    project: Project,
) -> None:
    data = _windows(*[{"start": "x"}] * 201)
    assert _codes(_parse(project, data)[1]) == [("M01", "windows")]
    data = _windows(*[{"start": i, "end": i + 3, "gain_db": 1} for i in range(200)])
    assert _parse(project, data)[1] == []


@pytest.mark.parametrize(
    ("changes", "path"),
    [
        ({"bpm": 59}, "synth.bpm"),
        ({"bpm": 181}, "synth.bpm"),
        ({"bpm": 0}, "synth.bpm"),
        ({"progression": []}, "synth.progression"),
        ({"progression": ["C"] * 17}, "synth.progression"),
        ({"progression": ["Am", "H"]}, "synth.progression[1]"),
        ({"progression": ["Am", "am"]}, "synth.progression[1]"),
        ({"progression": ["Cb"]}, "synth.progression[0]"),
        ({"progression": ["Am7"]}, "synth.progression[0]"),
    ],
)
def test_music_schema_m02_the_synth(project: Project, changes: dict[str, Any], path: str) -> None:
    doc, found = _parse(project, _with_synth(**changes))
    assert doc is None and _codes(found) == [("M02", path)]


def test_music_schema_m02_the_limits_themselves_are_fine(project: Project) -> None:
    for changes in (
        {"bpm": 60},
        {"bpm": 180},
        {"progression": ["C#m"] * 16},
        {"progression": ["Bb"]},
    ):
        assert _parse(project, _with_synth(**changes))[1] == [], changes


@pytest.mark.parametrize(
    ("changes", "path"),
    [
        ({"progression": "Am"}, "synth.progression"),
        ({"progression": [3]}, "synth.progression[0]"),
        ({"bpm": "rapido"}, "synth.bpm"),
        ({"bpm": True}, "synth.bpm"),
        ({"drums": 1}, "synth.drums"),
        ({"mute_drums": 3}, "synth.mute_drums"),
        ({"mute_drums": [{"start": 1}]}, "synth.mute_drums[0].end"),
        (
            {"mute_drums": [{"start": 1, "end": 5, "gain_db": 3}]},
            "synth.mute_drums[0].<clave desconocida>",
        ),
        ({"stop_drums_f": 1.5}, "synth.stop_drums_f"),
        ({"origin_f": "0"}, "synth.origin_f"),
        ({"otra": 1}, "synth.<clave desconocida>"),
    ],
)
def test_music_schema_m01_the_types_of_the_synth(
    project: Project, changes: dict[str, Any], path: str
) -> None:
    doc, found = _parse(project, _with_synth(**changes))
    assert doc is None and _codes(found) == [("M01", path)]


def test_music_schema_m02_a_missing_progression_is_m01(project: Project) -> None:
    data = {"schema": "kcut.music/1", "mode": "synth", "synth": {"bpm": 100}}
    assert _codes(_parse(project, data)[1]) == [("M01", "synth.progression")]


def test_music_schema_a_section_that_is_there_is_checked_whatever_the_mode(
    project: Project,
) -> None:
    data = {**NONE, "synth": {"progression": ["Z"]}}
    assert _codes(_parse(project, data)[1]) == [("M02", "synth.progression[0]")]
