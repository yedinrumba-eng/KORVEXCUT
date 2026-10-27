"""`kcut graphics check` and the limits of `edit/graphics.json` (spec S1.6a round 2, 001.28 point 3;
row 24): a file of more than 1 MiB is not read (exit 3, and the message repeats nothing of it), more
than 500 cues are one G01 (exit 1) and 500 valid cues are `"ok": true`.

Collected from `test_graphics_check.py`, whose `cut` fixture (a copy of the synthetic project with
the example EDL and the transcript of a1 planted) these use.
"""

import json
from pathlib import Path
from typing import Any

from tests.fixtures.synth_graphics import graphics_v1_document
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["TestGraphicsLimits", "TestHideLimits"]
MIB = 1024 * 1024
MARK = "ESTO-NO-SE-REPITE"  # a text in the file that no message may repeat


def _cues(count: int) -> dict[str, Any]:
    cues = [
        {
            "id": f"cue-{i:04d}",
            "component": "label",
            "start": 0,
            "end": 30,
            "params": {"text": "x"},
        }
        for i in range(count)
    ]
    return {"schema": "kcut.graphics/1", "captions": {"enabled": True}, "cues": cues}


def _padded(root: Path, document: dict[str, Any], size: int) -> None:
    """Write `document`, padded with spaces to exactly `size` bytes (it is still JSON)."""
    text = json.dumps(document, ensure_ascii=False, indent=1).encode("utf-8")
    assert len(text) < size
    (root / "edit" / "graphics.json").write_bytes(text + b" " * (size - len(text)))


class TestGraphicsLimits:
    def test_graphics_limits_a_file_over_1_mib_is_exit_3_and_repeats_nothing_of_it(
        self, cut: Path, kcut_json: Run
    ) -> None:
        document = graphics_v1_document()
        document["cues"][2]["params"]["text"] = MARK
        _padded(cut, document, MIB + 1)
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
        assert "pesa más de 1 MB" in doc["error"]["message"]
        assert not any(piece in json.dumps(doc) + err for piece in (MARK, "gancho", "kinetic"))

    def test_graphics_limits_a_file_of_exactly_1_mib_is_read(
        self, cut: Path, kcut_json: Run
    ) -> None:
        _padded(cut, graphics_v1_document(), MIB)
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert [c["id"] for c in doc["cues"]] == ["gancho", "titulo", "pill", "cierre"]

    def test_graphics_limits_501_cues_are_exit_1_with_one_g01_on_cues(
        self, cut: Path, kcut_json: Run
    ) -> None:
        (cut / "edit" / "graphics.json").write_text(
            json.dumps(_cues(501)), encoding="utf-8", newline="\n"
        )
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 1 and doc["ok"] is False, (doc, err)
        assert doc["errors"] == [
            {"code": "G01", "path": "cues", "message": "hay más de 500 cues; kcut no los revisa"}
        ]
        assert doc["cues"] == [] and doc["warnings"] == []

    def test_graphics_limits_500_valid_cues_are_ok(self, cut: Path, kcut_json: Run) -> None:
        (cut / "edit" / "graphics.json").write_text(
            json.dumps(_cues(500)), encoding="utf-8", newline="\n"
        )
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert len(doc["cues"]) == 500 and doc["errors"] == []


def _hide(root: Path, windows: int) -> None:
    document = graphics_v1_document()
    document["captions"] = {"enabled": True, "hide": [{"start": 0, "end": 30}] * windows}
    (root / "edit" / "graphics.json").write_text(
        json.dumps(document), encoding="utf-8", newline="\n"
    )


class TestHideLimits:
    """Row 13 (001.30 point 1): `captions.hide` is capped like the cues, and `--json` lists at most
    `MAX_SHOWN` errors and warnings with their totals, like `edl check --json`."""

    def test_graphics_check_hide_limits_501_windows_are_one_g01_on_captions_hide(
        self, cut: Path, kcut_json: Run
    ) -> None:
        _hide(cut, 501)
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 1 and doc["ok"] is False, (doc, err)
        assert doc["errors"] == [
            {
                "code": "G01",
                "path": "captions.hide",
                "message": "hay más de 500 ventanas en captions.hide; kcut no las revisa",
            }
        ]
        assert (doc["errors_total"], doc["truncated"]) == (1, False)

    def test_graphics_check_hide_limits_500_windows_have_no_g01(
        self, cut: Path, kcut_json: Run
    ) -> None:
        _hide(cut, 500)
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 0 and doc["ok"] is True, (doc, err)
        assert doc["errors"] == [] and doc["errors_total"] == 0

    def test_graphics_check_hide_limits_120_unknown_keys_list_50_and_count_120(
        self, cut: Path, kcut_json: Run
    ) -> None:
        document = {"schema": "kcut.graphics/1", "cues": []}
        document.update({f"clave{i}": 1 for i in range(120)})
        (cut / "edit" / "graphics.json").write_text(
            json.dumps(document), encoding="utf-8", newline="\n"
        )
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))
        assert code == 1 and doc["ok"] is False, (doc, err)
        assert len(doc["errors"]) == 50 and doc["errors_total"] == 120
        assert doc["truncated"] is True and doc["warnings_total"] == len(doc["warnings"])
        assert all(e["code"] == "G01" for e in doc["errors"])
        assert "clave7" not in json.dumps(doc)  # a key that kcut does not know is never repeated

    def test_graphics_check_hide_limits_a_clean_check_reports_totals_and_no_truncation(
        self, cut: Path, kcut_json: Run
    ) -> None:
        code, doc, err = kcut_json("graphics", "check", *project_args(cut))  # no file: G11
        assert code == 0, (doc, err)
        assert (doc["errors_total"], doc["warnings_total"], doc["truncated"]) == (0, 1, False)
