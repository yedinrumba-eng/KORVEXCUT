"""The path of a sticker's image is not repeated on the console, on stderr or in `--json`
(spec S1.8a step 0, 001.35 point 1; row 8). The image is `recursos/Maria-809-555-1234.png`: a
name that holds a phone number, and Claude reads what `kcut` prints.

Three cases, each one in the three outputs: the image is not in the manifest (G10, exit 5), the
manifest is broken and quotes a path that leaves the project (G09), and a path of 100 000
characters (G03, exit 1, and not the exit 10 that it used to be). The project is a copy of the
synthetic one, and the command runs in this process (`cli.main`).
"""

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from kcut import cli
from tests.fixtures.synth_edl import write_edl_v1
from tests.integration.view_frames_helpers import project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
NAME = "Maria-809-555-1234"
SECRETS = ("Maria", "809", "555", "1234")
IMAGE = f"recursos/{NAME}.png"


def _project_with_a_sticker(root: Path, image: str) -> None:
    write_edl_v1(root)
    cue = {
        "id": "mascota",
        "component": "sticker",
        "start": 180,
        "end": 210,
        "params": {"image": image},
    }
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(root / "recursos" / f"{NAME}.png")


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str, dict[str, Any]]:
    """The exit code, stdout and stderr of the human output, and the document of `--json`."""
    capsys.readouterr()
    code = cli.main(list(args))
    plain = capsys.readouterr()
    json_code = cli.main([*args, "--json"])
    as_json = capsys.readouterr()
    assert json_code == code
    return code, plain.out, plain.err + as_json.err, json.loads(as_json.out)


def _nothing_secret(*texts: str) -> None:
    for text in texts:
        assert [s for s in SECRETS if s in text] == [], text


def test_image_path_not_echoed_cli_a_sticker_that_nobody_approved_is_exit_5(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project_with_a_sticker(view_fresh, IMAGE)
    code, out, err, doc = _run(capsys, "graphics", "check", *project_args(view_fresh))
    assert code == 5
    _nothing_secret(out, err, json.dumps(doc, ensure_ascii=False))
    (error,) = doc["errors"]
    assert error["code"] == "G10" and error["path"] == "cues[0].params.image"
    assert error["message"] == (
        "el recurso no está en el manifiesto recursos/recursos.json: "
        "pide aprobación antes de usarlo"
    )
    assert "G10" in out  # the human output says it too


def test_image_path_not_echoed_cli_the_capture_gate_does_not_repeat_it_either(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`graphics capture` stops with exit 5 on the G10 before any Chromium starts."""
    _project_with_a_sticker(view_fresh, IMAGE)
    code, out, err, doc = _run(capsys, "graphics", "capture", *project_args(view_fresh))
    assert code == 5 and doc["error"]["kind"] == "GateError"
    _nothing_secret(out, err, json.dumps(doc, ensure_ascii=False))


def test_image_path_not_echoed_cli_a_broken_manifest_that_quotes_a_path_out_of_the_project(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project_with_a_sticker(view_fresh, IMAGE)
    item = {
        "file": f"../{NAME}.png",
        "kind": "imagen",
        "origin": "propio",
        "license": "propia",
        "obtained": "2026-10-27",
        "approved_by": "test",
    }
    manifest = {"schema": "kcut.recursos/1", "items": [item]}
    (view_fresh / "recursos" / "recursos.json").write_text(json.dumps(manifest), encoding="utf-8")
    code, out, err, doc = _run(capsys, "graphics", "check", *project_args(view_fresh))
    assert code == 1  # a G09: the manifest cannot be used
    _nothing_secret(out, err, json.dumps(doc, ensure_ascii=False))
    (error,) = doc["errors"]
    assert error["code"] == "G09" and error["path"] == "cues[0].params.image"


def test_image_path_not_echoed_cli_a_path_of_100000_characters_is_a_g03_and_exit_1(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project_with_a_sticker(view_fresh, "recursos/" + "a" * 99_991)
    code, out, err, doc = _run(capsys, "graphics", "check", *project_args(view_fresh))
    assert code == 1  # not 10
    assert [(e["code"], e["path"]) for e in doc["errors"]] == [("G03", "cues[0].params.image")]
    assert len(out) + len(err) + len(json.dumps(doc)) < 20_000  # the path itself is not printed
