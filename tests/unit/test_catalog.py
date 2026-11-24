"""The catalog (spec S1.9a, row 3; D8: the one source of truth of what the engine can do).

`collect()` builds it from the registries of the engine (graphic components, looks, sound effects)
and from the static items (music, camera, transition, workflow) and the planned ones. What is
`available` has an implementation behind it; what is implemented is in the catalog. The ids are
unique inside their category.
"""

import dataclasses
import json
from collections import Counter
from importlib import resources

import pytest

from kcut import cli
from kcut.audio.sfx_library import SFX
from kcut.catalog.collect import collect
from kcut.catalog.model import CATEGORIES, CatalogItem
from kcut.config.model import BrandSection
from kcut.edl import model as edl_model
from kcut.gfx.components import COMPONENTS, page_component
from kcut.params import ParamSpec
from kcut.render.looks import LOOKS, look_chain
from tests.unit.catalog_ranges import RANGED, refused

ITEM_KEYS = [
    "category",
    "id",
    "name_es",
    "purpose_es",
    "avoid_es",
    "status",
    "since",
    "cost",
    "cost_note_es",
    "params",
]
PARAM_KEYS = ["name", "kind", "required", "default", "lo", "hi", "help_es"]
AVAILABLE = {
    "graphic": {
        "captions", "title", "label", "kinetic", "endcard", "steps", "sticker", "holo_board",
        "globe",
    },
    "look": {"neutro", "contraste", "calido", "frio", "cinematico", "bn-acento"},
    "sfx": {
        "whoosh", "boom", "pop", "shimmer", "key", "click", "kick", "hat", "pad", "typing",
        "riser", "blip8", "powerup",
    },
    "music": {"synth", "file", "none"},
    "camera": {"zoom", "push", "reframe", "screen_card", "broll_push", "color_card"},
    "transition": {"cut", "fade_black"},
    "workflow": {"qa"},
}  # fmt: skip
PLANNED = {
    "transition": {"crossfade", "whip"},
    "graphic": {"lower_third"},  # 001.42 (D24): `matte_captions` is out (it was here too)
    "music": {"beat_cut"},
}  # 001.39 (D22): `camera` lost its three planned ids, so it has none
DISCARDED = (  # 001.39 (D22): Yedin, 26/10/2026; 001.42 (D24): `matte_captions`, 23/11/2026
    "face_follow", "hand_track", "privacy_blur", "matte_captions",
)  # fmt: skip
BRAND = BrandSection("#E5FF1F", "#2FA8FF", "#0B0B0E", "#FFFFFF")


def _by(status: str) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for item in collect():
        if item.status == status:
            found.setdefault(item.category, set()).add(item.id)
    return found


def test_catalog_ids_are_unique_inside_their_category() -> None:
    pairs = [(item.category, item.id) for item in collect()]
    assert [pair for pair, n in Counter(pairs).items() if n > 1] == []


def test_catalog_the_categories_are_the_seven_of_the_spec() -> None:
    assert CATEGORIES == (
        "graphic", "look", "sfx", "music", "camera", "transition", "workflow",
    )  # fmt: skip
    assert {item.category for item in collect()} <= set(CATEGORIES)


def test_catalog_what_is_available_in_001_is_what_the_spec_lists() -> None:
    assert _by("available") == AVAILABLE
    assert len(AVAILABLE["sfx"]) == 13 and AVAILABLE["sfx"] == set(SFX)  # the spec says "los 13"


def test_catalog_what_is_planned_is_what_the_spec_lists() -> None:
    assert _by("planned") == PLANNED


def test_catalog_planned_has_none_of_what_yedin_discarded() -> None:
    """001.39 (D22): `face_follow`, `hand_track` and `privacy_blur` are discarded, so they are not
    proposed again (R6): no item of any category and any status carries one of those ids."""
    ids = {item.id for item in collect()}
    assert ids.isdisjoint(DISCARDED)
    assert all(item.id not in DISCARDED for item in collect() if item.status == "planned")


