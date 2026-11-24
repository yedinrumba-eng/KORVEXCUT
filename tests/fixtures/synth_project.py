"""The whole synthetic project, ready for `kcut build` (spec S1.9b).

    .venv/Scripts/python.exe -X utf8 -m tests.fixtures.synth_project "<folder>"

(without `-I`, so that `-m` finds `tests`). `<folder>` must not exist or must be empty, and it must
be outside the repo of kcut (DS14: `kcut new` refuses to make a project there). It makes the
project there (`make_project`) and prints its path: then `kcut build --project "<folder>"` builds
`salida/v1.mp4`, and `kcut storyboard` and the like can be looked at by a person. Exit 0, or: 2 with
the wrong arguments, 3 if `<folder>` is a project already, has something in it or is inside the
repo, and the exit code of the `kcut` command that failed otherwise.

`make_project(root)` is `kcut new`, `make_media`, `kcut ingest`, `kcut transcribe` (if the model of
Whisper is on the machine: without it the project has no transcript and says so in its truth), the
example EDL, `write_graphics_v1(with_showpieces=True)` and the plans of audio; and
`min_transcript_match = 0.5` in its `kcut.toml`, because the speech of the cameras is synthetic.
`finish_project(root, media)` is what comes after `kcut ingest`, for a project that already went
through it (the session fixture `synth_project`, copied).
"""

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.fixtures.synth_audio import write_audio_plans
from tests.fixtures.synth_edl import EdlTruth, write_edl_v1
from tests.fixtures.synth_graphics import write_graphics_v1
from tests.fixtures.synth_media import MediaTruth, make_media

MODEL_MISSING_EXIT = 7  # `MissingDependency`: `kcut transcribe` does not download the model
MIN_MATCH = ("min_transcript_match = 0.80", "min_transcript_match = 0.5")


@dataclass(frozen=True)
class ProjectTruth:
    """What the synthetic project is: its media, its EDL and whether it has a transcript."""

    media: MediaTruth
    edl: EdlTruth
    transcribed: bool


def _kcut(*args: str) -> subprocess.CompletedProcess[str]:
    """`python -m kcut <args>` in an isolated interpreter, as the tests run it."""
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-m", "kcut", *args],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def _require(step: str, done: subprocess.CompletedProcess[str]) -> None:
    assert done.returncode == 0, f"{step} salió {done.returncode}: {done.stderr or done.stdout}"


def make_project(root: Path) -> ProjectTruth:
    """The synthetic project in `root` (a folder that does not exist yet), ready to build."""
    _require("kcut new", _kcut("new", str(root)))
    media = make_media(root / "crudo")
    _require("kcut ingest", _kcut("ingest", "--project", str(root), "--json"))
    return finish_project(root, media)


def finish_project(root: Path, media: MediaTruth) -> ProjectTruth:
    """Everything after `kcut ingest`: the transcript (if there is a model), the EDL, the graphics
    with the showpieces, the plans of audio and the threshold of the QA of the synthetic voice."""
    done = _kcut("transcribe", "--project", str(root), "--json")
    if done.returncode != MODEL_MISSING_EXIT:
        _require("kcut transcribe", done)
    edl = write_edl_v1(root)
    write_graphics_v1(root, with_showpieces=True)
    write_audio_plans(root)
    config = root / "kcut.toml"
    text = config.read_text(encoding="utf-8")
    assert MIN_MATCH[0] in text, "la plantilla de kcut.toml ya no trae min_transcript_match = 0.80"
    config.write_text(text.replace(*MIN_MATCH), encoding="utf-8", newline="\n")
    return ProjectTruth(media, edl, transcribed=done.returncode == 0)


def _refusal(root: Path) -> str | None:
    """Why `root` cannot be used, or `None`: it must be a folder that does not exist or is empty."""
    if (root / "kcut.toml").exists():
        return f"{root} ya es un proyecto de kcut: usa una carpeta nueva o vacía"
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        return f"{root} no está vacía: usa una carpeta nueva o vacía"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('uso: python -X utf8 -m tests.fixtures.synth_project "<carpeta>"', file=sys.stderr)
        return 2
    root = Path(argv[1]).resolve()
    refusal = _refusal(root)
    if refusal is not None:
        print(f"synth_project: {refusal}", file=sys.stderr)
        return 3
    try:
        truth = make_project(root)
    except AssertionError as exc:
        print(f"synth_project: {exc}", file=sys.stderr)
        return 1
    print(root)
    if not truth.transcribed:
        print(
            "synth_project: sin modelo de Whisper: el proyecto no tiene transcripción",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
