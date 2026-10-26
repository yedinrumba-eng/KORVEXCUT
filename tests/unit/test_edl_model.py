"""Reading an EDL (spec S1.5a): `parse_edl` never raises and reports every schema error as E01;
`find_edl` and `load_edl` find and read the file. Nothing of the range of a value is judged here.
"""

import copy
import json
import pathlib
from pathlib import Path

import pytest

from kcut.edl.files import MAX_EDL_BYTES, find_edl, load_edl
from kcut.edl.model import BrollSpan, CamSpan, ColorSpan, GapClip, ScreenSpan, VoiceClip
from kcut.edl.parse import parse_edl
from kcut.errors import ProjectError
from kcut.project import open_project
from tests.unit.edl_fakes import Doc, edit, example_doc, parsed


def _issues(doc: object) -> list[tuple[str, str]]:
    edl, issues = parse_edl(doc)
    assert edl is None
    return [(i.code, i.path) for i in issues]


class TestParseTheExample:
    def test_edl_model_the_example_has_no_issues_and_every_kind_of_clip_and_span(self) -> None:
        edl, issues = parse_edl(example_doc())
        assert issues == [] and edl is not None
        assert (edl.version, edl.fps, edl.out_w, edl.out_h, edl.frames) == (1, 30, 1080, 1920, 345)
        assert [type(c) for c in edl.clips] == [GapClip, VoiceClip, GapClip, VoiceClip, GapClip]
        kinds = [ColorSpan, CamSpan, CamSpan, CamSpan, ScreenSpan, CamSpan, ColorSpan]
        assert [type(s) for s in edl.spans] == kinds
        assert set(edl.sources) == {"a1", "a2", "b1"}

    def test_edl_model_defaults_are_the_ones_of_the_spec(self) -> None:
        edl = parsed()
        cam = edl.spans[2]
        assert isinstance(cam, CamSpan)
        assert (cam.zoom, cam.cx, cam.cy, cam.anchor, cam.push) == (1.0, 0.5, 0.5, "center", 0.05)
        assert cam.src_f is None and cam.look is None and cam.fade_in_f == cam.fade_out_f == 0
        screen = edl.spans[4]
        assert isinstance(screen, ScreenSpan) and screen.card_y == 0.47
        assert screen.remap[1].speed == 2.0 and screen.keys[1].card == (1000, 760)
        assert edl.spans[3].look == "calido" and edl.spans[6].fade_out_f == 10

    def test_edl_model_look_defaults_to_neutro_and_voice_duration_is_out_minus_in(self) -> None:
        doc = edit(lambda d: d.pop("look"))
        edl = parsed(doc)
        assert edl.look == "neutro"
        voice = edl.clips[1]
        assert isinstance(voice, VoiceClip) and voice.dur_f == 180

    def test_edl_model_a_broll_and_a_free_camera_read_their_fields(self) -> None:
        def change(doc: Doc) -> None:
            doc["spans"][1] = {
                "kind": "broll", "at_f": 30, "dur_f": 60, "src": "b1", "src_f": 10, "dim": 0.5,
            }  # fmt: skip
            doc["spans"][2]["src_f"] = 33

        edl = parsed(edit(change))
        broll, free = edl.spans[1], edl.spans[2]
        assert isinstance(broll, BrollSpan) and (broll.push, broll.dim, broll.sharpen) == (
            0.07,
            0.5,
            0.0,
        )
        assert isinstance(free, CamSpan) and free.src_f == 33

    def test_edl_model_a_path_label_goes_in_front_of_every_path(self) -> None:
        _, issues = parse_edl({"schema": "x"}, "edl")
        assert issues and all(i.path.startswith("edl") for i in issues)


