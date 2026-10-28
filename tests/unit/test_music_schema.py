"""The schema of `edit/music.json` and each code M01 to M05 with a case (spec S1.8b row 3, 001.15).

M01 the shape, M02 the `synth`, M03 the `file`, M04 a song that nobody approved (exit 5), M05 a
window or a frame outside the video. A message never repeats text of the file nor the path of the
song. The project is a temporary folder and the EDL is the example (345 frames).
"""

import json
from pathlib import Path
from typing import Any

import pytest

from kcut.issues import exit_code
from kcut.project import Project
from tests.fixtures.synth_audio import music_plan_document
from tests.unit.gfx_resolve_fakes import make_project
from tests.unit.music_schema_file_cases import *  # noqa: F403  (the `file`: 300-line rule)
from tests.unit.music_schema_helpers import FRAMES
from tests.unit.music_schema_helpers import codes as _codes
from tests.unit.music_schema_helpers import parse as _parse
from tests.unit.music_schema_helpers import synth_doc as _synth_doc
from tests.unit.music_schema_helpers import with_synth as _with_synth
from tests.unit.music_schema_shape_cases import *  # noqa: F403  (the shape: 300-line rule)


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


@pytest.mark.parametrize(
    ("data", "path"),
    [
        (_with_synth(mute_drums=[{"start": 5, "end": 5}]), "synth.mute_drums[0]"),
        (_with_synth(mute_drums=[{"start": 9, "end": 5}]), "synth.mute_drums[0]"),
        (_with_synth(mute_drums=[{"start": -1, "end": 5}]), "synth.mute_drums[0]"),
        (_with_synth(mute_drums=[{"start": 0, "end": FRAMES + 1}]), "synth.mute_drums[0]"),
        (_with_synth(stop_drums_f=FRAMES + 1), "synth.stop_drums_f"),
        (_with_synth(stop_drums_f=-1), "synth.stop_drums_f"),
        (_with_synth(origin_f=FRAMES + 1), "synth.origin_f"),
        (_with_synth(origin_f=-1), "synth.origin_f"),
        (_synth_doc(windows=[{"start": 5, "end": 5, "gain_db": 1}]), "windows[0]"),
        (_synth_doc(windows=[{"start": 0, "end": FRAMES + 1, "gain_db": 1}]), "windows[0]"),
        (_synth_doc(windows=[{"start": -2, "end": 4, "gain_db": 1}]), "windows[0]"),
    ],
)
def test_music_schema_m05_a_window_or_a_frame_outside_the_video(
    project: Project, data: dict[str, Any], path: str
) -> None:
    doc, found = _parse(project, data)
    assert doc is None and _codes(found) == [("M05", path)] and exit_code(found) == 1


def test_music_schema_m05_the_edges_of_the_video_are_inside(project: Project) -> None:
    data = _with_synth(
        mute_drums=[{"start": 0, "end": FRAMES}], stop_drums_f=FRAMES, origin_f=FRAMES
    )
    data["windows"] = [{"start": FRAMES - 1, "end": FRAMES, "gain_db": -24}]
    assert _parse(project, data)[1] == []


def test_music_schema_a_message_never_repeats_text_of_the_file(project: Project) -> None:
    data = {"schema": "kcut.music/1", "mode": "IGNORE-PREVIOUS", "IGNORE-KEY": 1}
    found = _parse(project, data)[1]
    assert found and "IGNORE" not in json.dumps([(i.path, i.message_es) for i in found])


def test_music_schema_the_document_survives_json(project: Project) -> None:
    again = json.loads(json.dumps(music_plan_document()))
    doc, found = _parse(project, again)
    assert found == [] and doc is not None
