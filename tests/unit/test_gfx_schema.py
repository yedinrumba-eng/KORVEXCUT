"""The schema of `edit/graphics.json` (spec S1.6a row 2): `parse_graphics`, `default_doc` and the
G01 and G02 issues. Only the shape of the file; what the parameters mean is `test_gfx_codes`."""

import copy
from typing import Any

import pytest

from kcut.gfx.schema import SCHEMA, CueDoc, default_doc, parse_graphics
from tests.fixtures.synth_graphics import graphics_v1_document
from tests.unit.gfx_limits_cases import *  # noqa: F403  (001.28: 300-line rule)


def _doc(change: Any = None) -> dict[str, Any]:
    document = copy.deepcopy(graphics_v1_document())
    if change is not None:
        change(document)
    return document


def _problems(data: object) -> list[tuple[str, str]]:
    doc, issues = parse_graphics(data)
    assert doc is None and issues, "se esperaba un error"
    return [(i.code, i.path) for i in issues]


def test_gfx_schema_the_fixture_parses_into_four_cues_in_order() -> None:
    doc, issues = parse_graphics(graphics_v1_document())
    assert issues == [] and doc is not None
    shape = [(c.index, c.id, c.component) for c in doc.cues]
    assert shape == [
        (0, "gancho", "kinetic"),
        (1, "titulo", "title"),
        (2, "pill", "label"),
        (3, "cierre", "endcard"),
    ]
    assert doc.captions_enabled is True and doc.hide == ()
    assert (doc.cues[0].start, doc.cues[0].end) == (0, 30)
    assert isinstance(doc.cues[0], CueDoc) and doc.cues[0].hide_captions is None


def test_gfx_schema_default_doc_has_no_cues_no_windows_and_leaves_captions_to_the_toml() -> None:
    doc = default_doc()
    assert (doc.captions_enabled, doc.hide, doc.cues) == (None, (), ())


def test_gfx_schema_the_minimum_document_is_a_schema_and_cues() -> None:
    doc, issues = parse_graphics({"schema": SCHEMA, "cues": []})
    assert issues == [] and doc is not None and doc.captions_enabled is None


def test_gfx_schema_captions_without_enabled_leaves_it_to_the_toml_and_enabled_false_is_false() -> (
    None
):
    doc = parse_graphics({"schema": SCHEMA, "captions": {}, "cues": []})[0]
    assert doc is not None and doc.captions_enabled is None
    doc = parse_graphics({"schema": SCHEMA, "captions": {"enabled": False}, "cues": []})[0]
    assert doc is not None and doc.captions_enabled is False


def test_gfx_schema_captions_hide_windows_take_frames_and_anchors() -> None:
    hide = [
        {"start": 0, "end": 30},
        {"start": {"word": "a1:w0001", "edge": "start"}, "end": {"src": "a1", "f": 90}},
    ]
    doc, issues = parse_graphics({"schema": SCHEMA, "captions": {"hide": hide}, "cues": []})
    assert issues == [] and doc is not None
    assert [(w.index, w.start, w.end) for w in doc.hide] == [
        (0, 0, 30), (1, {"word": "a1:w0001", "edge": "start"}, {"src": "a1", "f": 90})]  # fmt: skip


def test_gfx_schema_a_cue_can_hide_captions_or_not_and_takes_an_anchor_for_its_times() -> None:
    def change(d: dict[str, Any]) -> None:
        d["cues"][0]["hide_captions"] = False
        d["cues"][1]["start"] = {"word": "a1:w0031", "edge": "start", "offset_f": -1}
        d["cues"][2]["start"] = {"src": "a1", "f": 100}

    doc = parse_graphics(_doc(change))[0]
    assert doc is not None
    assert doc.cues[0].hide_captions is False and doc.cues[1].hide_captions is None
    assert doc.cues[1].start == {"word": "a1:w0031", "edge": "start", "offset_f": -1}


@pytest.mark.parametrize("data", [None, [], "x", 3, True])
def test_gfx_schema_g01_the_document_must_be_an_object(data: object) -> None:
    assert _problems(data) == [("G01", "")]


def test_gfx_schema_g01_the_schema_must_be_kcut_graphics_1() -> None:
    assert _problems(_doc(lambda d: d.update(schema="kcut.graphics/2"))) == [("G01", "schema")]
    assert _problems(_doc(lambda d: d.pop("schema"))) == [("G01", "schema")]


def test_gfx_schema_g01_cues_are_required_and_must_be_a_list() -> None:
    assert _problems(_doc(lambda d: d.pop("cues"))) == [("G01", "cues")]
    assert _problems(_doc(lambda d: d.update(cues={}))) == [("G01", "cues")]


def test_gfx_schema_g01_an_unknown_key_is_named_without_its_name() -> None:
    top = _problems(_doc(lambda d: d.update(IGNORE="x")))
    assert top == [("G01", "<clave desconocida>")]
    cue = _problems(_doc(lambda d: d["cues"][0].update(IGNORE="x")))
    assert cue == [("G01", "cues[0].<clave desconocida>")]
    inner = _problems(_doc(lambda d: d.update(captions={"enabled": True, "IGNORE": 1})))
    assert inner == [("G01", "captions.<clave desconocida>")]


