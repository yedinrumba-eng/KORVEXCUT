"""kcut ingest: inventory of `crudo/`, work files (wav16, proxies) and camera sync."""

from __future__ import annotations

import argparse
import time
from typing import Any

from kcut.console import Out, Progress
from kcut.ingest.inventory import Inventory, Notice, SyncRejected
from kcut.ingest.run import run_ingest
from kcut.ingest.sync_reasons import SYNC_METHODS, rejection_text
from kcut.project import open_project
from kcut.timebase import fmt_s

NAME = "ingest"
HELP_ES = "Inventaría crudo/, extrae audio, crea proxies y sincroniza cámaras"
_NO_SYNC = "sin sincronía"  # also the whole text of a rejection whose reason kcut does not write


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    sub = subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)
    sub.add_argument("--no-proxy", action="store_true", help="no genera proxies de video")
    sub.add_argument("--resync", action="store_true", help="recalcula la sincronía de cámaras")
    return sub


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    project = open_project(args.project)
    started = time.monotonic()
    progress = Progress("ingest", 0, "pasos")
    notices: list[Notice] = []
    try:
        inventory = run_ingest(
            project,
            make_proxies=not args.no_proxy,
            resync=args.resync,
            progress=progress,
            log=getattr(args, "log", None),
            notices=notices,
        )
    finally:
        progress.close()
    elapsed = round(time.monotonic() - started, 1)
    _human_lines(out, inventory, project.config.output.fps)
    out.result(_document(inventory, notices, elapsed))
    return 0


def _document(inventory: Inventory, notices: list[Notice], elapsed_s: float) -> dict[str, Any]:
    by_class: dict[str, int] = {}
    for clip in inventory.clips:
        by_class[clip.clip_class] = by_class.get(clip.clip_class, 0) + 1
    sync = inventory.sync
    return {
        "ok": True,
        "inventory": ".kcut/inventory.json",
        "clips": len(inventory.clips),
        "by_class": by_class,
        "sync": {
            "master": sync.master,
            "members": [
                {
                    "id": m.id,
                    "offset_ms": m.offset_ms,
                    "score": m.score,
                    "ratio": m.ratio,
                    "drift_ms": m.drift_ms,
                    "method": m.method if m.method in SYNC_METHODS else None,
                }
                for m in sync.members
            ],
            "rejected": [{"id": r.id, "reason": _reason_text(r)} for r in sync.rejected],
        },
        "warnings": [
            *_clip_warning_docs(inventory),
            *(_notice_json(n) for n in notices),
        ],
        "elapsed_s": elapsed_s,
    }


def _reason_text(rejected: SyncRejected) -> str:
    """The fixed text of a rejection, as in the human line. The `reason` stored in the inventory
    is free text that Claude would read as data; it is never copied out (001.8, point 2)."""
    text = rejection_text(rejected.reason, rejected.lag_a_ms, rejected.lag_b_ms)
    return text if text is not None else _NO_SYNC


def _clip_warning_docs(inventory: Inventory) -> list[dict[str, Any]]:
    """One `{id, code}` per clip warning; `sync_ambiguous` also carries its `message_es`."""
    docs: list[dict[str, Any]] = []
    for clip in inventory.clips:
        for code in clip.warnings:
            doc: dict[str, Any] = {"id": clip.id, "code": code}
            if code == "sync_ambiguous":
                rejected = next((r for r in inventory.sync.rejected if r.id == clip.id), None)
                if rejected is not None:
                    doc["message_es"] = rejection_text(
                        rejected.reason, rejected.lag_a_ms, rejected.lag_b_ms
                    )
            docs.append(doc)
    return docs


def _notice_json(notice: Notice) -> dict[str, Any]:
    """A run-level warning: no clip id; `file` names the file when the warning is about one."""
    doc: dict[str, Any] = {"id": None, "code": notice.code, "detail": notice.detail}
    if notice.file is not None:
        doc["file"] = notice.file
    doc["message_es"] = notice.detail
    return doc


def _human_lines(out: Out, inventory: Inventory, fps: int) -> None:
    for clip in inventory.clips:
        length = f" - {fmt_s(clip.frames or 0, fps)} s" if clip.frames is not None else ""
        out.line("OK", f"{clip.id}: {clip.clip_class} - {clip.file}{length}")
        for code in clip.warnings:
            out.line("AVISO", f"{clip.id}: {code}")
    sync = inventory.sync
    if sync.master is not None:
        out.line("INFO", f"sincronía: maestro {sync.master}")
    for member in sync.members:
        known = f" ({member.method})" if member.method in SYNC_METHODS else ""  # never raw text
        out.line("OK", f"{member.id}: offset {member.offset_ms:+d} ms{known}")
    for rejected in sync.rejected:
        # a fixed text per motive: the stored `reason` itself is never printed (001.7, point 12)
        text = rejection_text(rejected.reason, rejected.lag_a_ms, rejected.lag_b_ms)
        out.line("AVISO", f"{rejected.id}: {_NO_SYNC}" + (f" - {text}" if text else ""))
