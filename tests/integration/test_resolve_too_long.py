"""A path that the system cannot resolve ends in a message, not in exit 10 (spec S1.8b step 0,
001.36 point 5; row 16). The manifest has a `file` of 40 000 characters: `Path.resolve`
raises `ValueError` and the command used to end as an `InternalError`. The unit side is in
`tests/unit/test_resolve_too_long.py`; here it is the command: `graphics check`, where the image
cannot be used (a G09, exit 1) and `kcut mix`, where the music file cannot be (exit 3).
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from kcut import cli
from kcut.audio.wavio import write_wav_s16_mono
from tests.fixtures.synth_edl import write_edl_v1
from tests.integration.mix_helpers import audio_project
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
UNRESOLVABLE = "la ruta no se puede resolver"


def _broken_manifest(root: Path) -> None:
    item = {
        "file": "recursos/" + "a" * 40000,
        "kind": "imagen",
        "origin": "propio",
        "license": "propia",
        "obtained": "2026-10-28",
        "approved_by": "test",
    }
    manifest = {"schema": "kcut.recursos/1", "items": [item]}
    (root / "recursos" / "recursos.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_resolve_too_long_graphics_check_with_a_manifest_file_of_40000_characters_is_not_exit_10(
    view_fresh: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_edl_v1(view_fresh)
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(view_fresh / "recursos" / "logo.png")
    params = {"image": "recursos/logo.png"}
    cue = {"id": "m", "component": "sticker", "start": 180, "end": 210, "params": params}
    document = {"schema": "kcut.graphics/1", "captions": {"enabled": False}, "cues": [cue]}
    (view_fresh / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")
    _broken_manifest(view_fresh)
    capsys.readouterr()
    code = cli.main(["graphics", "check", *project_args(view_fresh), "--json"])
    out: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert code == 1, out  # a G09 about the image, and not the exit 10 of a ValueError
    (error,) = out["errors"]
    assert error["code"] == "G09" and error["path"] == "cues[0].params.image"
    assert UNRESOLVABLE in error["message"] and "aaaa" not in error["message"]


def test_resolve_too_long_mix_with_a_manifest_file_of_40000_characters_is_exit_3_with_that_text(
    view_fresh: Path, kcut_json: Run
) -> None:
    """`kcut mix` with a song of `recursos/`: the manifest cannot be read because one of its `file`
    is a path that the system cannot resolve. It is exit 3 with the fixed text and where in the
    manifest it is (`items[0].file`), not exit 10, and nothing of that path is printed."""
    root = audio_project(view_fresh, music=False)
    (root / "recursos" / "musica").mkdir(parents=True, exist_ok=True)
    write_wav_s16_mono(root / "recursos" / "musica" / "tema.wav", np.zeros(4800, np.float32), 48000)
    _broken_manifest(root)
    music = {"schema": "kcut.music/1", "mode": "file", "file": {"path": "recursos/musica/tema.wav"}}
    (root / "edit" / "music.json").write_text(json.dumps(music), encoding="utf-8")
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 3 and doc["error"]["kind"] == "ProjectError", (doc, err)
    message = doc["error"]["message"]
    assert UNRESOLVABLE in message and "items[0].file" in message and "aaaa" not in message