def test_catalog_planned_json_of_the_command_has_none_of_what_yedin_discarded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """001.39 (D22): the same, in the document that `kcut catalog --json` prints."""
    capsys.readouterr()
    assert cli.main(["catalog", "--json"]) == 0
    document = json.loads(capsys.readouterr().out)
    planned = [item["id"] for item in document["items"] if item["status"] == "planned"]
    assert not {item["id"] for item in document["items"]} & set(DISCARDED)
    assert sorted(planned) == sorted(i for ids in PLANNED.values() for i in ids)
    assert "camera" not in {i["category"] for i in document["items"] if i["status"] == "planned"}


def test_catalog_the_planned_ones_say_when_and_that_they_do_not_exist() -> None:
    for item in collect():
        if item.status == "planned":
            assert item.since in ("F2", "F4"), item.id
            assert item.params == () and item.cost_note_es == ""
            assert "no existe" in item.avoid_es


def test_catalog_every_available_item_has_an_implementation() -> None:
    for item in collect():
        if item.status != "available":
            continue
        if item.category == "graphic":
            component = page_component(item.id)
            assert component is not None, item.id
            folder = resources.files("kcut.gfx").joinpath("web", "components")
            for name in component.js_files:
                assert folder.joinpath(name).is_file(), (item.id, name)
        elif item.category == "look":
            assert item.id in LOOKS
            look_chain(item.id, BRAND)  # a look with no chain would raise
        elif item.category == "sfx":
            assert callable(SFX[item.id].fn), item.id
        elif item.category in ("camera", "transition"):
            fields = {f.name for cls in _edl_classes() for f in dataclasses.fields(cls)}
            assert item.edl_field is None or item.edl_field in fields, item.id
        elif item.category == "music":
            assert item.id in ("synth", "file", "none")


def _edl_classes() -> list[type]:
    return [
        obj
        for obj in vars(edl_model).values()
        if isinstance(obj, type) and dataclasses.is_dataclass(obj)
    ]


def test_catalog_only_the_transition_cut_has_no_edl_field() -> None:
    """Cutting is not putting anything: `cut` has no field. Every other camera and transition
    that is available names the field of the EDL that makes it."""
    missing = [
        (item.category, item.id)
        for item in collect()
        if item.category in ("camera", "transition")
        and item.status == "available"
        and item.edl_field is None
    ]
    assert missing == [("transition", "cut")]


def test_catalog_everything_the_engine_implements_is_in_the_catalog() -> None:
    graphic = {item.id for item in collect() if item.category == "graphic"}
    assert set(COMPONENTS) | {"captions"} <= graphic
    assert set(LOOKS) <= {item.id for item in collect() if item.category == "look"}
    assert set(SFX) <= {item.id for item in collect() if item.category == "sfx"}


def test_catalog_the_graphics_come_from_the_components_with_their_own_texts() -> None:
    title = next(i for i in collect() if (i.category, i.id) == ("graphic", "title"))
    component = COMPONENTS["title"]
    assert (title.name_es, title.purpose_es, title.avoid_es) == (
        component.name_es,
        component.purpose_es,
        component.avoid_es,
    )
    assert (title.cost, title.cost_note_es, title.since) == (
        component.cost,
        component.cost_note_es,
        component.since,
    )
    assert [p.name for p in title.params] == [p.name for p in component.params]


def test_catalog_json_has_the_fields_of_the_spec_in_order() -> None:
    for item in collect():
        document = item.to_json()
        assert list(document) == ITEM_KEYS, item.id
        assert document["status"] in ("available", "planned")
        assert document["cost"] in ("bajo", "medio", "alto")
        params = document["params"]
        assert isinstance(params, list)
        for param in params:
            assert list(param) == PARAM_KEYS, (item.id, param)


def test_catalog_json_can_be_written_with_no_nan_and_comes_back_equal() -> None:
    documents = [item.to_json() for item in collect()]
    assert json.loads(json.dumps(documents, allow_nan=False)) == documents


