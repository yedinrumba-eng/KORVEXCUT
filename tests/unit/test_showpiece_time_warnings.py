"""`resolve` warns when a time of a component falls where nobody will see it (spec S1.8a step 0,
001.35 point 9; row 16). The warning is a G03 at the `warning` level, so it never changes the exit
code: the cue may still be made longer. Times are relative to the start of the cue, and the cue
here is `[100, 100 + length)` of the example EDL (345 frames at 30 fps).

- `steps.items[N].at_f`, `holo_board.type_at_f` and `sticker.fly_to.at_f` at or after the length of
  the cue: `<parámetro> cae en o después del final del cue; no se va a ver`;
- `sticker.fly_to.at_f` in the last 0.12 s of the cue (at 30 fps, the last 3 frames, or fewer when
  it is at the end already): `el vuelo del sticker dura menos de 0.12 s`.
"""

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from kcut.issues import Issue, exit_code
from kcut.project import Project
from tests.unit.gfx_resolve_fakes import (
    doc_without_captions,
    make_project,
    run_resolve,
    write_graphics,
    write_manifest,
)

LENGTH = 30
END = " cae en o después del final del cue; no se va a ver"
SHORT_FLIGHT = "el vuelo del sticker dura menos de 0.12 s"


@pytest.fixture
def project(tmp_path: Path) -> Project:
    made = make_project(tmp_path)
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(made.root / "recursos" / "logo.png")
    write_manifest(made, "recursos/logo.png")
    return made


def _cue(project: Project, component: str, params: dict[str, Any], length: int = LENGTH) -> None:
    cue = {
        "id": "uno",
        "component": component,
        "start": 100,
        "end": 100 + length,
        "params": params,
    }
    write_graphics(project, doc_without_captions(lambda d: d.update(cues=[cue])))


def _steps(*at: int) -> dict[str, Any]:
    return {"items": [{"at_f": a, "label": f"P{i}", "text": f"paso {i}"} for i, a in enumerate(at)]}


def _sticker(at_f: int, **extra: Any) -> dict[str, Any]:
    fly = {"x": 0.3, "y": 0.4, "at_f": at_f}
    return {"image": "recursos/logo.png", "exit": "fly_to", "fly_to": fly, **extra}


def _warnings(project: Project) -> list[tuple[str, str, str]]:
    """`(code, path, message)` of the warnings; the document has to have no error."""
    resolved = run_resolve(project)
    assert [i for i in resolved.issues if i.level == "error"] == [], resolved.issues
    assert exit_code(resolved.issues) == 0  # a warning never changes the exit
    return [(i.code, i.path, i.message_es) for i in resolved.issues if i.level == "warning"]


def test_showpiece_time_warnings_steps_at_or_after_the_end_of_the_cue(project: Project) -> None:
    _cue(project, "steps", _steps(0, 10, LENGTH))
    assert _warnings(project) == [
        ("G03", "cues[0].params.items[2].at_f", "steps.items[2].at_f" + END)
    ]
    _cue(project, "steps", _steps(0, LENGTH + 5, LENGTH + 20))  # each one that does not show
    found = _warnings(project)
    assert [path for _, path, _ in found] == [
        "cues[0].params.items[1].at_f",
        "cues[0].params.items[2].at_f",
    ]
    assert all(code == "G03" and text.endswith(END) for code, _, text in found)


def test_showpiece_time_warnings_steps_inside_the_cue_have_none(project: Project) -> None:
    _cue(project, "steps", _steps(0, 10, LENGTH - 1))  # the last frame of the cue is `LENGTH - 1`
    assert _warnings(project) == []
    assert run_resolve(project).issues == []


def test_showpiece_time_warnings_holo_type_at_f_at_or_after_the_end(project: Project) -> None:
    holo = {"text": "HOLA", "type_at_f": 45}
    _cue(project, "holo_board", holo, length=45)
    assert _warnings(project) == [("G03", "cues[0].params.type_at_f", "holo_board.type_at_f" + END)]
    _cue(project, "holo_board", {**holo, "type_at_f": 80}, length=45)
    assert [p for _, p, _ in _warnings(project)] == ["cues[0].params.type_at_f"]
    _cue(project, "holo_board", {**holo, "type_at_f": 44}, length=45)
    assert _warnings(project) == []


def test_showpiece_time_warnings_sticker_fly_to_at_or_after_the_end(project: Project) -> None:
    _cue(project, "sticker", _sticker(LENGTH))
    assert _warnings(project) == [
        ("G03", "cues[0].params.fly_to.at_f", "sticker.fly_to.at_f" + END)
    ]
    _cue(project, "sticker", _sticker(LENGTH + 10))
    assert [text for _, _, text in _warnings(project)] == ["sticker.fly_to.at_f" + END]


@pytest.mark.parametrize(
    ("at_f", "warns"),
    [(LENGTH - 1, True), (LENGTH - 2, True), (LENGTH - 3, True), (LENGTH - 4, False), (10, False)],
)
def test_showpiece_time_warnings_sticker_flight_shorter_than_012_s(
    project: Project, at_f: int, warns: bool
) -> None:
    """At 30 fps 0.12 s is 3.6 frames: a flight that starts 3 frames before the end (0.1 s) is
    short, and one that starts 4 frames before (0.133 s) is not."""
    _cue(project, "sticker", _sticker(at_f))
    expected = [("G03", "cues[0].params.fly_to.at_f", SHORT_FLIGHT)] if warns else []
    assert _warnings(project) == expected


def test_showpiece_time_warnings_a_time_past_the_end_is_one_warning_not_two(
    project: Project,
) -> None:
    _cue(project, "sticker", _sticker(LENGTH))
    assert [text for _, _, text in _warnings(project)] == ["sticker.fly_to.at_f" + END]


def test_showpiece_time_warnings_the_cue_is_still_drawn(project: Project) -> None:
    """A warning is not an error: the cue is in the result, and `exit_code` is 0."""
    _cue(project, "steps", _steps(0, LENGTH + 4))
    resolved = run_resolve(project)
    assert [c.id for c in resolved.cues] == ["uno"]
    assert [i.level for i in resolved.issues] == ["warning"]
    assert exit_code(resolved.issues) == 0


def test_showpiece_time_warnings_a_cue_with_an_error_has_only_the_error(project: Project) -> None:
    params = _steps(0, LENGTH + 4)
    params["items"][1]["label"] = "x" * 40  # a G03 error: `label` is at most 12 characters
    _cue(project, "steps", params)
    resolved = run_resolve(project)
    assert [(i.code, i.level) for i in resolved.issues] == [("G03", "error")]


def test_showpiece_time_warnings_other_components_have_none(project: Project) -> None:
    title = {"text": "Hola", "bar": True}
    _cue(project, "title", title)
    assert _warnings(project) == []
    _cue(project, "globe", {})
    assert _warnings(project) == []


def test_showpiece_time_warnings_the_messages_are_fixed_text_with_the_issue_path(
    project: Project,
) -> None:
    _cue(project, "steps", _steps(0, LENGTH))
    (found,) = [i for i in run_resolve(project).issues if i.level == "warning"]
    assert isinstance(found, Issue) and found.code == "G03" and found.level == "warning"
    assert "paso 1" not in found.message_es  # the text of the step is not repeated
