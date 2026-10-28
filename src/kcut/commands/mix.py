"""kcut mix: the audio of the cut, mixed to the level of the delivery (spec S1.8b).

Order: the lock of the output (`build-vN`, shared with `render`; the gate of the strategy is not
asked), the check of the EDL (exit 1), the words the cut keeps, `edit/sfx.json` (`parse_sfx` and
`resolve_events`, codes A) and `edit/music.json` (`parse_music`, codes M); with an error in any of
them it stops before anything is made, with the exit of `exit_code` (1, or 5 for an M04). Without
those files there are no effects and no music. Then `mixer.mix` writes `.kcut/build/vN/mix.wav` and
the loudness of the voice and of the mix is measured with `ebur128`. It does not touch the video.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from kcut import proc
from kcut.audio.loudnorm import EburMeasure, audio_timeout_s, ebur128_args, parse_ebur128
from kcut.audio.mixer import STEPS, AudioPlan, mix
from kcut.audio.music_model import NO_MUSIC
from kcut.audio.music_schema import parse_music
from kcut.audio.sfx_events import resolve_events
from kcut.audio.sfx_schema import parse_sfx
from kcut.audio.voice_track import require_mix_space
from kcut.commands.listing import findings_json, list_findings
from kcut.commands.refuse import refuse_edl
from kcut.console import Out, Progress
from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.edl.kept import KeptWords, kept_words
from kcut.edl.model import Edl
from kcut.ingest.cache_guard import assert_in_cache, build_folder
from kcut.ingest.inventory import Notice
from kcut.ingest.partials import sweep_orphan_partials
from kcut.issues import Issue, exit_code, issue_json
from kcut.jsonio import MAX_MUSIC_BYTES, MAX_SFX_BYTES, read_json
from kcut.logfile import append_log
from kcut.paths import resolve_in_project, to_rel
from kcut.project import Project, load_inventory, open_project
from kcut.render.lock import OutputLock
from kcut.timebase import SAMPLE_RATE
from kcut.timebase import spf as samples_per_frame

NAME = "mix"
HELP_ES = "Mezcla la voz, los efectos y la música del corte a un nivel de entrega (mix.wav)"
SFX_REL = "edit/sfx.json"
MUSIC_REL = "edit/music.json"
_F32 = ["-f", "f32le", "-ar", "48000", "-ac", "1"]


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument(
        "--edl",
        metavar="EDL",
        default=None,
        help="ruta del EDL, relativa al proyecto (por defecto el edit/edl-vN.json de N más alto)",
    )
    return sub


def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    log = getattr(args, "log", None)
    inventory = load_inventory(project, log)
    rel, version = find_edl(project, args.edl)
    lock_name = f"build-v{version}"
    assert_in_cache(project, project.layout.locks / f"{lock_name}.lock")
    notices: list[Notice] = []
    with OutputLock(project.layout.locks, lock_name):
        checked = check_edl_file(project, inventory, rel)
        errors = [issue for issue in checked.issues if issue.level == "error"]
        if errors or checked.edl is None:
            refuse_edl(out, rel, errors)
        edl = checked.edl
        kept = kept_words(project, edl, inventory, notices=notices, log=log)
        plan, issues = _plan(project, edl, kept)
        if any(issue.level == "error" for issue in issues):
            _warn_notices(out, notices)  # 001.37, point 12: before it stops, not lost
            return _refused(out, issues)
        folder = build_folder(project, version)
        folder.mkdir(parents=True, exist_ok=True)
        swept = sweep_orphan_partials(project)  # what a mix killed by force left (001.37, point 11)
        if swept and log is not None:
            append_log(log, f"[orphan_partials] {swept} archivos parciales huérfanos borrados\n")
        require_mix_space(folder, edl)  # a full disk is told now, not after minutes (001.37, 4)
        progress = Progress(f"mix v{version}", STEPS, "pasos")
        wav = mix(
            project, edl, version, progress,
            plan=plan, inventory=inventory, log=log, issues=issues, notices=notices,
        )  # fmt: skip
        progress.close()
        samples = edl.frames * samples_per_frame(edl.fps)
        timeout = audio_timeout_s(samples / SAMPLE_RATE)  # as `normalize` (001.37, point 3)
        voice = _measure(folder / "voice.f32", True, log, timeout)
        mixed = _measure(wav, False, log, timeout)
    _warn_notices(out, notices)
    errors, warnings = _split(issues)
    elapsed = round(time.monotonic() - started, 1)
    where = to_rel(project.root, wav)
    out.line("OK", f"{where}: {samples} muestras, {_text(mixed.I)} LUFS en {elapsed} s")
    list_findings(out, "AVISO", warnings)
    out.result(
        {
            "ok": True,
            "mix": where,
            "samples": samples,
            "voice_lufs": _round(voice.I),
            "mix_I": _round(mixed.I),
            "mix_TP": _round(mixed.TP),
            "sfx_events": len(plan.events),
            "music": plan.music.mode,
            **findings_json([issue_json(i) for i in errors], [issue_json(i) for i in warnings]),
        }
    )
    return 0


def _plan(project: Project, edl: Edl, kept: KeptWords) -> tuple[AudioPlan, list[Issue]]:
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


def _read_optional(project: Project, rel: str, cap: int) -> tuple[object] | None:
    """The JSON of `rel` (as the only item of a tuple, since the JSON may be `null`), or `None` if
    the file is not there. One that is there and cannot be read (size over `cap`, not JSON) is a
    ProjectError, exit 3."""
    path = resolve_in_project(project.root, rel)
    if not os.path.lexists(path):
        return None
    return (read_json(path, cap),)


def _measure(source: Path, raw: bool, log: Path | None, timeout: float) -> EburMeasure:
    """`I`, `TP` and `LRA` of `source` (raw float32 if `raw`, a wav otherwise) with `ebur128`, in
    `timeout` seconds at most: a hung `ffmpeg` would keep the lock of the output taken (001.37)."""
    inputs = [*(_F32 if raw else []), "-i", str(source)]
    args = ebur128_args(proc.tool_path("ffmpeg"), inputs)
    result = proc.run(args, log=log, timeout_s=timeout, capture_stderr=True)
    return parse_ebur128(result.stderr)


def _warn_notices(out: Out, notices: list[Notice]) -> None:
    """The warnings of the run, on stderr, except `pii_unmasked` (001.37, point 12): it warns that
    the texts Claude reads are not masked, and `kcut mix` shows no text."""
    for notice in notices:
        if notice.code != "pii_unmasked":
            out.warn(f"{notice.code}: {notice.detail}")


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _text(value: float | None) -> str:
    return "sin dato" if value is None else f"{value:.1f}"


def _split(issues: list[Issue]) -> tuple[list[Issue], list[Issue]]:
    return (
        [issue for issue in issues if issue.level == "error"],
        [issue for issue in issues if issue.level == "warning"],
    )


def _refused(out: Out, issues: list[Issue]) -> int:
    """`sfx.json` or `music.json` has errors: they are the answer, and nothing is mixed."""
    errors, warnings = _split(issues)
    out.line("ERROR", f"hay {len(errors)} errores en edit/sfx.json o edit/music.json")
    list_findings(out, "ERROR", errors)
    list_findings(out, "AVISO", warnings)
    out.result(
        {
            "ok": False,
            "mix": None,
            "samples": None,
            "voice_lufs": None,
            "mix_I": None,
            "mix_TP": None,
            "sfx_events": None,
            "music": None,
            **findings_json([issue_json(i) for i in errors], [issue_json(i) for i in warnings]),
        }
    )
    return exit_code(issues)
