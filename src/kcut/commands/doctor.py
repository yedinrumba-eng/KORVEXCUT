"""kcut doctor: verify the machine has everything the engine needs."""

from __future__ import annotations

import argparse
from dataclasses import asdict

from kcut import __version__
from kcut.console import Out
from kcut.doctor.checks import CheckResult, run_all

NAME = "doctor"
HELP_ES = "Revisa que la máquina tenga todo lo que kcut necesita"
DEFAULT_MODEL = "medium"


def add_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    parent: argparse.ArgumentParser,
) -> argparse.ArgumentParser:
    return subparsers.add_parser(NAME, parents=[parent], help=HELP_ES, description=HELP_ES)


def run(args: argparse.Namespace) -> int:
    out = Out(json_mode=args.json)
    results = run_all(DEFAULT_MODEL)
    ok = all(r.ok for r in results if r.required)
    for result in results:
        out.line(_tag(result), _text(result))
    if not ok:
        out.line("INFO", "Faltan requisitos: arregla los [FALTA] y vuelve a correr kcut doctor")
    out.result(
        {
            "schema": "kcut.doctor/1",
            "version": __version__,
            "ok": ok,
            "checks": [asdict(r) for r in results],
        }
    )
    return 0 if ok else 1


def _tag(result: CheckResult) -> str:
    if result.ok:
        return "OK"
    return "FALTA" if result.required else "AVISO"


def _text(result: CheckResult) -> str:
    text = f"{result.id}: {result.detail}"
    if not result.ok and result.fix_es:
        text += f" - {result.fix_es}"
    return text
