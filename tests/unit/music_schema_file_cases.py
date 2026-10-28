"""The `file` section of `edit/music.json` against the schema (spec S1.8b row 3, 001.15): M03 for
the path and the numbers, M04 for a song that nobody approved (exit 5), the manifest that cannot be
read, and that no message repeats the path of the song. Collected from `test_music_schema.py`
(300-line rule); `project` is its fixture.
"""

import json

import pytest

from kcut.errors import ProjectError
from kcut.issues import exit_code
from kcut.project import Project
from tests.unit.gfx_resolve_fakes import write_manifest
from tests.unit.music_schema_helpers import SECRET
from tests.unit.music_schema_helpers import codes as _codes
from tests.unit.music_schema_helpers import file_doc as _file_doc
from tests.unit.music_schema_helpers import parse as _parse
from tests.unit.music_schema_helpers import song as _song


@pytest.mark.parametrize(
    ("path", "name"),
    [
        ("../tema.wav", "leaves"),
        ("C:/musica/tema.wav", "drive"),
        ("recursos/../crudo/tema.wav", "folder"),
        ("edit/tema.wav", "not-in-recursos"),
        ("recursos/musica/tema.txt", "extension"),
        ("recursos/musica/tema", "no-extension"),
        ("recursos/CON.wav", "reserved"),
    ],
)
def test_music_schema_m03_a_path_that_is_not_a_song_of_recursos(
    project: Project, path: str, name: str
) -> None:
    _song(project)
    doc, found = _parse(project, _file_doc(path=path))
    assert doc is None and _codes(found) == [("M03", "file.path")], (name, found)
    assert path not in found[0].message_es