@pytest.mark.parametrize("key", ["id", "component", "start", "end"])
def test_gfx_schema_g01_a_cue_without_id_component_start_or_end_is_incomplete(key: str) -> None:
    problems = _problems(_doc(lambda d: d["cues"][1].pop(key)))
    assert problems == [("G01", f"cues[1].{key}")]


@pytest.mark.parametrize(
    "cue_id", ["Mayus", "con espacio", "", "a" * 33, "ñ", "under_score", 7, None]
)
def test_gfx_schema_g01_an_id_is_1_to_32_of_a_z_0_9_and_hyphen(cue_id: object) -> None:
    assert _problems(_doc(lambda d: d["cues"][0].update(id=cue_id))) == [("G01", "cues[0].id")]


def test_gfx_schema_g01_an_id_can_be_32_long_and_have_hyphens_and_digits() -> None:
    doc = parse_graphics(_doc(lambda d: d["cues"][0].update(id="a-1" * 10 + "bb")))[0]
    assert doc is not None


def test_gfx_schema_g01_a_repeated_id_is_an_error_on_the_second() -> None:
    assert _problems(_doc(lambda d: d["cues"][3].update(id="gancho"))) == [("G01", "cues[3].id")]


def test_gfx_schema_g01_the_internal_id_of_the_subtitles_is_not_a_valid_id() -> None:
    assert _problems(_doc(lambda d: d["cues"][0].update(id="__captions__"))) == [
        ("G01", "cues[0].id")
    ]


@pytest.mark.parametrize(
    "value",
    [
        True,
        1.0,
        30.5,
        "30",
        None,
        [],
        {},
        {"word": "x"},
        {"src": "a1"},
        {"word": "x", "edge": "mid"},
        {"word": "x", "edge": "start", "extra": 1},
    ],
)
def test_gfx_schema_g01_start_and_end_are_a_whole_number_or_an_anchor_of_the_right_shape(
    value: object,
) -> None:
    assert _problems(_doc(lambda d: d["cues"][0].update(start=value))) == [("G01", "cues[0].start")]
    assert _problems(_doc(lambda d: d["cues"][0].update(end=value))) == [("G01", "cues[0].end")]


@pytest.mark.parametrize("params", [[], "x", 3, None])
def test_gfx_schema_g01_params_must_be_an_object(params: object) -> None:
    assert _problems(_doc(lambda d: d["cues"][0].update(params=params))) == [
        ("G01", "cues[0].params")
    ]


def test_gfx_schema_g01_hide_captions_must_be_true_or_false() -> None:
    assert _problems(_doc(lambda d: d["cues"][0].update(hide_captions="si"))) == [
        ("G01", "cues[0].hide_captions")
    ]


def test_gfx_schema_g01_captions_enabled_and_hide_have_their_own_types() -> None:
    assert _problems(_doc(lambda d: d.update(captions={"enabled": "si"}))) == [
        ("G01", "captions.enabled")
    ]
    assert _problems(_doc(lambda d: d.update(captions={"hide": {}}))) == [("G01", "captions.hide")]
    assert _problems(_doc(lambda d: d.update(captions=[]))) == [("G01", "captions")]
    assert _problems(_doc(lambda d: d.update(captions={"hide": [3]}))) == [
        ("G01", "captions.hide[0]")
    ]
    window = {"hide": [{"start": 0}]}
    assert _problems(_doc(lambda d: d.update(captions=window))) == [("G01", "captions.hide[0].end")]
    window = {"hide": [{"start": 0.5, "end": 5}]}
    assert _problems(_doc(lambda d: d.update(captions=window))) == [
        ("G01", "captions.hide[0].start")
    ]


def test_gfx_schema_g02_an_unknown_component_is_g02_and_the_message_lists_the_known_ones() -> None:
    doc, issues = parse_graphics(_doc(lambda d: d["cues"][0].update(component="fireworks")))
    assert doc is None and [(i.code, i.path) for i in issues] == [("G02", "cues[0].component")]
    assert "fireworks" not in issues[0].message_es
    for known in ("title", "label", "kinetic", "endcard"):
        assert known in issues[0].message_es


def test_gfx_schema_g02_captions_is_internal_and_cannot_be_a_cue() -> None:
    doc, issues = parse_graphics(_doc(lambda d: d["cues"][0].update(component="captions")))
    assert doc is None and [(i.code, i.path) for i in issues] == [("G02", "cues[0].component")]
    assert "interno" in issues[0].message_es


def test_gfx_schema_a_non_text_component_is_g02() -> None:
    assert _problems(_doc(lambda d: d["cues"][0].update(component=5))) == [
        ("G02", "cues[0].component")
    ]


def test_gfx_schema_several_problems_are_all_reported() -> None:
    def change(d: dict[str, Any]) -> None:
        d["schema"] = "x"
        d["cues"][0]["component"] = "nope"
        d["cues"][1]["id"] = "BAD"

    assert _problems(_doc(change)) == [
        ("G01", "schema"),
        ("G02", "cues[0].component"),
        ("G01", "cues[1].id"),
    ]
