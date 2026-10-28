"""Four stills of the showpiece components, for a person to look at (spec S1.7 row 6, 001.15).

    .venv/Scripts/python.exe -X utf8 -m tests.fixtures.showpiece_stills "<folder>"

(without `-I`, as `synth_project`: so that `-m` finds `tests`). `<folder>` must not exist or must be
empty, and it must be outside the repo of kcut (DS14: `kcut new` refuses to make a project there).
It builds the synthetic project there (`kcut new`, `make_media`, `kcut ingest`, the example EDL and
`write_graphics_v1(with_showpieces=True)`) and runs `kcut graphics still`, composited over the
picture (no `--alpha`), at the middle frame of `pasos`, `mascota`, `holo` and `mundo`
(`start + (end - start) // 2`), with `--out qa/showpieces`. It prints the four paths, one per line.

The subtitles are off in the `graphics.json` that it writes: nobody has run `kcut transcribe` on the
synthetic project, and the stills are of the components. Exit 0, or: 2 with the wrong arguments, 3
if `<folder>` is a project already, has something in it or is inside the repo, and the exit code
of the `kcut` command that failed otherwise.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.fixtures.synth_edl import write_edl_v1
from tests.fixtures.synth_graphics import showpiece_cues, write_graphics_v1
from tests.fixtures.synth_media import make_media

OUT = "qa/showpieces"
SHOWPIECES = ("pasos", "mascota", "holo", "mundo")


def middle_frames() -> list[int]:
    """The middle frame of each showpiece cue, in the order of `SHOWPIECES`."""
    by_id = {cue["id"]: cue for cue in showpiece_cues()}
    return [by_id[i]["start"] + (by_id[i]["end"] - by_id[i]["start"]) // 2 for i in SHOWPIECES]


def _kcut(*args: str) -> subprocess.CompletedProcess[str]:
    """`python -m kcut <args>` in an isolated interpreter, as the tests run it."""
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-m", "kcut", *args],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )


def _refusal(root: Path) -> str | None:
    """Why `root` cannot be used, or `None`: it must be a folder that does not exist or is empty."""
    if (root / "kcut.toml").exists():
        return f"{root} ya es un proyecto de kcut: usa una carpeta nueva o vacía"
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        return f"{root} no está vacía: usa una carpeta nueva o vacía"
    return None


def _fail(step: str, done: subprocess.CompletedProcess[str]) -> int:
    print(f"showpiece_stills: falló {step} (salida {done.returncode})", file=sys.stderr)
    print((done.stderr or done.stdout).strip(), file=sys.stderr)
    return done.returncode or 1


def _subtitles_off(root: Path) -> None:
    """The graphics of the project with `captions.enabled = false` (see the docstring)."""
    path = root / "edit" / "graphics.json"
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    document["captions"] = {"enabled": False}
    text = json.dumps(document, ensure_ascii=False, indent=1) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print('uso: python -X utf8 -m tests.fixtures.showpiece_stills "<carpeta>"', file=sys.stderr)
        return 2
    root = Path(argv[1]).resolve()
    refusal = _refusal(root)
    if refusal is not None:
        print(f"showpiece_stills: {refusal}", file=sys.stderr)
        return 3
    created = _kcut("new", str(root))
    if created.returncode != 0:
        return _fail("kcut new", created)
    make_media(root / "crudo")
    ingested = _kcut("ingest", "--project", str(root))
    if ingested.returncode != 0:
        return _fail("kcut ingest", ingested)
    write_edl_v1(root)
    write_graphics_v1(root, with_showpieces=True)
    _subtitles_off(root)
    frames = [str(f) for f in middle_frames()]
    shot = _kcut("graphics", "still", *frames, "--out", OUT, "--project", str(root), "--json")
    if shot.returncode != 0:
        return _fail("kcut graphics still", shot)
    stills = json.loads(shot.stdout)["stills"]
    if len(stills) != len(SHOWPIECES):
        print(f"showpiece_stills: se esperaban {len(SHOWPIECES)} stills", file=sys.stderr)
        return 1
    for still in stills:
        print((root / still["png"]).resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
