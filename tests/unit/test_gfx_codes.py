"""Every code G01 to G12 has a case that triggers it (spec S1.6a row 4), through `resolve`, the
function `graphics check` calls. No ffmpeg: `kept_words` is replaced, the EDL is the example of the
spec (345 frames; `a1` frames 60-239 heard from output frame 30) and the project is a temporary
folder. The exit codes of the command are in `tests/integration/test_graphics_check.py`.
"""

from pathlib import Path
from typing import Any

import pytest

from kcut.errors import ProjectError
from kcut.issues import Issue, exit_code
from kcut.project import Project
from tests.unit.edl_fakes import edit, parsed
from tests.unit.gfx_codes_images import *  # noqa: F403  (the images: 300-line rule)
from tests.unit.gfx_resolve_fakes import (
    codes,
    fake_kept,
    make_project,
    run_resolve,
    with_captions,
    word,
    write_graphics,
)
from tests.unit.gfx_resolve_fakes import (
    doc_without_captions as _doc,
)
from tests.unit.gfx_resolve_fakes import (
    errors_of as _errors,
)


@pytest.fixture
def project(tmp_path: Path) -> Project:
    return make_project(tmp_path)


def test_gfx_codes_a_good_document_has_no_issue_at_all(project: Project) -> None:
    write_graphics(project, _doc())
    resolved = run_resolve(project)
    assert resolved.issues == [] and [c.id for c in resolved.cues] == [
        "gancho",
        "titulo",
        "pill",
        "cierre",
    ]
    assert exit_code(resolved.issues) == 0


def test_gfx_codes_g01_the_schema_of_the_file(project: Project) -> None:
    write_graphics(project, _doc(lambda d: d.update(schema="nope")))
    resolved = run_resolve(project)
    assert (
        codes(resolved) == [("G01", "schema")]
        and resolved.cues == ()
        and exit_code(resolved.issues) == 1
    )


def test_gfx_codes_g02_a_component_that_does_not_exist_or_is_internal(project: Project) -> None:
    write_graphics(project, _doc(lambda d: d["cues"][0].update(component="fireworks")))
    assert codes(run_resolve(project)) == [("G02", "cues[0].component")]
    write_graphics(project, _doc(lambda d: d["cues"][0].update(component="captions")))
    assert codes(run_resolve(project)) == [("G02", "cues[0].component")]


def test_gfx_codes_g03_a_parameter_that_is_not_valid_drops_the_cue(project: Project) -> None:
    def change(d: dict[str, Any]) -> None:
        d["cues"][1]["params"]["size"] = True  # a bool is not a size
        d["cues"][2]["params"]["nope"] = 1
        d["cues"][3]["params"]["lines"][0]["color"] = "verde"
        del d["cues"][0]["params"]["lines"]

    write_graphics(project, _doc(change))
    resolved = run_resolve(project)
    assert _errors(resolved) == [
        ("G03", "cues[0].params.lines"),
        ("G03", "cues[1].params.size"),
        ("G03", "cues[2].params.<clave desconocida>"),
        ("G03", "cues[3].params.lines[0].color"),
    ]
    assert resolved.cues == ()  # every cue had a problem
    assert exit_code(resolved.issues) == 1


