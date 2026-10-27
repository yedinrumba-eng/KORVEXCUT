"""`kcut graphics check` on the synthetic project (spec S1.6a rows 4, 5, 7 and 11).

Each test works on a copy of the synthetic project (`view_fresh`), with the example EDL of S1.5
written into it, and runs the command in this process (`kcut_json`). The transcript of a1 is
planted with `save_transcript`, as `kcut transcribe` would leave it, with a phone number said in
digits: it has to reach `chunks` and `cues[].params` masked, and the cache has to stay as it was.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.gfx.components import COMPONENTS
from kcut.gfx.components_base import TITLE, ComponentDef
from kcut.params import ParamSpec
from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import graphics_v1_document, write_graphics_v1
from tests.integration.graphics_helpers import plant_words, tree_hash
from tests.integration.graphics_limits_cases import *  # noqa: F403  (001.28: 300-line rule)
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
PHONE = "809 555 1234"


@pytest.fixture
def cut(view_fresh: Path) -> Path:
    """A copy of the synthetic project with the example EDL and the transcript of a1 planted."""
    write_edl_v1(view_fresh)
    plant_words(view_fresh)
    return view_fresh


def _toml(root: Path, old: str, new: str) -> None:
    path = root / "kcut.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def _write(root: Path, document: dict[str, Any]) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    (root / "edit" / "graphics.json").write_text(text, encoding="utf-8", newline="\n")


def _words(doc: dict[str, Any]) -> list[str]:
    return [w["text"] for chunk in doc["chunks"] for w in chunk["words"]]


def _codes(items: list[dict[str, Any]]) -> list[str]:
    return [item["code"] for item in items]


class TestFixture:
    """Row 7: the fixture writes the exact parameters, and the synthetic project passes."""

    def test_graphics_check_fixture_writes_the_exact_parameters(self, cut: Path) -> None:
        write_graphics_v1(cut, False)
        written = json.loads((cut / "edit" / "graphics.json").read_text(encoding="utf-8"))
        assert written == graphics_v1_document()
        by_id = {c["id"]: c for c in written["cues"]}
        assert by_id["gancho"]["params"] == {
            "lines": [
                {"text": "Esto lo hizo", "at_f": 2, "size": 72, "color": "light"},
                {"text": "kcut", "at_f": 7, "size": 96, "color": "accent"},
            ],
            "y": 0.45,
        }
        assert by_id["titulo"]["params"] == {
            "text": "Higgsfield",
            "bar": True,
            "size": 96,
            "y": 0.6,
        }
        assert by_id["pill"]["params"] == {"text": "hecho con kcut", "size": 40, "y": 0.58}
        assert by_id["cierre"]["params"] == {
            "lines": [{"text": "Fin", "at_f": 0, "size": 96, "color": "light"}],
            "cta": "sigueme",
            "cta_at_f": 4,
            "y": 0.47,
        }
        spans = {c["id"]: (c["component"], c["start"], c["end"]) for c in written["cues"]}
        assert spans == {
            "gancho": ("kinetic", 0, 30),
            "titulo": ("title", 40, 80),
            "pill": ("label", 90, 150),
            "cierre": ("endcard", 315, 345),
        }
        assert written["captions"] == {"enabled": True}

    def test_graphics_check_fixture_is_ok_with_four_cues(self, cut: Path, kcut_json: Run) -> None:
        write_graphics_v1(cut, False)
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert doc["schema"] == "kcut.gfxcheck/1" and doc["frames"] == 345
        assert doc["edl"] == "edit/edl-v1.json" and doc["graphics_json"] == "edit/graphics.json"
        assert [c["id"] for c in doc["cues"]] == ["gancho", "titulo", "pill", "cierre"]
        assert doc["errors"] == [] and doc["chunks"]

    def test_graphics_check_fixture_params_come_with_the_defaults_and_hex_colors(
        self, cut: Path, kcut_json: Run
    ) -> None:
        write_graphics_v1(cut, False)
        doc = kcut_json("graphics", "check", *project_args(cut))[1]
        by_id = {c["id"]: c for c in doc["cues"]}
        title = by_id["titulo"]["params"]
        assert (title["x"], title["bar_color"], title["color"], title["stroke"]) == (
            0.5, "#E5FF1F", "#0B0B0E", False)  # fmt: skip
        assert by_id["gancho"]["params"]["lines"][1]["color"] == "#E5FF1F"
        assert by_id["gancho"]["params"]["lines"][0]["color"] == "#FFFFFF"
        assert (by_id["gancho"]["start_f"], by_id["gancho"]["end_f"]) == (0, 30)


class TestPii:
    """Row 5 (T2): a phone number is masked in what Claude reads."""

    def test_graphics_check_pii_in_the_chunks_and_in_a_cue_text(
        self, cut: Path, kcut_json: Run
    ) -> None:
        document = graphics_v1_document()
        document["cues"][2]["params"]["text"] = f"llama {PHONE}"
        _write(cut, document)
        before = tree_hash(cut / ".kcut" / "transcripts")
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 0, (doc, err)
        words = _words(doc)
        assert "**11" in words and not {"972", "808", "3211"} & set(words)
        text = {c["id"]: c for c in doc["cues"]}["pill"]["params"]["text"]
        assert text.startswith("llama ") and text.endswith("**34")
        assert not any(piece in json.dumps(doc) for piece in ("809", "555", "1234", "3211"))
        assert tree_hash(cut / ".kcut" / "transcripts") == before  # the cache stays as it was
        assert "pii_unmasked" not in _codes(doc["warnings"])

    def test_graphics_check_pii_with_mask_pii_false_is_raw_and_says_so(
        self, cut: Path, kcut_json: Run
    ) -> None:
        document = graphics_v1_document()
        document["cues"][2]["params"]["text"] = f"llama {PHONE}"
        _write(cut, document)
        _toml(cut, "mask_pii = true", "mask_pii = false")
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 0, (doc, err)
        assert {"972", "808", "3211"} <= set(_words(doc))
        assert {c["id"]: c for c in doc["cues"]}["pill"]["params"]["text"] == f"llama {PHONE}"
        assert "pii_unmasked" in _codes(doc["warnings"])


class TestDefaultCaptions:
    """Row 11 (001.15 point 40): without `edit/graphics.json` the subtitles are the graphics."""

    def test_graphics_check_default_captions_on_with_a_transcript_is_g11(
        self, cut: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert doc["graphics_json"] is None and doc["cues"] == []
        assert doc["chunks"] and "**11" in _words(doc) and "3211" not in _words(doc)
        (g11,) = [w for w in doc["warnings"] if w["code"] == "G11"]
        assert (
            g11["message"]
            == "no hay edit/graphics.json: subtítulos por defecto desde la transcripción"
        )

    def test_graphics_check_default_captions_off_is_g12_and_no_chunks(
        self, cut: Path, kcut_json: Run
    ) -> None:
        _toml(cut, "[captions]\nenabled = true", "[captions]\nenabled = false")
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert doc["chunks"] == [] and doc["cues"] == [] and doc["graphics_json"] is None
        (g12,) = [w for w in doc["warnings"] if w["code"] == "G12"]
        assert "los subtítulos están apagados" in g12["message"]

    def test_graphics_check_default_captions_on_without_a_transcript_is_g08_exit_1(
        self, view_fresh: Path, kcut_json: Run
    ) -> None:
        write_edl_v1(view_fresh)
        code, doc, err = kcut_json("graphics", "check", *project_args(view_fresh))
        assert code == 1 and doc["ok"] is False, (doc, err)
        assert _codes(doc["errors"]) == ["G08"]
        assert "kcut transcribe" in doc["errors"][0]["message"]
        assert "captions.enabled=false" in doc["errors"][0]["message"]

    def test_graphics_check_default_captions_the_file_rules_when_it_is_there(
        self, cut: Path, kcut_json: Run
    ) -> None:
        write_graphics_v1(cut, False)
        doc = kcut_json("graphics", "check", *project_args(cut))[1]
        assert doc["graphics_json"] == "edit/graphics.json" and len(doc["cues"]) == 4
        assert "G11" not in _codes(doc["warnings"])


class TestExitCodes:
    """Row 4 (the part of the command): 1 with errors, 5 with G10, 0 with only warnings."""

    def test_graphics_check_codes_an_error_is_exit_1(self, cut: Path, kcut_json: Run) -> None:
        document = graphics_v1_document()
        document["cues"][1]["params"]["size"] = 9000
        _write(cut, document)
        code, doc, _ = kcut_json("graphics", "check", *project_args(cut))
        assert code == 1 and doc["ok"] is False
        assert [(e["code"], e["path"]) for e in doc["errors"]] == [("G03", "cues[1].params.size")]
        assert [c["id"] for c in doc["cues"]] == ["gancho", "pill", "cierre"]  # the bad one is out

    def test_graphics_check_codes_g10_is_exit_5(
        self, cut: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        picture = ComponentDef(
            "picture", TITLE.js_files, False, (ParamSpec("image", "path", True),),
            "Imagen", "una imagen aprobada", "nada", "bajo", "", "test",
        )  # fmt: skip
        monkeypatch.setitem(COMPONENTS, "picture", picture)
        document = graphics_v1_document()
        document["cues"] = [
            {
                "id": "foto",
                "component": "picture",
                "start": 0,
                "end": 30,
                "params": {"image": "recursos/logo.png"},
            }
        ]
        _write(cut, document)
        (cut / "recursos" / "logo.png").write_bytes(b"not even a picture")
        code, doc, _ = kcut_json("graphics", "check", *project_args(cut))
        assert code == 5 and _codes(doc["errors"]) == ["G10"]
        assert doc["errors"][0]["path"] == "cues[0].params.image"

    def test_graphics_check_codes_only_warnings_is_exit_0(self, cut: Path, kcut_json: Run) -> None:
        code, doc, _ = kcut_json("graphics", "check", *project_args(cut))  # no file: G11
        assert code == 0 and doc["errors"] == [] and _codes(doc["warnings"]) == ["G11"]

    def test_graphics_check_codes_an_edl_with_errors_is_exit_1_with_the_e_codes(
        self, cut: Path, kcut_json: Run
    ) -> None:
        write_graphics_v1(cut, False)
        path = cut / "edit" / "edl-v1.json"
        edl = json.loads(path.read_text(encoding="utf-8"))
        edl["frames"] = 346
        path.write_text(json.dumps(edl), encoding="utf-8")
        code, doc, _ = kcut_json("graphics", "check", *project_args(cut))
        assert code == 1 and doc["ok"] is False
        assert "E08" in _codes(doc["errors"])
        assert (
            doc["cues"] == []
            and doc["chunks"] == []
            and doc["graphics_json"] == "edit/graphics.json"
        )

    def test_graphics_check_codes_a_folder_for_the_file_is_exit_3_not_the_default(
        self, cut: Path, kcut_json: Run
    ) -> None:
        (cut / "edit" / "graphics.json").mkdir()
        code, doc, _ = kcut_json("graphics", "check", *project_args(cut))
        assert code == 3 and doc["error"]["kind"] == "ProjectError"

    def test_graphics_check_codes_broken_json_is_exit_3(self, cut: Path, kcut_json: Run) -> None:
        (cut / "edit" / "graphics.json").write_text("{no es json", encoding="utf-8")
        code, doc, _ = kcut_json("graphics", "check", *project_args(cut))
        assert code == 3 and doc["error"]["kind"] == "ProjectError"

    def test_graphics_check_codes_a_missing_file_is_never_exit_3(
        self, cut: Path, kcut_json: Run
    ) -> None:
        assert not (cut / "edit" / "graphics.json").exists()
        assert kcut_json("graphics", "check", *project_args(cut))[0] == 0
