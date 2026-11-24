"""kcut qa: audit `salida/vN.mp4` (spec S1.9a).

The video is measured (frames, streams, loudness, black and frozen pictures), what Whisper hears in
it is compared with the words the cut keeps, and the report `qa/vN/report.json` and the contact
sheet `qa/vN/contact.jpg` are written. `--json` prints the report. A report whose verdict is `fail`
exits 1; `pass` and `incomplete` (some check was skipped) exit 0. Only `salida/vN.mp4` is accepted
(exit 2 for any other path, before anything runs).
"""

from __future__ import annotations

import argparse
import contextlib
from pathlib import PurePosixPath
from typing import Any

from kcut.console import Out, Progress
from kcut.ingest.cache_guard import assert_in_cache
from kcut.project import Project, open_project
from kcut.qa.report import Check, QaReport
from kcut.qa.run import STEPS, VIDEO_NAME, run_qa
from kcut.render.lock import OutputLock

NAME = "qa"
HELP_ES = "Audita salida/vN.mp4: frames, streams, sonoridad, negros, congelados y lo que se oye"
MAX_SHOWN_DIFFS = 5  # differences of the transcript that the human output lists
_TAGS = {"pass": "OK", "fail": "ERROR", "skipped": "AVISO"}


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument("video", metavar="VIDEO", help="salida/vN.mp4, relativo al proyecto")
    sub.add_argument(
        "--edl",
        metavar="EDL",
        default=None,
        help="ruta del EDL, relativa al proyecto (por defecto qa/vN/inputs/edl-vN.json si "
        "existe, si no edit/edl-vN.json)",
    )
    return sub


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    progress = Progress(f"qa {args.video}", STEPS, "pasos")
    with _build_lock(project, args.video):  # 001.51: not while a `kcut build` of it is running
        report = run_qa(
            project, args.video, args.edl, progress, out=out, log=getattr(args, "log", None)
        )
    progress.close()
    for item in report.warnings:
        out.warn(f"{item['code']}: {item['message_es']}")
    for check in report.checks:
        out.line(_TAGS[check.status], f"{check.id}: {_describe(check)}")
        if check.id == "transcript":
            _list_diffs(out, check)
    _verdict(out, report)
    out.result(report.to_json())
    return report.exit_code


def _build_lock(project: Project, video: str) -> contextlib.AbstractContextManager[object]:
    """The lock `build-vN` of the video, taken without waiting (`LockedError`, exit 6). `kcut
    build` calls `run_qa` with its own lock already taken, so the lock is taken here and not
    there. A name that is not `salida/vN.mp4` takes none: `run_qa` refuses it (exit 2)."""
    found = VIDEO_NAME.fullmatch(video)
    if found is None:
        return contextlib.nullcontext()
    name = f"build-v{found.group(1)}"
    assert_in_cache(project, project.layout.locks / f"{name}.lock")
    return OutputLock(project.layout.locks, name)


def _verdict(out: Out, report: QaReport) -> None:
    tag = {"pass": "OK", "fail": "ERROR", "incomplete": "AVISO"}[report.verdict]
    folder = PurePosixPath("qa") / PurePosixPath(report.video).stem  # qa/vN, as run_qa writes it
    sheet = report.contact_sheet
    where = "sin hoja de contacto" if sheet is None else f"hoja en {sheet}"
    out.line(
        tag,
        f"veredicto {report.verdict} - {report.duration_display}, {report.file_mb} MB - "
        f"reporte en {folder / 'report.json'}, {where}",
    )


def _value(number: object) -> str:
    """A measure for a line: the number, or `sin dato` if it could not be measured."""
    return "sin dato" if number is None else str(number)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _describe(check: Check) -> str:
    """A line in Spanish for a check: what was measured against what was asked."""
    data = check.data
    if check.status == "skipped":
        return f"omitido - {check.reason_es}"
    extra = f" - {check.reason_es}" if check.reason_es else ""
    if check.id == "frames":
        return f"{data['value']} frames de {data['expected']} esperados"
    if check.id in ("video_stream", "audio_stream"):
        return " ".join(str(part) for part in _dict(data["value"]).values())
    if check.id == "av_delta":
        return f"{_value(data['value_ms'])} ms de diferencia (máximo {data['max_ms']} ms)"
    if check.id == "loudness":
        return (
            f"{_value(data['I_LUFS'])} LUFS (objetivo {data['target']} +/- {data['tolerance']}), "
            f"pico {_value(data['TP_dBTP'])} dBTP (máximo {data['max_tp']}){extra}"
        )
    if check.id in ("black", "freeze"):
        found = _list(data["intervals"])
        odd = sum(1 for item in found if not item["expected"])
        return f"{len(found)} intervalos, {odd} no esperados"
    if check.id == "transcript":
        return (
            f"coincidencia {data['match']} (mínimo {data['min']}), idioma {data['language']}, "
            f"{len(_list(data['diffs']))} diferencias"
        )
    return check.status


def _list_diffs(out: Out, check: Check) -> None:
    """The first differences of the transcript (their texts are masked already, T2)."""
    diffs = _list(check.data.get("diffs"))
    for item in diffs[:MAX_SHOWN_DIFFS]:
        expected = " ".join(str(item["expected"]).split())  # 001.47: one line, always
        heard = " ".join(str(item["heard"]).split())
        where = f"{item['at_display']} {item['op']}"
        out.line("INFO", f"{where}: esperado '{expected}', oído '{heard}'")
    if len(diffs) > MAX_SHOWN_DIFFS:
        out.line("INFO", f"... y {len(diffs) - MAX_SHOWN_DIFFS} más (están en el reporte)")
