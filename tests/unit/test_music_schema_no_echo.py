"""`music.json` never has its own text echoed back, and its frames have a ceiling (spec S1.8b round
1, 001.37 point 6; row 29).

A value that is not a number comes out of `params._shown` (`<texto, N car.>` for a text) and not
from `repr` cut to 40 characters, which repeated up to 37 characters of the file: Claude reads what
`kcut mix` prints, and the text can be a phone number a person said. Same as `sfx_schema`, whose
messages come out of `check_params`. And `src_in_f`, `fade_in_f` and `fade_out_f` go up to
2 592 000 frames (12 h at 60 fps, the ceiling of the EDL): more is an M03 (exit 1); before, a
`src_in_f` of `10**18` went on to `ffmpeg` and came back as a ToolError (exit 4).
"""

from pathlib import Path

import pytest

from kcut.issues import exit_code
from kcut.project import Project
from tests.unit.gfx_resolve_fakes import make_project
from tests.unit.music_schema_helpers import (
    codes,
    file_doc,
    parse,
    song,
    synth_doc,
    with_synth,
)

TEXT = "Maria 809-555-1234 …"  # 20 characters
LEAKS = ("Maria", "809", "555", "1234", "…")
MAX_F = 2_592_000


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


@pytest.mark.parametrize(
    ("data", "path"),
    [
        (synth_doc(gain_db=TEXT), "gain_db"),
        (with_synth(bpm=TEXT), "synth.bpm"),
        (synth_doc(windows=[{"start": 0, "end": 30, "gain_db": TEXT}]), "windows[0].gain_db"),
    ],
)
def test_music_schema_no_echo_a_text_where_a_number_goes_is_its_length_and_not_the_text(
    project: Project, data: dict[str, object], path: str
) -> None:
    doc, found = parse(project, data)
    assert doc is None and codes(found) == [("M01", path)], found
    message = found[0].message_es
    assert message == "debe ser un número (vino <texto, 20 car.>)"
    assert not any(piece in message for piece in LEAKS)


def test_music_schema_no_echo_a_number_out_of_range_still_says_what_came(
    project: Project,
) -> None:
    _, found = parse(project, synth_doc(gain_db=99))
    assert codes(found) == [("M01", "gain_db")] and "(vino 99)" in found[0].message_es
    _, found = parse(project, with_synth(bpm=10**30))
    assert codes(found) == [("M02", "synth.bpm")] and "10000000000000000000" in found[0].message_es


@pytest.mark.parametrize("name", ["src_in_f", "fade_in_f", "fade_out_f"])
def test_music_schema_no_echo_a_frame_over_12_hours_at_60_fps_is_m03_and_exit_1(
    project: Project, name: str
) -> None:
    song(project)
    for value in (MAX_F + 1, 10**18, 10**298):
        doc, found = parse(project, file_doc(**{name: value}))
        assert doc is None and codes(found) == [("M03", f"file.{name}")], (name, value, found)
        assert exit_code(found) == 1
        assert not any(digit * 8 in found[0].message_es for digit in "0123456789")
    doc, found = parse(project, file_doc(**{name: MAX_F}))
    assert found == [] and doc is not None  # the ceiling itself is fine


def test_music_schema_no_echo_a_negative_frame_is_still_m03(project: Project) -> None:
    song(project)
    _, found = parse(project, file_doc(src_in_f=-1))
    assert codes(found) == [("M03", "file.src_in_f")] and exit_code(found) == 1