def test_music_schema_m03_every_extension_of_audio_is_allowed(project: Project) -> None:
    for extension in (".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".MP3"):
        rel = _song(project, f"tema{extension}")
        assert _parse(project, _file_doc(path=rel))[1] == [], extension


def test_music_schema_m03_a_song_that_is_not_there_does_not_exist_approved_or_not(
    project: Project,
) -> None:
    doc, found = _parse(project, _file_doc())  # not in the manifest either
    assert doc is None and _codes(found) == [("M03", "file.path")]
    assert "no existe" in found[0].message_es
    write_manifest(project, "recursos/musica/tema.wav")  # approved, but there is no such file
    doc, found = _parse(project, _file_doc())
    assert doc is None and _codes(found) == [("M03", "file.path")]
    assert "no existe" in found[0].message_es


def test_music_schema_a_manifest_that_cannot_be_read_is_a_project_error_and_not_an_issue(
    project: Project,
) -> None:
    """The file of `music.json` is fine; it is `recursos/recursos.json` that is broken. That is
    exit 3 (as a `sfx.json` that is not JSON), and it says where in the manifest it is wrong."""
    rel = _song(project, approved=None)
    item = {"file": "recursos/otra.png", "kind": "imagen", "origin": "propio", "license": "x"}
    manifest = {
        "schema": "kcut.recursos/1",
        "items": [item],
    }  # without `obtained` and `approved_by`
    (project.root / "recursos" / "recursos.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ProjectError) as info:
        _parse(project, _file_doc(path=rel))
    assert info.value.exit_code == 3 and "items[0].obtained" in info.value.message_es


@pytest.mark.parametrize("key", ["src_in_f", "fade_in_f", "fade_out_f"])
def test_music_schema_m03_a_negative_number_of_the_file(project: Project, key: str) -> None:
    _song(project)
    doc, found = _parse(project, _file_doc(**{key: -1}))
    assert doc is None and _codes(found) == [("M03", f"file.{key}")]


def test_music_schema_m01_the_types_and_the_path_length_of_the_file(project: Project) -> None:
    _song(project)
    for changes, path in (
        ({"path": 3}, "file.path"),
        ({"path": "recursos/" + "a" * 200}, "file.path"),  # 209 characters: max_len is 200
        ({"loop": "si"}, "file.loop"),
        ({"src_in_f": 1.5}, "file.src_in_f"),
        ({"fade_out_f": "36"}, "file.fade_out_f"),
        ({"otra": 1}, "file.<clave desconocida>"),
    ):
        found = _parse(project, _file_doc(**changes))[1]
        assert _codes(found) == [("M01", path)], changes
    assert (
        _parse(project, {"schema": "kcut.music/1", "mode": "file", "file": {}})[1][0].path
        == "file.path"
    )


def test_music_schema_the_file_defaults_are_the_ones_of_the_example(project: Project) -> None:
    rel = _song(project)
    data = {"schema": "kcut.music/1", "mode": "file", "file": {"path": rel}}
    doc, found = _parse(project, data)
    assert found == [] and doc is not None and doc.file is not None
    assert (doc.file.src_in_f, doc.file.loop, doc.file.fade_in_f, doc.file.fade_out_f) == (
        0, False, 0, 36,
    )  # fmt: skip


def test_music_schema_m04_a_song_that_nobody_approved_is_exit_5(project: Project) -> None:
    rel = _song(project, approved=None)  # the file is there, the manifest does not list it
    doc, found = _parse(project, _file_doc(path=rel))
    assert doc is None and _codes(found) == [("M04", "file.path")]
    assert exit_code(found) == 5
    assert "manifiesto" in found[0].message_es and "tema" not in found[0].message_es


def test_music_schema_m04_a_song_without_approved_by_is_exit_5(project: Project) -> None:
    rel = _song(project, approved="")
    doc, found = _parse(project, _file_doc(path=rel))
    assert doc is None and _codes(found) == [("M04", "file.path")] and exit_code(found) == 5
    assert "approved_by" in found[0].message_es


def test_music_schema_m04_wins_the_exit_over_the_other_errors(project: Project) -> None:
    rel = _song(project, approved=None)
    data = _file_doc(path=rel, src_in_f=-3)
    found = _parse(project, data)[1]
    assert sorted(i.code for i in found) == ["M03", "M04"] and exit_code(found) == 5
    assert exit_code([i for i in found if i.code == "M03"]) == 1


def test_music_schema_the_song_is_approved_and_good(project: Project) -> None:
    rel = _song(project)
    doc, found = _parse(project, _file_doc(path=rel, src_in_f=15, fade_in_f=15))
    assert found == [] and doc is not None and doc.file is not None
    assert (doc.mode, doc.file.path, doc.file.src_in_f, doc.file.loop) == ("file", rel, 15, True)


def test_music_schema_no_message_repeats_the_path_of_the_song(project: Project) -> None:
    rel = _song(project, f"{SECRET}.mp3", approved=None)
    outside = f"../{SECRET}.mp3"
    for path in (rel, outside, f"edit/{SECRET}.mp3", f"recursos/{SECRET}.txt"):
        found = _parse(project, _file_doc(path=path))[1]
        shown = " ".join(i.path + i.message_es for i in found)
        assert found and [s for s in SECRET.split("-") if s in shown] == [], (path, shown)


__all__ = [
    "test_music_schema_a_manifest_that_cannot_be_read_is_a_project_error_and_not_an_issue",
    "test_music_schema_m01_the_types_and_the_path_length_of_the_file",
    "test_music_schema_m03_a_negative_number_of_the_file",
    "test_music_schema_m03_a_path_that_is_not_a_song_of_recursos",
    "test_music_schema_m03_a_song_that_is_not_there_does_not_exist_approved_or_not",
    "test_music_schema_m03_every_extension_of_audio_is_allowed",
    "test_music_schema_m04_a_song_that_nobody_approved_is_exit_5",
    "test_music_schema_m04_a_song_without_approved_by_is_exit_5",
    "test_music_schema_m04_wins_the_exit_over_the_other_errors",
    "test_music_schema_no_message_repeats_the_path_of_the_song",
    "test_music_schema_the_file_defaults_are_the_ones_of_the_example",
    "test_music_schema_the_song_is_approved_and_good",
]
