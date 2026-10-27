"""`kcut graphics check` as a command (spec S1.6a): what it prints for a person and how it refuses.

The JSON of the command and its exit codes are in `test_graphics_check.py`.
"""

from pathlib import Path

import pytest

from tests.conftest import run_kcut
from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import graphics_v1_document, write_graphics_v1
from tests.integration.graphics_helpers import plant_words
from tests.integration.test_graphics_check import _write
from tests.integration.view_frames_helpers import Run, project_args

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]


@pytest.fixture
def cut(view_fresh: Path) -> Path:
    """A copy of the synthetic project with the example EDL and the transcript of a1 planted."""
    write_edl_v1(view_fresh)
    plant_words(view_fresh)
    return view_fresh


class TestCommandLine:
    """The shape of the command: what it prints for a person, and how it refuses."""

    def test_graphics_check_human_output_is_tagged_lines(self, cut: Path) -> None:
        write_graphics_v1(cut, False)
        done = run_kcut("graphics", "check", "--project", str(cut))
        assert done.returncode == 0, done.stderr
        assert done.stdout.startswith("[OK] edit/edl-v1.json: 4 cues, ")
        assert "0 errores, 0 avisos" in done.stdout and "\x1b" not in done.stdout

    def test_graphics_check_human_output_names_a_warning_with_its_code(self, cut: Path) -> None:
        done = run_kcut("graphics", "check", "--project", str(cut))
        assert done.returncode == 0, done.stderr
        assert "[AVISO] G11: no hay edit/graphics.json: subtítulos por defecto" in done.stdout

    def test_graphics_check_human_output_of_an_error_is_exit_1_with_the_code_and_the_path(
        self, cut: Path
    ) -> None:
        document = graphics_v1_document()
        document["cues"][0]["end"] = 999
        _write(cut, document)
        done = run_kcut("graphics", "check", "--project", str(cut))
        assert done.returncode == 1
        assert "[ERROR] G07 cues[0]: " in done.stdout

    def test_graphics_check_without_an_action_is_exit_2(self, kcut_json: Run) -> None:
        assert kcut_json("graphics")[0] == 2

    def test_graphics_check_an_edl_that_is_not_there_is_exit_3(
        self, cut: Path, kcut_json: Run
    ) -> None:
        code, doc, _ = kcut_json(
            "graphics", "check", "--edl", "edit/edl-v9.json", *project_args(cut)
        )
        assert code == 3 and doc["error"]["kind"] == "ProjectError"
