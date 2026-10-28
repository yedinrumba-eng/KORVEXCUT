"""A sticker with an image that nobody approved is a G10 and `kcut graphics check` exits with 5
(spec S1.7 row 3, 001.15: the gate of the images, DS9). Collected by `test_components_showpiece.py`
(300-line rule); the fixtures (`view_fresh`, `kcut_json`) come from `tests/integration/conftest.py`.

The project is a copy of the synthetic one with the example EDL and `recursos/logo.png`, which
`write_logo` approves in the manifest: each test takes the approval away in its own way.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import LOGO, write_logo
from tests.integration.view_frames_helpers import Run, project_args

STICKER: dict[str, Any] = {
    "id": "mascota",
    "component": "sticker",
    "start": 180,
    "end": 210,
    "params": {"image": LOGO, "exit": "fly_to", "fly_to": {"x": 0.3, "y": 0.4, "at_f": 20}},
}


def _project_with_a_sticker(root: Path) -> None:
    write_edl_v1(root)
    write_logo(root)
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [STICKER]}
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


def _change_manifest(root: Path, change: Callable[[dict[str, Any]], object]) -> None:
    path = root / "recursos" / "recursos.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(json.dumps(document), encoding="utf-8", newline="\n")


def _errors(code: int, doc: dict[str, Any]) -> tuple[int, list[tuple[str, str]]]:
    return code, [(e["code"], e["path"]) for e in doc["errors"]]


def test_sticker_unapproved_exit5(view_fresh: Path, kcut_json: Run) -> None:
    """The image is in the manifest, with an empty `approved_by`."""
    _project_with_a_sticker(view_fresh)
    _change_manifest(view_fresh, lambda d: d["items"][0].update(approved_by=""))
    code, doc, _ = kcut_json("graphics", "check", *project_args(view_fresh))
    assert _errors(code, doc) == (5, [("G10", "cues[0].params.image")]), doc


def test_sticker_not_in_the_manifest_exit5(view_fresh: Path, kcut_json: Run) -> None:
    """The image is a file of `recursos/` that the manifest does not list at all."""
    _project_with_a_sticker(view_fresh)
    _change_manifest(view_fresh, lambda d: d["items"].clear())
    code, doc, _ = kcut_json("graphics", "check", *project_args(view_fresh))
    assert _errors(code, doc) == (5, [("G10", "cues[0].params.image")]), doc


def test_sticker_approved_check_is_exit_0(view_fresh: Path, kcut_json: Run) -> None:
    """The control: with the approval in place the same cue passes, so the 5 above is the gate."""
    _project_with_a_sticker(view_fresh)
    code, doc, _ = kcut_json("graphics", "check", *project_args(view_fresh))
    assert _errors(code, doc) == (0, []), doc
    assert [c["component"] for c in doc["cues"]] == ["sticker"]
    assert doc["cues"][0]["params"]["image"] == LOGO  # the path, never a data URI
