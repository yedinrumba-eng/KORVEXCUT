"""kcut graphics: `check` judges `edit/graphics.json` against the EDL (spec S1.6a).

`check` needs the EDL to be good first: with errors in the EDL it exits 1 with those errors (codes
E) and resolves nothing else. Without `edit/graphics.json` it judges the implicit document
(subtitles from the transcript, 001.15 point 40): that file missing is never an exit 3. What it
prints is what Claude reads, so the texts of the cues and of the subtitles come out masked
(001.15 T2) unless `privacy.mask_pii` is false, and then `pii_unmasked` says so.
"""

from __future__ import annotations

import argparse
import os
from typing import Any

from kcut.console import Out
from kcut.edl.check import EdlCheck, check_edl_file
from kcut.gfx.captions import shown_chunks
from kcut.gfx.resolve import GRAPHICS_REL, ResolvedGraphics, chunk_json, resolve
from kcut.gfx.resolve_cues import ResolvedCue
from kcut.ingest.inventory import Notice
from kcut.issues import Issue, exit_code, issue_json
from kcut.pack.pii import mask_text
from kcut.project import Project, load_inventory, open_project

NAME = "graphics"
HELP_ES = "Revisa los gráficos del video (check)"
MAX_SHOWN = 50  # findings of each kind that the human output lists


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, help=HELP_ES, description=HELP_ES)
    actions = sub.add_subparsers(dest="graphics_command", metavar="ACCION", required=True)
    check = actions.add_parser(
        "check",
        parents=[parent],
        help="valida edit/graphics.json contra el EDL",
        description="Valida edit/graphics.json contra el EDL: exit 1 si tiene errores, 5 si pide "
        "un recurso sin aprobar.",
    )
    check.add_argument(
        "--edl",
        metavar="EDL",
        default=None,
        help="ruta del EDL, relativa al proyecto (por defecto el edit/edl-vN.json de N más alto)",
    )
    return sub


def run(args: argparse.Namespace) -> int:
    return _check(args)


def _check(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    log = getattr(args, "log", None)
    inventory = load_inventory(project, log)
    checked = check_edl_file(project, inventory, args.edl)
    edl_errors = [i for i in checked.issues if i.level == "error"]
    if edl_errors or checked.edl is None:
        return _refused(out, project, checked, edl_errors)
    resolved = resolve(project, checked.edl, checked.version, inventory=inventory, log=log)
    errors = [i for i in resolved.issues if i.level == "error"]
    warnings = [i for i in resolved.issues if i.level == "warning"]
    chunks = shown_chunks(resolved.chunks, resolved.shown, resolved.captions_cfg)
    summary = f"{len(resolved.cues)} cues, {len(chunks)} subtítulos, {len(errors)} errores"
    out.line("ERROR" if errors else "OK", f"{checked.rel}: {summary}, {len(warnings)} avisos")
    _list(out, "ERROR", errors)
    _list(out, "AVISO", warnings)
    for notice in resolved.notices:
        out.line("AVISO", f"{notice.code}: {notice.detail}")
    out.result(
        {
            "schema": "kcut.gfxcheck/1",
            "ok": not errors,
            "edl": checked.rel,
            "graphics_json": resolved.graphics_json,
            "frames": resolved.frames,
            "cues": [_cue_json(c, resolved) for c in resolved.cues],
            "chunks": [chunk_json(c) for c in chunks],
            "errors": [issue_json(i) for i in errors],
            "warnings": [issue_json(i) for i in warnings]
            + [_notice_json(n) for n in resolved.notices],
        }
    )
    return exit_code(resolved.issues)


def _refused(out: Out, project: Project, checked: EdlCheck, errors: list[Issue]) -> int:
    """The EDL has errors: they are the answer, and no graphics are resolved."""
    present = os.path.lexists(project.layout.edit / "graphics.json")
    out.line("ERROR", f"{checked.rel}: el EDL tiene {len(errors)} errores; corre kcut edl check")
    _list(out, "ERROR", errors)
    out.result(
        {
            "schema": "kcut.gfxcheck/1",
            "ok": False,
            "edl": checked.rel,
            "graphics_json": GRAPHICS_REL if present else None,
            "frames": None if checked.edl is None else checked.edl.frames,
            "cues": [],
            "chunks": [],
            "errors": [issue_json(i) for i in errors],
            "warnings": [],
        }
    )
    return exit_code(errors)


def _list(out: Out, tag: str, issues: list[Issue]) -> None:
    """The first `MAX_SHOWN` findings, one line each, and how many more there are."""
    for issue in issues[:MAX_SHOWN]:
        where = f" {issue.path}" if issue.path else ""
        out.line(tag, f"{issue.code}{where}: {issue.message_es}")
    if len(issues) > MAX_SHOWN:
        out.line(tag, f"... y {len(issues) - MAX_SHOWN} más")


def _notice_json(notice: Notice) -> dict[str, str]:
    return {"code": notice.code, "path": "", "message": notice.detail}


def _cue_json(cue: ResolvedCue, resolved: ResolvedGraphics) -> dict[str, object]:
    """A cue for Claude: its `params` with the defaults applied and every text in them masked
    (a text in a cue can be a phone number the person said). A `path` is its relative path."""
    params = _masked(cue.params) if resolved.masked else cue.params
    return {
        "id": cue.id,
        "component": cue.component,
        "start_f": cue.start_f,
        "end_f": cue.end_f,
        "params": params,
    }


def _masked(value: object) -> Any:
    """A copy of `value` with `mask_text` applied to every string inside it, in lists and objects
    too (keys stay: they are the names of parameters)."""
    if isinstance(value, str):
        return mask_text(value, parts=False)
    if isinstance(value, list):
        return [_masked(item) for item in value]
    if isinstance(value, dict):
        return {key: _masked(item) for key, item in value.items()}
    return value
