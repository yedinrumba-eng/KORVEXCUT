"""The audio steps that `kcut mix` and `kcut build` share (spec S1.8b, S1.9b; 001.51 point 6):
`sfx.json` and `music.json` read and checked before anything is made, and the mix written to
`.kcut/build/vN/mix.wav`.

A file that is not there is nothing to check (no effects, no music); one that is there and has
errors stops `build` with their exit code (`exit_code`: 1, or 5 for an M04), after printing the
first ones, and is the answer of `mix`. They live here, and not in `commands/`, because a module
outside `commands/` cannot import a command (`tests/unit/test_layers.py`).
"""

import os
from pathlib import Path

from kcut.audio.mixer import STEPS as MIX_STEPS
from kcut.audio.mixer import AudioPlan, mix
from kcut.audio.music_model import NO_MUSIC
from kcut.audio.music_schema import parse_music
from kcut.audio.sfx_events import resolve_events
from kcut.audio.sfx_schema import parse_sfx
from kcut.console import Out, Progress
from kcut.edl.kept import KeptWords, kept_words
from kcut.edl.model import Edl
from kcut.edl.refuse import MAX_NAMED
from kcut.errors import CheckFailed, GateError
from kcut.gfx.layer import GATE_EXIT
from kcut.ingest.inventory import Inventory, Notice
from kcut.issues import Issue, exit_code
from kcut.jsonio import MAX_MUSIC_BYTES, MAX_SFX_BYTES, read_json
from kcut.paths import resolve_in_project
from kcut.project import Project

SFX_REL = "edit/sfx.json"
MUSIC_REL = "edit/music.json"


def audio_plan(
    out: Out,
    project: Project,
    edl: Edl,
    inventory: Inventory,
    notices: list[Notice],
    log: Path | None,
) -> tuple[AudioPlan, list[Issue]]:
    """What `sfx.json` and `music.json` say, resolved against the EDL, and their findings. With an
    error in any of them: the first ones are printed and the exit is 1 (5 with an M04)."""
    kept = kept_words(project, edl, inventory, notices=notices, log=log)
    plan, issues = read_plan(project, edl, kept)
    _raise_for_errors(out, issues)
    return plan, issues


def read_plan(project: Project, edl: Edl, kept: KeptWords) -> tuple[AudioPlan, list[Issue]]:
    """`sfx.json` and `music.json` read, checked against the EDL and resolved, and the issues of
    both (A01-A08, M01-M05). A file that is not there is nothing to check: no effects, no music."""
    issues: list[Issue] = []
    plan = AudioPlan()
    sfx = _read_optional(project, SFX_REL, MAX_SFX_BYTES)
    if sfx is not None:
        doc, found = parse_sfx(sfx[0])
        issues += found
        if doc is not None:
            events, found = resolve_events(doc, kept.words, edl, edl.fps)
            issues += found
            windows = tuple((w.start, w.end, w.gain_db) for w in doc.windows)
            plan = AudioPlan(tuple(events), doc.bus_gain_db, windows, NO_MUSIC)
    music = _read_optional(project, MUSIC_REL, MAX_MUSIC_BYTES)
    if music is not None:
        music_doc, found = parse_music(music[0], project, edl.frames)
        issues += found
        if music_doc is not None:
            plan = AudioPlan(plan.events, plan.bus_gain_db, plan.sfx_windows, music_doc)
    return plan, issues


def make_mix(
    project: Project,
    edl: Edl,
    version: int,
    plan: AudioPlan,
    issues: list[Issue],
    inventory: Inventory,
    notices: list[Notice],
    log: Path | None,
) -> Path:
    """`.kcut/build/vN/mix.wav`, with its own progress line (the lock is the caller's)."""
    progress = Progress(f"mix v{version}", MIX_STEPS, "pasos")
    wav = mix(
        project, edl, version, progress,
        plan=plan, inventory=inventory, log=log, issues=issues, notices=notices,
    )  # fmt: skip
    progress.close()
    return wav


def _read_optional(project: Project, rel: str, cap: int) -> tuple[object] | None:
    """The JSON of `rel` (the only item of a tuple, since the JSON may be `null`), or `None` if
    the file is not there. One that is there and cannot be read is a ProjectError, exit 3."""
    path = resolve_in_project(project.root, rel)
    if not os.path.lexists(path):
        return None
    return (read_json(path, cap),)


def _raise_for_errors(out: Out, issues: list[Issue]) -> None:
    errors = [issue for issue in issues if issue.level == "error"]
    if not errors:
        return
    for issue in errors[:MAX_NAMED]:
        out.line("ERROR", f"{issue.code} {issue.path}: {issue.message_es}")
    named = ", ".join(sorted({issue.code for issue in errors}))
    message = (
        f"hay {len(errors)} errores en edit/sfx.json o edit/music.json ({named}); "
        "corre kcut mix y corrígelos"
    )
    if exit_code(errors) == GATE_EXIT:
        raise GateError(message)
    raise CheckFailed(message)
