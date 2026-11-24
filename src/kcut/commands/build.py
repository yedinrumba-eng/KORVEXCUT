"""kcut build: the finished video of the cut, in `salida/vN.mp4` (spec S1.9b).

Picture with the graphics, the mix of voice, effects and music, the mux of the two, the snapshot of
the inputs in `qa/vN/inputs/` and, unless `--skip-qa`, `kcut qa` over the result. It refuses to
replace a `salida/vN.mp4` that is there without `--force` (exit 3), and it needs the strategy
approved (exit 5). `--json` prints the result, with the report of the QA inside. A QA whose verdict
is `fail` exits 1, with the video made; `pass` and `incomplete` exit 0. The steps and their order
are in `kcut/pipeline/build.py`.
"""

from __future__ import annotations

import argparse
import time

from kcut.console import Out, Progress
from kcut.pipeline.build import STEPS, BuildResult, run_build
from kcut.project import open_project

NAME = "build"
HELP_ES = "Construye el video final (salida/vN.mp4): imagen, gráficos, audio, snapshot y QA"
_TAGS = {"pass": "OK", "fail": "ERROR", "incomplete": "AVISO"}


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
    sub.add_argument("--skip-qa", action="store_true", help="no corre kcut qa al terminar")
    sub.add_argument("--force", action="store_true", help="reemplaza salida/vN.mp4 si ya existe")
    return sub


def run(args: argparse.Namespace) -> int:
    started = time.monotonic()
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    progress = Progress("build", STEPS, "pasos")
    result = run_build(
        project,
        args.edl,
        skip_qa=args.skip_qa,
        force=args.force,
        progress=progress,
        out=out,
        log=getattr(args, "log", None),
    )
    progress.close()
    for item in result.warnings:
        out.warn(item)
    elapsed = round(time.monotonic() - started, 1)
    out.line("OK", f"{result.video}: {result.frames} frames en {elapsed} s")
    report = result.report
    if report is None:
        out.line("AVISO", "sin QA (--skip-qa): el video no se auditó")
    else:
        for warning in report.warnings:
            out.warn(f"{warning['code']}: {warning['message_es']}")
        out.line(
            _TAGS[report.verdict],
            f"veredicto {report.verdict} - reporte en qa/v{result.version}/report.json",
        )
    out.result(_document(result, elapsed))
    return 0 if report is None else report.exit_code


def _document(result: BuildResult, elapsed: float) -> dict[str, object]:
    """What `--json` prints."""
    report = result.report
    return {
        "ok": report is None or report.verdict != "fail",
        "video": result.video,
        "frames": result.frames,
        "inputs": result.inputs,
        "verdict": None if report is None else report.verdict,
        "report": None if report is None else report.to_json(),
        "timings_s": result.timings_s,
        "elapsed_s": elapsed,
        "warnings": list(result.warnings),
    }
