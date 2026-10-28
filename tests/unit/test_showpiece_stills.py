"""The refusals and the frames of `tests/fixtures/showpiece_stills.py` (spec S1.7 row 6). The stills
themselves are made by the command of the row, which needs ffmpeg and Chromium."""

from pathlib import Path

import pytest

from tests.fixtures import showpiece_stills


def test_showpiece_stills_the_frames_are_the_middle_of_each_cue() -> None:
    # pasos 210-270, mascota 180-210, holo 270-315, mundo 280-315: start + (end - start) // 2
    assert showpiece_stills.middle_frames() == [240, 195, 292, 297]


def test_showpiece_stills_no_folder_or_two_is_a_usage_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert showpiece_stills.main(["prog"]) == 2
    assert showpiece_stills.main(["prog", "a", "b"]) == 2
    assert "uso:" in capsys.readouterr().err


def test_showpiece_stills_a_project_is_refused_with_3_and_left_as_it_is(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "kcut.toml").write_text("x = 1\n", encoding="utf-8")
    assert showpiece_stills.main(["prog", str(tmp_path)]) == 3
    assert "ya es un proyecto" in capsys.readouterr().err
    assert [p.name for p in tmp_path.iterdir()] == ["kcut.toml"]


def test_showpiece_stills_a_folder_with_something_in_it_is_refused_with_3(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "notas.txt").write_text("mias\n", encoding="utf-8")
    assert showpiece_stills.main(["prog", str(tmp_path)]) == 3
    assert "no está vacía" in capsys.readouterr().err
    assert [p.name for p in tmp_path.iterdir()] == ["notas.txt"]


def test_showpiece_stills_a_file_in_place_of_the_folder_is_refused_with_3(
    tmp_path: Path,
) -> None:
    target = tmp_path / "es-un-archivo"
    target.write_text("x\n", encoding="utf-8")
    assert showpiece_stills.main(["prog", str(target)]) == 3
    assert target.read_text(encoding="utf-8") == "x\n"