class TestSchemaErrorsAreE01:
    def test_edl_model_not_an_object(self) -> None:
        assert _issues([]) == [("E01", "")]

    def test_edl_model_wrong_schema_text(self) -> None:
        assert _issues(edit(lambda d: d.update(schema="kcut.edl/2"))) == [("E01", "schema")]

    def test_edl_model_a_missing_field(self) -> None:
        assert _issues(edit(lambda d: d["spans"][1].pop("dur_f"))) == [("E01", "spans[1].dur_f")]
        assert _issues(edit(lambda d: d.pop("frames"))) == [("E01", "frames")]

    def test_edl_model_an_unknown_key_is_named_without_its_text(self) -> None:
        doc = edit(lambda d: d["clips"][1].update(inventada=1))
        edl, issues = parse_edl(doc)
        assert edl is None and [(i.code, i.path) for i in issues] == [
            ("E01", "clips[1].<clave desconocida>")
        ]
        assert "inventada" not in issues[0].message_es

    @pytest.mark.parametrize("value", [30.0, True, "30", None])
    def test_edl_model_a_frame_field_has_to_be_a_whole_number(self, value: object) -> None:
        assert _issues(edit(lambda d: d["clips"][1].update(in_f=value))) == [
            ("E01", "clips[1].in_f")
        ]
        assert _issues(edit(lambda d: d["spans"][0].update(dur_f=value))) == [
            ("E01", "spans[0].dur_f")
        ]

    def test_edl_model_a_wrong_type_in_a_number_or_a_text(self) -> None:
        assert _issues(edit(lambda d: d["spans"][1].update(zoom="1.3"))) == [
            ("E01", "spans[1].zoom")
        ]
        assert _issues(edit(lambda d: d["spans"][1].update(zoom=True))) == [
            ("E01", "spans[1].zoom")
        ]
        assert _issues(edit(lambda d: d["clips"][1].update(why=3))) == [("E01", "clips[1].why")]

    def test_edl_model_an_unknown_kind_or_anchor_or_color(self) -> None:
        assert _issues(edit(lambda d: d["clips"][0].update(kind="hole"))) == [
            ("E01", "clips[0].kind")
        ]
        assert _issues(edit(lambda d: d["spans"][0].update(kind="photo"))) == [
            ("E01", "spans[0].kind")
        ]
        assert _issues(edit(lambda d: d["spans"][1].update(anchor="left"))) == [
            ("E01", "spans[1].anchor")
        ]
        assert _issues(edit(lambda d: d["spans"][0].update(color="red"))) == [
            ("E01", "spans[0].color")
        ]

    def test_edl_model_a_key_or_a_remap_point_with_the_wrong_shape(self) -> None:
        def short_crop(d: Doc) -> None:
            d["spans"][4]["keys"][0]["crop"] = [0.5, 0.5]

        def float_card(d: Doc) -> None:
            d["spans"][4]["keys"][0]["card"] = [1040.5, 476]

        def bad_speed(d: Doc) -> None:
            d["spans"][4]["remap"][1]["speed"] = "fast"

        assert _issues(edit(short_crop)) == [("E01", "spans[4].keys[0].crop")]
        assert _issues(edit(float_card)) == [("E01", "spans[4].keys[0].card[0]")]
        assert _issues(edit(bad_speed)) == [("E01", "spans[4].remap[1].speed")]

    def test_edl_model_the_errors_of_different_places_are_all_reported(self) -> None:
        def change(doc: Doc) -> None:
            doc["fps"] = "30"
            doc["clips"][1]["in_f"] = 1.5
            doc["spans"][2]["zoom"] = None
            doc["spans"][5].pop("src")

        paths = [path for _, path in _issues(edit(change))]
        assert paths == ["fps", "clips[1].in_f", "spans[2].zoom", "spans[5].src"]

    def test_edl_model_sources_with_a_bad_entry_name_the_id(self) -> None:
        def change(doc: Doc) -> None:
            doc["sources"]["a1"] = {"qhash": 5}

        edl, issues = parse_edl(edit(change))
        assert edl is None and issues[0].path == "sources" and "a1" in issues[0].message_es
        assert _issues(edit(lambda d: d.pop("sources"))) == [("E01", "sources")]
        assert _issues(edit(lambda d: d["sources"].update(a1={"hash": "x"}))) == [
            ("E01", "sources")
        ]

    def test_edl_model_parse_never_raises_on_hostile_json(self) -> None:
        for doc in (None, 3, "x", [1], {"spans": {}}, {"clips": [3, None]}, {"output": []}):
            edl, issues = parse_edl(doc)
            assert edl is None and issues and all(i.code == "E01" for i in issues)

    def test_edl_model_a_huge_integer_is_an_issue_not_a_crash(self) -> None:
        doc = copy.deepcopy(example_doc())
        doc["clips"][1]["in_f"] = 10**400
        edl, issues = parse_edl(doc)
        assert edl is not None and issues == []  # a whole number: ranges judges it


