"""`kcut graphics check` and the times that fall where nobody will see them (spec S1.8a step 0,
001.35 point 9; row 16): the G03 warnings of `resolve` are listed, and the exit code stays 0. The
cases of each component are in `tests/unit/test_showpiece_time_warnings.py`; here is the command,
on the synthetic project with the example EDL and `recursos/logo.png` approved.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import LOGO, write_logo
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]


def _write(root: Path, cues: list[dict[str, Any]]) -> None:
    write_edl_v1(root)
    write_logo(root)
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": cues}
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


def _cues(steps_at: int, holo_at: int, fly_at: int) -> list[dict[str, Any]]:
    """`pasos` (60 frames), `holo` (45) and `mascota` (30) with the time of each one given."""
    items = [{"at_f": a, "label": "P", "text": "paso"} for a in (0, steps_at)]
    fly = {"x": 0.3, "y": 0.4, "at_f": fly_at}
    return [
        {"id": "pasos", "component": "steps", "start": 210, "end": 270, "params": {"items": items}},
        {
            "id": "holo",
            "component": "holo_board",
            "start": 270,
            "end": 315,
            "params": {"text": "HOLA", "type_at_f": holo_at},
        },
        {
            "id": "mascota",
            "component": "sticker",
            "start": 180,
            "end": 210,
            "params": {"image": LOGO, "exit": "fly_to", "fly_to": fly},
        },
    ]


def test_showpiece_time_warnings_graphics_check_lists_them_and_exits_0(
    view_fresh: Path, kcut_json: Run
) -> None:
    _write(view_fresh, _cues(steps_at=60, holo_at=45, fly_at=28))
    code, doc, _ = kcut_json("graphics", "check", *project_args(view_fresh))
    assert code == 0 and doc["ok"] is True and doc["errors"] == [], doc
    found = [(w["code"], w["path"]) for w in doc["warnings"]]
    assert found == [
        ("G03", "cues[0].params.items[1].at_f"),
        ("G03", "cues[1].params.type_at_f"),
        ("G03", "cues[2].params.fly_to.at_f"),
    ], doc["warnings"]
    messages = [w["message"] for w in doc["warnings"]]
    assert messages[0] == "steps.items[1].at_f cae en o después del final del cue; no se va a ver"
    assert messages[1] == "holo_board.type_at_f cae en o después del final del cue; no se va a ver"
    assert messages[2] == "el vuelo del sticker dura menos de 0.12 s"
    assert [c["id"] for c in doc["cues"]] == ["pasos", "holo", "mascota"]  # the cues are all there


def test_showpiece_time_warnings_times_inside_the_cues_give_no_warning(
    view_fresh: Path, kcut_json: Run
) -> None:
    _write(view_fresh, _cues(steps_at=59, holo_at=44, fly_at=20))
    code, doc, _ = kcut_json("graphics", "check", *project_args(view_fresh))
    assert code == 0 and doc["errors"] == [] and doc["warnings"] == [], doc
