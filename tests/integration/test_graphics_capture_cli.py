"""`kcut graphics capture` and `still` as commands (spec S1.6b): what they print for a person, how
the arguments are read and that the JSON is the one document. Each test runs `python -m kcut` in a
process of its own, on a copy of the small project (a 2 s EDL, 60 frames), with one label cue.
"""

import json
import shutil
from pathlib import Path

import pytest

from tests.conftest import run_kcut
from tests.integration.render_small_cases import small, small_base

pytestmark = [pytest.mark.ffmpeg, pytest.mark.chromium, pytest.mark.slow]
__all__ = ["small", "small_base"]
GRAPHICS = {
    "schema": "kcut.graphics/1",
    "captions": {"enabled": False},
    "cues": [
        {
            "id": "pill",
            "component": "label",
            "start": 10,
            "end": 40,
            "params": {"text": "hecho con kcut", "y": 0.58},
        }
    ],
}


@pytest.fixture
def root(small: Path) -> Path:
    (small / "edit" / "graphics.json").write_text(json.dumps(GRAPHICS), encoding="utf-8")
    return small


def test_graphics_capture_cli_the_human_output_says_what_was_made_and_then_that_it_was_there(
    root: Path,
) -> None:
    first = run_kcut("graphics", "capture", "--project", str(root))
    assert first.returncode == 0, first.stderr
    line = first.stdout.splitlines()[0]
    assert line.startswith("[OK] .kcut/build/v1/gfx/index.json: ") and line.endswith("capturados")
    assert "\x1b" not in first.stdout
    second = run_kcut("graphics", "capture", "--project", str(root))
    assert second.returncode == 0, second.stderr
    assert second.stdout.splitlines()[0].endswith("frames ya estaban en la caché")


def test_graphics_capture_cli_with_json_stdout_is_one_document_and_progress_goes_to_stderr(
    root: Path,
) -> None:
    done = run_kcut("graphics", "capture", "--json", "--project", str(root))
    assert done.returncode == 0, done.stderr
    doc = json.loads(done.stdout)  # one document, nothing else on stdout
    assert set(doc) == {"ok", "edl", "frames", "captured", "index", "warnings"}
    assert doc["ok"] is True and doc["edl"] == "edit/edl-v1.json" and doc["captured"] is True
    assert doc["index"] == ".kcut/build/v1/gfx/index.json" and doc["frames"] == 29
    assert doc["warnings"] == []


def test_graphics_capture_cli_nothing_to_draw_is_an_info_line(small: Path) -> None:
    toml = small / "kcut.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(
        text.replace("[captions]\nenabled = true", "[captions]\nenabled = false"),
        encoding="utf-8",
        newline="\n",
    )
    done = run_kcut("graphics", "capture", "--project", str(small))
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == (
        "[INFO] edit/edl-v1.json: no hay nada que dibujar; no se captura nada"
    )
    assert "G12" in done.stderr  # and the warning says why


def test_graphics_still_cli_the_human_output_is_one_ok_line_per_still(root: Path) -> None:
    done = run_kcut("graphics", "still", "20", "30", "--out", "qa/v", "--project", str(root))
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "[OK] qa/v/still_000020.png",
        "[OK] qa/v/still_000030.png",
    ]
    assert (root / "qa" / "v" / "still_000020.png").is_file()


def test_graphics_still_cli_the_default_folder_is_in_the_cache(root: Path) -> None:
    done = run_kcut("graphics", "still", "20", "--project", str(root))
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["[OK] .kcut/build/v1/gfx/stills/still_000020.png"]


def test_graphics_still_cli_a_second_run_replaces_the_files_without_force(root: Path) -> None:
    args = ("graphics", "still", "20", "--out", "qa/v", "--project", str(root))
    assert run_kcut(*args).returncode == 0
    before = (root / "qa" / "v" / "still_000020.png").stat().st_mtime_ns
    again = run_kcut(*args)
    assert again.returncode == 0, again.stderr
    assert (root / "qa" / "v" / "still_000020.png").stat().st_mtime_ns >= before


def test_graphics_cli_the_arguments_are_checked_as_usage(root: Path) -> None:
    assert run_kcut("graphics", "still", "--project", str(root)).returncode == 2  # no frame
    assert run_kcut("graphics", "still", "abc", "--project", str(root)).returncode == 2
    assert run_kcut("graphics", "still", "1.5", "--project", str(root)).returncode == 2
    assert run_kcut("graphics", "capture", "--bogus", "--project", str(root)).returncode == 2
    assert run_kcut("graphics", "nope", "--project", str(root)).returncode == 2


def test_graphics_cli_the_help_lists_the_three_actions() -> None:
    done = run_kcut("graphics", "--help")
    assert done.returncode == 0
    assert all(name in done.stdout for name in ("check", "capture", "still"))
    still = run_kcut("graphics", "still", "--help")
    assert "--alpha" in still.stdout and "--out" in still.stdout and "--edl" in still.stdout
    capture = run_kcut("graphics", "capture", "--help")
    assert "--force" in capture.stdout and "--edl" in capture.stdout


def test_graphics_capture_cli_an_edl_of_another_version_has_its_own_folder(root: Path) -> None:
    """`--edl edit/edl-v2.json` builds under `.kcut/build/v2/gfx/`, with its own lock."""
    shutil.copy2(root / "edit" / "edl-v1.json", root / "edit" / "edl-v2.json")
    path = root / "edit" / "edl-v2.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["version"] = 2
    path.write_text(json.dumps(document), encoding="utf-8")
    done = run_kcut("graphics", "capture", "--edl", "edit/edl-v2.json", "--project", str(root))
    assert done.returncode == 0, done.stderr
    assert (root / ".kcut" / "build" / "v2" / "gfx" / "index.json").is_file()