class TestReservedCodes:
    def test_edl_model_e10_and_e16_are_reserved_and_no_source_file_has_them(self) -> None:
        source = pathlib.Path(__file__).resolve().parents[2] / "src" / "kcut"
        offenders = [
            str(path)
            for path in source.rglob("*.py")
            if '"E10"' in path.read_text(encoding="utf-8")
            or '"E16"' in path.read_text(encoding="utf-8")
        ]
        assert offenders == []


class TestFindAndLoad:
    def _project(self, tmp_path: Path) -> Path:
        root = tmp_path / "proyecto ñandú"
        (root / "edit").mkdir(parents=True)
        (root / "kcut.toml").write_text("", encoding="utf-8")
        return root

    def test_edl_model_find_takes_the_highest_n(self, tmp_path: Path) -> None:
        root = self._project(tmp_path)
        for name in ("edl-v1.json", "edl-v10.json", "edl-v2.json", "edl-v02.json", "edl-v0.json"):
            (root / "edit" / name).write_text("{}", encoding="utf-8")
        (root / "edit" / "edl-v99999.json").write_text("{}", encoding="utf-8")
        assert find_edl(open_project(str(root)), None) == ("edit/edl-v10.json", 10)

    def test_edl_model_find_without_an_edl_is_a_project_error(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectError, match=r"edl-vN\.json"):
            find_edl(open_project(str(self._project(tmp_path))), None)

    def test_edl_model_find_with_a_path_takes_n_from_the_name(self, tmp_path: Path) -> None:
        project = open_project(str(self._project(tmp_path)))
        assert find_edl(project, "edit\\viejos/edl-v3.json") == ("edit/viejos/edl-v3.json", 3)
        for bad in ("edit/edl.json", "edit/edl-v0.json", "edit/otro.json", "edit/edl-v1.json.bak"):
            with pytest.raises(ProjectError, match=r"edl-vN\.json"):
                find_edl(project, bad)

    @pytest.mark.parametrize("rel", ["../edl-v1.json", "/tmp/edl-v1.json", "C:/edl-v1.json"])
    def test_edl_model_find_refuses_a_path_that_leaves_the_project(
        self, tmp_path: Path, rel: str
    ) -> None:
        with pytest.raises(ProjectError):
            find_edl(open_project(str(self._project(tmp_path))), rel)

    def test_edl_model_load_gives_the_edl_and_the_version_of_the_name(self, tmp_path: Path) -> None:
        root = self._project(tmp_path)
        (root / "edit" / "edl-v4.json").write_text(json.dumps(example_doc()), encoding="utf-8")
        edl, issues, version = load_edl(open_project(str(root)), "edit/edl-v4.json")
        assert edl is not None and issues == [] and version == 4

    def test_edl_model_load_with_schema_errors_gives_no_edl_but_the_issues(
        self, tmp_path: Path
    ) -> None:
        root = self._project(tmp_path)
        (root / "edit" / "edl-v1.json").write_text("{}", encoding="utf-8")
        edl, issues, version = load_edl(open_project(str(root)), "edit/edl-v1.json")
        assert edl is None and version == 1 and {i.code for i in issues} == {"E01"}

    def test_edl_model_load_a_file_that_is_not_json_or_is_missing_is_a_project_error(
        self, tmp_path: Path
    ) -> None:
        root = self._project(tmp_path)
        project = open_project(str(root))
        (root / "edit" / "edl-v1.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ProjectError, match="JSON mal formado"):
            load_edl(project, "edit/edl-v1.json")
        with pytest.raises(ProjectError, match="no existe"):
            load_edl(project, "edit/edl-v7.json")

    def test_edl_model_load_refuses_a_file_over_the_cap(self, tmp_path: Path) -> None:
        root = self._project(tmp_path)
        (root / "edit" / "edl-v1.json").write_bytes(b" " * (MAX_EDL_BYTES + 1))
        with pytest.raises(ProjectError, match="pesa más de"):
            load_edl(open_project(str(root)), "edit/edl-v1.json")
