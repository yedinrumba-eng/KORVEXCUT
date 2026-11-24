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
import time
from pathlib import Path

from kcut import proc
from kcut.audio.loudnorm import EburMeasure, audio_timeout_s, ebur128_args, parse_ebur128
from kcut.audio.voice_track import require_mix_space
from kcut.commands.listing import findings_json, list_findings
from kcut.console import Out
from kcut.edl.check import check_edl_file
from kcut.edl.files import find_edl
from kcut.edl.kept import kept_words
from kcut.edl.refuse import refuse_edl
from kcut.ingest.cache_guard import assert_in_cache, build_folder
from kcut.ingest.inventory import Notice
from kcut.ingest.partials import sweep_orphan_partials
from kcut.issues import Issue, exit_code, issue_json
from kcut.logfile import append_log
from kcut.paths import to_rel
from kcut.pipeline.audio import make_mix, read_plan  # 001.51: shared with `build`
from kcut.project import load_inventory, open_project
from kcut.render.lock import OutputLock
from kcut.timebase import SAMPLE_RATE
from kcut.timebase import spf as samples_per_frame

NAME = "mix"
HELP_ES = "Mezcla la voz, los efectos y la música del corte a un nivel de entrega (mix.wav)"
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
        plan, issues = read_plan(project, edl, kept)
        if any(issue.level == "error" for issue in issues):
            _warn_notices(out, notices)  # 001.37, point 12: before it stops, not lost
            return _refused(out, issues)
        folder = build_folder(project, version)
        folder.mkdir(parents=True, exist_ok=True)
        swept = sweep_orphan_partials(project)  # what a mix killed by force left (001.37, point 11)
        if swept and log is not None:
            append_log(log, f"[orphan_partials] {swept} archivos parciales huérfanos borrados\n")
        require_mix_space(folder, edl)  # a full disk is told now, not after minutes (001.37, 4)
        wav = make_mix(project, edl, version, plan, issues, inventory, notices, log)
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
