"""Command-line entry point: builds the parser, runs a subcommand, maps errors to exit codes."""

import argparse
import importlib
import sys
import traceback
from collections.abc import Callable
from typing import NoReturn, cast

from kcut import __version__
from kcut.console import Out, setup_streams
from kcut.errors import InternalError, KcutError, UsageError

COMMAND_MODULES: tuple[str, ...] = ("kcut.commands.doctor",)

_EXIT_INTERRUPTED = 130


class _Parser(argparse.ArgumentParser):
    """ArgumentParser that raises UsageError (exit 2) instead of printing and exiting."""

    def error(self, message: str) -> NoReturn:
        raise UsageError(f"Argumentos inválidos: {message}")


def _common_parent() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--json", action="store_true", help="salida como un solo documento JSON")
    parent.add_argument("--project", metavar="DIR", default=None, help="carpeta del proyecto")
    parent.add_argument("-v", "--verbose", action="store_true", help="más detalle")
    return parent


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="kcut", description="Motor determinista de edición de video.")
    parser.add_argument("--version", action="version", version=f"kcut {__version__}")
    subparsers = cast(
        "argparse._SubParsersAction[argparse.ArgumentParser]",
        parser.add_subparsers(dest="command", metavar="COMANDO", required=True),
    )
    parent = _common_parent()
    for module_name in COMMAND_MODULES:
        module = importlib.import_module(module_name)
        sub = module.add_parser(subparsers, parent)
        sub.set_defaults(run_command=module.run)
    return parser


def main(argv: list[str] | None = None) -> int:
    setup_streams()
    raw = list(sys.argv[1:] if argv is None else argv)
    json_mode = "--json" in raw
    verbose = "-v" in raw or "--verbose" in raw
    try:
        args = _build_parser().parse_args(raw)
        json_mode, verbose = bool(args.json), bool(args.verbose)
        run_command: Callable[[argparse.Namespace], int] = args.run_command
        return int(run_command(args))
    except SystemExit as exc:  # argparse --version / --help
        return _exit_code(exc)
    except KcutError as exc:
        return _report(exc.exit_code, type(exc).__name__, exc.message_es, json_mode)
    except KeyboardInterrupt:
        return _report(
            _EXIT_INTERRUPTED, "KeyboardInterrupt", "Interrumpido por el usuario", json_mode
        )
    except Exception as exc:
        if verbose:
            traceback.print_exc()
        message = f"Error interno ({type(exc).__name__}): {exc}"
        return _report(InternalError.exit_code, InternalError.__name__, message, json_mode)


def _exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def _report(exit_code: int, kind: str, message: str, json_mode: bool) -> int:
    if json_mode:
        Out(json_mode=True).result(
            {"ok": False, "error": {"exit_code": exit_code, "kind": kind, "message": message}}
        )
    else:
        print(f"[ERROR] {message}", file=sys.stderr)
    return exit_code
