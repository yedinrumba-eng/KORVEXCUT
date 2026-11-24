"""`kcut build`, in order (spec S1.9b): the video of the cut, finished, in `salida/vN.mp4`.

The lock `build-vN`; `salida/vN.mp4` that is already there and no `--force` (exit 3); the gate of
the strategy (exit 5); the check of the EDL (exit 1); the manifest of resources (exit 1); the
graphics, `sfx.json` and `music.json`, whose errors stop everything before anything is made (exit 1,
5 for a G10 or an M04); the picture with the graphics over it; the mix; the mux of the two into
`salida/vN.partial.mp4`, moved over `salida/vN.mp4`; the snapshot of the inputs in `qa/vN/inputs/`;
and `kcut qa` unless `--skip-qa`. The lock is taken here and not again by what is called from here.

So, with `salida/vN.mp4` there, no `--force` and no approval, the exit is 3 and not 5 (001.15).
`salida/vN.mp4` and its partial pass through `assert_writable` (T4) before the work starts and again
right before each is written: a symlink there, to a file of `crudo/`, is exit 3 and the file stays.
What `qa/vN/` is going to lose and receive (`stale_rels`) is looked at in the same place, a folder
where a file of `.kcut/build/vN/` goes is exit 3 before the mezzanines (`build_destinations`), and
the disk is asked once for everything (`require_build_space`) (001.52).
The time of each step goes in the result and in the log.
"""

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from kcut.audio.voice_track import require_build_space
from kcut.console import Out, Progress
from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.edl.gate import strategy_approved
from kcut.edl.refuse import MAX_NAMED, refuse_edl
from kcut.errors import CheckFailed, GateError, ProjectError
from kcut.findings import finding_lines
from kcut.gfx.layer import layer_bytes
from kcut.ingest.cache_guard import assert_in_cache, build_folder
from kcut.ingest.inventory import Notice
from kcut.ingest.partials import sweep_orphan_partials
from kcut.issues import Issue
from kcut.jsonio import refuse_directory
from kcut.logfile import append_log
from kcut.paths import to_rel
from kcut.pipeline.audio import audio_plan, make_mix
from kcut.pipeline.destinations import build_destinations
from kcut.pipeline.picture import make_video, mux_replace, resolve_graphics
from kcut.pipeline.snapshot import (
    clear_stale,
    confirm_inputs,
    read_inputs,
    snapshot_inputs,
    stale_rels,
)
from kcut.project import Project, assert_writable, load_inventory
from kcut.qa.report import QaReport
from kcut.qa.run import STEPS as QA_STEPS
from kcut.qa.run import run_qa
from kcut.recursos.manifest import validate_manifest
from kcut.render.lock import OutputLock

STEPS = 6  # what `progress` counts: checks, picture, mix, mux, snapshot, qa


@dataclass(frozen=True)
class BuildResult:
    """What a build made: `video` (`salida/vN.mp4`), its `frames`, the snapshot `inputs`
    (`qa/vN/inputs/inputs.json`), the `report` of `kcut qa` (`None` with `--skip-qa`), the seconds
    of each step and the warnings of the run (`code: detail`)."""

    version: int
    video: str
    frames: int
    inputs: str
    report: QaReport | None
    timings_s: dict[str, float]
    warnings: tuple[str, ...]