def test_catalog_the_param_of_a_title_has_the_shape_of_the_example() -> None:
    title = next(i for i in collect() if (i.category, i.id) == ("graphic", "title"))
    text = title.to_json()["params"][0]  # type: ignore[index]
    assert text == {
        "name": "text",
        "kind": "str",
        "required": True,
        "default": None,
        "lo": None,
        "hi": None,
        "help_es": "texto del título (hasta 40 caracteres)",
    }


def test_catalog_every_text_is_filled_in_and_plain() -> None:
    """Spanish, one line, with no long dash and no emoji: the human output is ASCII punctuation."""
    for item in collect():
        for text in (item.name_es, item.purpose_es, item.avoid_es):
            assert text and "\n" not in text and "—" not in text, (item.id, text)
        assert "\n" not in item.cost_note_es and "—" not in item.cost_note_es


def test_catalog_the_available_ones_have_a_slice_and_the_planned_ones_a_phase() -> None:
    for item in collect():
        if item.status == "available":
            assert item.since.startswith("S1."), (item.id, item.since)
        else:
            assert item.since.startswith("F"), (item.id, item.since)


def test_catalog_the_workflow_qa_is_there_and_storyboard_is_not_yet() -> None:
    workflow = {i.id for i in collect() if i.category == "workflow"}
    assert workflow == {"qa"}  # S1.10 adds `storyboard`


@pytest.mark.parametrize("category", CATEGORIES)
def test_catalog_every_category_has_items(category: str) -> None:
    assert any(item.category == category for item in collect())


def test_catalog_collect_gives_the_same_list_every_time() -> None:
    first, second = collect(), collect()
    assert first == second and all(isinstance(item, CatalogItem) for item in first)


def test_catalog_planned_are_exactly_the_four_of_001_42() -> None:
    planned = sorted(i.id for i in collect() if i.status == "planned")
    assert planned == ["beat_cut", "crossfade", "lower_third", "whip"]


def test_catalog_planned_crossfade_says_what_the_example_of_the_spec_says() -> None:
    """001.41, point 9: the example of `kcut catalog --json` in the spec is this item."""
    item = next(i for i in collect() if (i.category, i.id) == ("transition", "crossfade"))
    assert item.cost == "medio"
    assert item.purpose_es == "Pasar de una toma a otra mezclando las dos"
    assert (item.name_es, item.status, item.since) == ("Fundido cruzado", "planned", "F2")


def _ranged() -> list[tuple[str, str, CatalogItem, ParamSpec]]:
    return [
        (item.id, param.name, item, param)
        for item in collect()
        if item.category in ("camera", "transition") and item.status == "available"
        for param in item.params
        if param.kind in ("int", "float") and (param.lo is not None or param.hi is not None)
    ]


def test_catalog_the_ranges_of_camera_and_transitions_are_the_ones_the_engine_enforces() -> None:
    """001.41, point 9 (D8): `lo` and `hi` of `static_items.py` against E13 of `edl/fields.py`.
    Inside and on the edge the field is fine; a step outside it, E13 names that field."""
    assert {(i, n) for i, n, _, _ in _ranged()} == set(RANGED)  # a new range must be tied here
    for item_id, name, _, param in _ranged():
        step = 1 if param.kind == "int" else 0.01
        if param.lo is not None:
            assert not refused(item_id, name, param.lo), (item_id, name)
            assert refused(item_id, name, param.lo - step), (item_id, name)
        if param.hi is not None:
            assert not refused(item_id, name, param.hi), (item_id, name)
            assert refused(item_id, name, param.hi + step), (item_id, name)


def test_catalog_a_range_that_drifts_from_the_engine_fails_the_tie() -> None:
    """The tie itself works: with `zoom` listed up to 3.5 the engine refuses 3.2, so it fails."""
    assert refused("zoom", "zoom", 3.2) and not refused("zoom", "zoom", 3.0)
    assert refused("fade_black", "fade_in_f", -1) and not refused("fade_black", "fade_in_f", 0)