def test_gfx_codes_g04_a_word_that_the_cut_does_not_keep(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_kept(monkeypatch, [word(1, "hola", 40, 52)])

    def change(d: dict[str, Any]) -> None:
        d["cues"][1]["start"] = {"word": "a1:w0099", "edge": "start"}
        d["cues"][2]["end"] = {"word": "a1:w0001", "edge": "end", "offset_f": 100}  # fine: kept
        d["captions"] = {
            "enabled": False,
            "hide": [{"start": 0, "end": {"word": "a1:w0098", "edge": "end"}}],
        }

    write_graphics(project, _doc(change))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G04", "captions.hide[0].end"), ("G04", "cues[1].start")]
    assert [c.id for c in resolved.cues] == ["gancho", "pill", "cierre"]
    assert [c.end_f for c in resolved.cues if c.id == "pill"] == [152]  # 52 + 100: that one is kept


def test_gfx_codes_g04_a_word_that_is_kept_resolves_with_its_offset(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_kept(monkeypatch, [word(1, "hola", 40, 52)])

    def change(d: dict[str, Any]) -> None:
        d["cues"][1]["start"] = {"word": "a1:w0001", "edge": "start", "offset_f": -1}
        d["cues"][1]["end"] = {"word": "a1:w0001", "edge": "start", "offset_f": 30}

    write_graphics(project, _doc(change))
    resolved = run_resolve(project)
    assert resolved.issues == []
    title = next(c for c in resolved.cues if c.id == "titulo")
    assert (title.start_f, title.end_f) == (39, 70)


def test_gfx_codes_g05_a_frame_of_a_source_that_is_not_heard(project: Project) -> None:
    def change(d: dict[str, Any]) -> None:
        d["cues"][0]["end"] = {"src": "a1", "f": 10}  # a1 frames 0-59 were cut
        d["cues"][1]["start"] = {"src": "a1", "f": 100}  # heard at output frame 70
        d["cues"][1]["end"] = {"src": "a1", "f": 130, "offset_f": 1}  # 101

    write_graphics(project, _doc(change))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G05", "cues[0].end")]
    title = next(c for c in resolved.cues if c.id == "titulo")
    assert (title.start_f, title.end_f) == (70, 101)


def test_gfx_codes_g06_a_frame_heard_in_several_places_is_a_warning_and_the_first_is_used(
    project: Project,
) -> None:
    twice = parsed(
        edit(
            lambda d: d.update(
                clips=[
                    {"kind": "voice", "at_f": 0, "src": "a1", "in_f": 60, "out_f": 120, "why": "x"},
                    {
                        "kind": "voice",
                        "at_f": 100,
                        "src": "a1",
                        "in_f": 90,
                        "out_f": 150,
                        "why": "x",
                    },
                ]
            )
        )
    )
    write_graphics(
        project, _doc(lambda d: d["cues"][1].update(start={"src": "a1", "f": 100}, end=200))
    )
    resolved = run_resolve(project, twice)
    assert [(i.code, i.level, i.path) for i in resolved.issues] == [
        ("G06", "warning", "cues[1].start")
    ]
    assert (
        next(c for c in resolved.cues if c.id == "titulo").start_f == 40
    )  # the first: 0 + (100 - 60)
    assert exit_code(resolved.issues) == 0  # a warning never changes the exit code


@pytest.mark.parametrize(
    ("start", "end", "where"),
    [
        (10, 10, "cues[1]"),
        (20, 10, "cues[1]"),
        (-1, 10, "cues[1]"),
        (0, 346, "cues[1]"),
        (346, 400, "cues[1]"),
    ],
)
def test_gfx_codes_g07_a_cue_has_to_fit_in_the_video(
    project: Project, start: int, end: int, where: str
) -> None:
    write_graphics(project, _doc(lambda d: d["cues"][1].update(start=start, end=end)))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G07", where)]
    assert "titulo" not in [c.id for c in resolved.cues]


def test_gfx_codes_g07_the_whole_video_fits_and_a_hidden_window_must_fit_too(
    project: Project,
) -> None:
    write_graphics(project, _doc(lambda d: d["cues"][1].update(start=0, end=345)))
    assert run_resolve(project).issues == []
    window = {"enabled": False, "hide": [{"start": 300, "end": 400}]}
    write_graphics(project, _doc(lambda d: d.update(captions=window)))
    assert _errors(run_resolve(project)) == [("G07", "captions.hide[0]")]


def test_gfx_codes_g07_the_message_does_not_repeat_a_huge_number(project: Project) -> None:
    write_graphics(project, _doc(lambda d: d["cues"][1].update(end=10**30)))
    (issue,) = [i for i in run_resolve(project).issues if i.code == "G07"]
    assert "10000000000000000000000000000" not in issue.message_es and len(issue.message_es) < 200


def test_gfx_codes_g08_subtitles_on_and_a_voice_clip_with_no_transcript(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_kept(monkeypatch, [], missing=("a1",))
    write_graphics(project, _doc(lambda d: d.update(captions={"enabled": True})))
    resolved = run_resolve(project)
    assert _errors(resolved) == [("G08", "captions")]
    message = resolved.issues[0].message_es
    assert "a1" in message and "kcut transcribe" in message and "captions.enabled=false" in message
    assert exit_code(resolved.issues) == 1


def test_gfx_codes_g08_with_the_subtitles_off_a_missing_transcript_is_fine(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_kept(monkeypatch, [], missing=("a1",))
    write_graphics(project, _doc())
    assert run_resolve(project).issues == [] and calls == []  # it did not even look for words


def test_gfx_codes_g11_no_file_and_subtitles_on(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_kept(monkeypatch, [word(1, "hola", 40, 52)])
    resolved = run_resolve(project)
    (issue,) = resolved.issues
    assert (issue.code, issue.level, issue.path) == ("G11", "warning", "")
    assert issue.message_es == (
        "no hay edit/graphics.json: subtítulos por defecto desde la transcripción"
    )
    assert resolved.source == "default" and resolved.graphics_json is None and not resolved.empty
    assert exit_code(resolved.issues) == 0


def test_gfx_codes_g12_no_file_and_subtitles_off(
    project: Project, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_kept(monkeypatch, [word(1, "hola", 40, 52)])
    resolved = run_resolve(with_captions(project, enabled=False))
    (issue,) = resolved.issues
    assert (issue.code, issue.level, issue.path) == ("G12", "warning", "")
    assert issue.message_es == (
        "no hay edit/graphics.json y los subtítulos están apagados: el video sale sin gráficos"
    )
    assert resolved.empty and resolved.cues == () and resolved.chunks == [] and calls == []
    assert exit_code(resolved.issues) == 0


def test_gfx_codes_a_folder_in_place_of_the_file_is_a_project_error_not_g11(
    project: Project,
) -> None:
    (project.root / "edit" / "graphics.json").mkdir()
    with pytest.raises(ProjectError):
        run_resolve(project)


def test_gfx_codes_the_exit_code_is_5_for_g10_1_for_any_other_error_and_0_for_warnings() -> None:
    def err(code: str) -> Issue:
        return Issue(code, "error", "p", "m")

    assert exit_code([err("G10")]) == 5 and exit_code([err("G10"), err("G03")]) == 5
    assert all(exit_code([err(f"G{n:02d}")]) == 1 for n in (1, 2, 3, 4, 5, 7, 8, 9))
    warnings = [Issue("G06", "warning", "p", "m"), Issue("G11", "warning", "", "m")]
    assert exit_code(warnings) == 0
