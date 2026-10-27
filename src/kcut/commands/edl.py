"""kcut edl: `check` judges an `edit/edl-vN.json`, `sources` prints the block that goes in it.

`check` exits 1 if the EDL has errors (warnings never fail it) and always says whether Gate 1, the
strategy, is approved; `render` and `build` are the ones that refuse to run without it. It prints
the summary and the gate first and then at most `MAX_SHOWN` errors and as many warnings, so an EDL
with thousands of findings costs a page, not a log (001.24, point 5).
"""

from __future__ import annotations

import argparse
import json

from kcut.console import Out
from kcut.edl.check import EdlCheck, check_edl_file, clip_audio_frames
from kcut.edl.gate import GateStatus, strategy_approved
from kcut.errors import UsageError
from kcut.ingest.inventory import Clip, Inventory
from kcut.issues import MAX_SHOWN, Issue, exit_code, issue_json
from kcut.project import Project, load_inventory, open_project
from kcut.schema_util import describe_value
from kcut.timebase import fmt_tc, ms_to_f_round

NAME = "edl"
HELP_ES = "Revisa el EDL (check) o imprime su bloque sources (sources)"
_NOT_MEDIA = ("imagen", "doc", "desconocido")


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, help=HELP_ES, description=HELP_ES)
    actions = sub.add_subparsers(dest="edl_command", metavar="ACCION", required=True)
    check = actions.add_parser(
        "check",
        parents=[parent],
        help="valida un EDL contra el proyecto",
        description="Valida un EDL contra el proyecto: exit 1 si tiene errores.",
    )
    check.add_argument(
        "edl",
        nargs="?",
        default=None,
        metavar="EDL",
        help="ruta del EDL, relativa al proyecto (por defecto el edit/edl-vN.json de N más alto)",
    )
    sources = actions.add_parser(
        "sources",
        parents=[parent],
        help="imprime el bloque sources listo para pegar en el EDL",
        description="Imprime el bloque sources del EDL con el qhash de cada clip del inventario.",
    )
    sources.add_argument(
        "ids",
        nargs="*",
        metavar="ID",
        help="ids de clips (por defecto, todos los de audio o video)",
    )
    return sub


def run(args: argparse.Namespace) -> int:
    if args.edl_command == "check":
        return _check(args)
    return _sources(args)


def _check(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    log = getattr(args, "log", None)
    result = check_edl_file(project, load_inventory(project, log), args.edl)
    gate = strategy_approved(project)
    errors = [issue for issue in result.issues if issue.level == "error"]
    warnings = [issue for issue in result.issues if issue.level == "warning"]
    fps = project.config.output.fps
    shown = _duration(result, fps)
    summary = f"{result.rel}: {shown}, {len(errors)} errores, {len(warnings)} avisos"
    out.line("ERROR" if errors else "OK", summary)
    out.line("OK" if gate.approved else "AVISO", f"estrategia ({gate.file}): {gate.reason_es}")
    _list(out, "ERROR", errors)
    _list(out, "AVISO", warnings)
    out.result(
        {
            "schema": "kcut.edlcheck/1",
            "edl": result.rel,
            "ok": not errors,
            "frames": None if result.edl is None else result.edl.frames,
            "duration_display": None if result.edl is None else fmt_tc(result.edl.frames, fps),
            "errors": [issue_json(issue) for issue in errors[:MAX_SHOWN]],
            "warnings": [issue_json(issue) for issue in warnings[:MAX_SHOWN]],
            "errors_total": len(errors),
            "warnings_total": len(warnings),
            "truncated": len(errors) > MAX_SHOWN or len(warnings) > MAX_SHOWN,
            "gate": _gate_json(gate),
        }
    )
    return exit_code(result.issues)


def _list(out: Out, tag: str, issues: list[Issue]) -> None:
    """The first `MAX_SHOWN` findings, one line each, and how many more there are."""
    for issue in issues[:MAX_SHOWN]:
        out.line(tag, f"{issue.code} {issue.path}: {issue.message_es}")
    if len(issues) > MAX_SHOWN:
        out.line(tag, f"… y {len(issues) - MAX_SHOWN} más")


def _duration(result: EdlCheck, fps: int) -> str:
    if result.edl is None:
        return "no se pudo leer"
    return f"{describe_value(result.edl.frames)} frames ({fmt_tc(result.edl.frames, fps)})"


def _gate_json(gate: GateStatus) -> dict[str, object]:
    return {"approved": gate.approved, "file": gate.file}


def _sources(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    inventory = load_inventory(project, getattr(args, "log", None))
    clips = _chosen(inventory, list(args.ids))
    fps = project.config.output.fps
    rows = [_row(project, clip, fps) for clip in clips]
    block = {clip.id: {"qhash": clip.qhash} for clip in clips}
    text = json.dumps({"sources": block}, ensure_ascii=False)
    out.line("INFO", text[1:-1])  # `"sources": {...}`: the line to paste inside the EDL
    for clip, row in zip(clips, rows, strict=True):
        out.line("INFO", _describe(clip, row))
    out.result({"ok": True, "sources": block, "clips": rows})
    return 0


def _chosen(inventory: Inventory, ids: list[str]) -> list[Clip]:
    """The clips asked for (in the order given, once each), or all with video or audio."""
    if not ids:
        return [c for c in inventory.clips if c.video is not None or c.audio is not None]
    chosen: list[Clip] = []
    for clip_id in dict.fromkeys(ids):
        clip = inventory.by_id(clip_id)
        if clip is None:
            raise UsageError(f"no existe el clip {describe_value(clip_id)} en el inventario")
        if clip.clip_class in _NOT_MEDIA:
            raise UsageError(f"{clip.id} es {clip.clip_class}: no tiene audio ni video para el EDL")
        chosen.append(clip)
    return chosen


def _row(project: Project, clip: Clip, fps: int) -> dict[str, object]:
    video = clip.video
    return {
        "id": clip.id,
        "qhash": clip.qhash,
        "frames": clip.frames,
        "w": None if video is None else video.display_w,
        "h": None if video is None else video.display_h,
        "vs_f": None if video is None else ms_to_f_round(video.start_ms, fps),
        "audio_f": clip_audio_frames(project, clip, fps),
    }


def _describe(clip: Clip, row: dict[str, object]) -> str:
    size = "sin video" if row["w"] is None else f"{row['w']}x{row['h']}"
    voice = "sin voz" if row["audio_f"] is None else f"voz hasta f{row['audio_f']}"
    start = f" - video desde f{row['vs_f']}" if row["vs_f"] else ""
    return f"{clip.id} - {clip.frames} frames - {size} - {voice}{start}"
