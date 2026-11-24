"""A mix that is louder than 0 LUFS before `loudnorm` is an error of the plan, not of the tool
(spec 001.38, point 1; S1.9a row 11). With gains that the schemas allow (`music.json` with
`gain_db: +6` and a window of +12, or `sfx.json` with `bus_gain_db: +12` and a window of +12) the
first pass measures over 0 LUFS and ffmpeg refuses that `measured_I` in the second pass: `kcut mix`
used to exit 4 with ffmpeg's own message. Measured with the synthetic project: the music with those
gains alone gives +1.3 LUFS, but the ducking brings the mix to -0.7, so the ducking is off in that
test; the bus of the effects at +12 alone gives -4.1, so it has the window too. Now it is exit 1
(CheckFailed), with a text that says what to lower, and no file of the mix is left half written.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration.mix_helpers import BUILD, FRAMES, audio_project
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
TOO_LOUD = (
    "la mezcla pasa de 0 LUFS antes de normalizar; baja las ganancias de la música o de los efectos"
)


def _write(root: Path, name: str, document: dict[str, Any]) -> None:
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    (root / "edit" / name).write_text(text, encoding="utf-8", newline="\n")


def _read(root: Path, name: str) -> dict[str, Any]:
    document: dict[str, Any] = json.loads((root / "edit" / name).read_text(encoding="utf-8"))
    return document


def _refused(code: int, doc: dict[str, Any], err: str, root: Path) -> None:
    assert code == 1 and doc["ok"] is False, (doc, err)
    assert doc["error"]["kind"] == "CheckFailed" and doc["error"]["message"] == TOO_LOUD
    assert "measured_I" not in json.dumps(doc) + err  # ffmpeg's own message is not the answer
    assert not (root / BUILD / "mix.wav").exists()
    assert not list((root / BUILD).glob("*.partial*"))


def test_loudnorm_ranges_music_gain_plus_6_and_a_window_of_plus_12_is_exit_1(
    view_fresh: Path, kcut_json: Run
) -> None:
    root = audio_project(view_fresh)
    music = _read(root, "music.json")
    music["gain_db"] = 6.0
    music["windows"] = [{"start": 0, "end": FRAMES, "gain_db": 12.0}]
    music["duck"]["enabled"] = False  # with the ducking on, the voice lowers it under 0 LUFS
    _write(root, "music.json", music)
    code, doc, err = kcut_json("mix", *project_args(root))
    _refused(code, doc, err, root)


def test_loudnorm_ranges_sfx_bus_gain_plus_12_is_exit_1(view_fresh: Path, kcut_json: Run) -> None:
    root = audio_project(view_fresh, music=False)
    sfx = _read(root, "sfx.json")
    sfx["bus_gain_db"] = 12.0
    sfx["windows"] = [{"start": 0, "end": FRAMES, "gain_db": 12.0}]  # the bus alone gives -4 LUFS
    _write(root, "sfx.json", sfx)
    code, doc, err = kcut_json("mix", *project_args(root))
    _refused(code, doc, err, root)


def test_loudnorm_ranges_a_mix_with_the_gains_of_the_spec_goes_through(
    view_fresh: Path, kcut_json: Run
) -> None:
    root = audio_project(view_fresh)
    code, doc, err = kcut_json("mix", *project_args(root))
    assert code == 0 and doc["ok"] is True, (doc, err)
