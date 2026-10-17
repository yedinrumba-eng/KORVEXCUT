"""kcut doctor: verify the machine has everything the engine needs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from kcut import __version__
from kcut.config.load import load_config
from kcut.console import Out
from kcut.doctor.checks import CheckResult, run_all
from kcut.errors import ProjectError
from kcut.paths import CONFIG_NAME
from kcut.project import locate_project

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
    model, config_check = _model_for_project(args.project)
    results = run_all(model)
    if config_check is not None:
        results.append(config_check)
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


def _model_for_project(explicit: str | None) -> tuple[str, CheckResult | None]:
    """Whisper model of the project's `kcut.toml`, or `medium` outside a project.

    A `kcut.toml` that does not load falls back to `medium` and adds the optional
    `project_config` check with the error.
    """
    root = locate_project(explicit)
    if root is None:
        return DEFAULT_MODEL, None
    try:
        return load_config(Path(root) / CONFIG_NAME).transcribe.model, None
    except ProjectError as exc:
        fix = f"corrige {CONFIG_NAME} (los demás checks usan el modelo {DEFAULT_MODEL})"
        return DEFAULT_MODEL, CheckResult("project_config", False, False, exc.message_es, fix)


def _tag(result: CheckResult) -> str:
    if result.ok:
        return "OK"
    return "FALTA" if result.required else "AVISO"


def _text(result: CheckResult) -> str:
    text = f"{result.id}: {result.detail}"
    if not result.ok and result.fix_es:
        text += f" - {result.fix_es}"
    return text