def run_build(
    project: Project,
    edl_rel: str | None,
    *,
    skip_qa: bool,
    force: bool,
    progress: Progress,
    out: Out,
    log: Path | None = None,
) -> BuildResult:
    """Build the video of `edl_rel` (`None`: the `edit/edl-vN.json` of the highest N)."""
    inventory = load_inventory(project, log)
    rel, version = find_edl(project, edl_rel)
    lock_name = f"build-v{version}"
    assert_in_cache(project, project.layout.locks / f"{lock_name}.lock")
    video_rel, partial_rel = f"salida/v{version}.mp4", f"salida/v{version}.partial.mp4"
    notices: list[Notice] = []
    timings: dict[str, float] = {}
    with OutputLock(project.layout.locks, lock_name):
        first = read_inputs(project, version, rel)  # 001.51: what is built is what is kept
        if os.path.lexists(project.root / video_rel) and not force:
            raise ProjectError(f"{video_rel} ya existe; usa --force para reemplazarlo")
        gate = strategy_approved(project)
        if not gate.approved:
            raise GateError(f"{gate.reason_es}; apruébala antes de construir")
        # before the work, and again before each write; 001.52: also what `qa/vN/` is going to
        # lose and receive (the same list as `clear_stale`), so a link there is told now
        for target in (video_rel, partial_rel, *stale_rels(version, rel)):
            assert_writable(project, target)
        checked = check_edl_file(project, inventory, rel)
        errors = [issue for issue in checked.issues if issue.level == "error"]
        if errors or checked.edl is None:
            refuse_edl(out, rel, errors)
        edl = checked.edl
        _check_manifest(out, project)
        resolved = resolve_graphics(out, project, edl, version, inventory, log)
        plan, issues = audio_plan(out, project, edl, inventory, notices, log)
        folder = build_folder(project, version)
        folder.mkdir(parents=True, exist_ok=True)
        for name in build_destinations():  # a folder there is told now, not after the mezzanines
            refuse_directory(folder / name)
        swept = sweep_orphan_partials(project)  # what a build killed by force left
        if swept and log is not None:
            append_log(log, f"[orphan_partials] {swept} archivos parciales huérfanos borrados\n")
        # a full disk is told now, not after minutes: once, for everything (001.52)
        need = layer_bytes(project, resolved, folder, force=False)
        require_build_space(folder, edl, layer_bytes=need)
        progress.update(1)

        mark = time.monotonic()
        _, frames, _ = make_video(project, edl, version, resolved, inventory, notices, log)
        _step(timings, "picture", mark, log)
        progress.update(2)
        mark = time.monotonic()
        wav = make_mix(project, edl, version, plan, issues, inventory, notices, log)
        _step(timings, "mix", mark, log)
        progress.update(3)
        mark = time.monotonic()

        def before_replace() -> None:  # after the ffmpeg of the mux, right before the video moves
            confirm_inputs(project, first, version, rel)
            clear_stale(project, version, rel)

        _mux(
            project, folder / "video.mp4", wav, (video_rel, partial_rel), version, log,
            before_replace,
        )  # fmt: skip
        _step(timings, "mux", mark, log)
        progress.update(4)
        mark = time.monotonic()
        inputs = snapshot_inputs(project, version, edl_rel=rel, read=first)
        _step(timings, "snapshot", mark, log)
        progress.update(5)
        report = None
        if not skip_qa:
            mark = time.monotonic()
            qa_progress = Progress(f"qa {video_rel}", QA_STEPS, "pasos")
            report = run_qa(project, video_rel, None, qa_progress, out=out, log=log)
            qa_progress.close()
            _step(timings, "qa", mark, log)
        progress.update(6)
    return BuildResult(
        version=version,
        video=video_rel,
        frames=frames,
        inputs=to_rel(project.root, inputs),
        report=report,
        timings_s={name: round(seconds, 1) for name, seconds in timings.items()},
        warnings=_warnings(notices, issues),
    )


def _check_manifest(out: Out, project: Project) -> None:
    """The manifest of resources, valid (exit 1 with the first problems printed)."""
    problems = validate_manifest(project)
    if not problems:
        return
    for problem in problems[:MAX_NAMED]:
        out.line("ERROR", problem)
    raise CheckFailed(
        f"recursos/recursos.json tiene {len(problems)} problemas; corrígelos antes de construir"
    )


def _mux(
    project: Project,
    video: Path,
    wav: Path,
    names: tuple[str, str],
    version: int,
    log: Path | None,
    before_replace: Callable[[], None],
) -> None:
    """The picture copied and the mix as AAC 192k stereo, to `salida/vN.partial.mp4`, moved over
    `salida/vN.mp4`. Both names are looked at again right before the move and the delete.
    `before_replace` runs after the ffmpeg and before the move: if it raises the partial goes."""
    video_rel, partial_rel = names
    final = assert_writable(project, video_rel)
    partial = assert_writable(project, partial_rel)
    partial.parent.mkdir(parents=True, exist_ok=True)

    def look() -> None:
        build_folder(project, version)
        assert_in_cache(project, video)
        assert_in_cache(project, wav)
        assert_writable(project, partial_rel)
        assert_writable(project, video_rel)

    mux_replace(
        video,
        wav,
        partial,
        final,
        audio_f32=False,
        look=look,
        log=log,
        before_replace=before_replace,
    )


def _step(timings: dict[str, float], name: str, mark: float, log: Path | None) -> None:
    """Record the seconds of a step, and put them in the log."""
    timings[name] = time.monotonic() - mark
    if log is not None:
        append_log(log, f"[build] {name}: {timings[name]:.1f} s\n")


def _warnings(notices: list[Notice], issues: list[Issue]) -> tuple[str, ...]:
    """The notices of the run as `code: detail`, without repeats, and then the warnings of
    `sfx.json` and `music.json` (A06, A08, M06...) as `kcut mix` lists them (`finding_lines`:
    `<code> <path>: <message>`, at most `MAX_SHOWN` and `... y N más`). The findings are not merged:
    two `A08` of different events are two lines (001.52)."""
    found = list(dict.fromkeys(f"{n.code}: {n.detail}" for n in notices))
    found += finding_lines([issue for issue in issues if issue.level == "warning"])
    return tuple(found)
