"""Command-line entry point: builds the parser, runs a subcommand, maps errors to exit codes."""

import argparse
import importlib
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn, cast

from kcut import __version__
from kcut.console import Out, safe_text, setup_streams
from kcut.errors import MAX_MESSAGE, InternalError, KcutError, ProjectError, UsageError
from kcut.logfile import CreatedLog, append_log, create_run_log, remove_if_empty, set_log_root
from kcut.pack.pii import mask_text
from kcut.paths import Layout, log_path
from kcut.project import check_layout_inside, locate_project
from kcut.scrub import scrub_media_metadata

COMMAND_MODULES: tuple[str, ...] = (
    "kcut.commands.doctor",
    "kcut.commands.new",
    "kcut.commands.ingest",
    "kcut.commands.transcribe",
    "kcut.commands.pack",
    "kcut.commands.view",
    "kcut.commands.frames",
    "kcut.commands.edl",
    "kcut.commands.render",
)

_EXIT_INTERRUPTED = 130
_MIN_HEAD = 120  # characters of an internal error's own text that stay, whatever the log path
_BACKUP_HEAD = 40  # characters of the start of a backup traceback: "Traceback (most recent call..."
_CREATED_LOGS: list[CreatedLog] = []  # logs this invocation created


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
    set_log_root(None)
    try:
        return _main(list(sys.argv[1:] if argv is None else argv))
    finally:
        _drop_empty_logs()
        set_log_root(None)


def _drop_empty_logs() -> None:
    """End of the invocation, however it ended: the log it created and left empty goes away."""
    created = list(_CREATED_LOGS)
    _CREATED_LOGS.clear()
    for item in created:
        remove_if_empty(item)


def _main(raw: list[str]) -> int:
    json_mode = "--json" in raw
    verbose = "-v" in raw or "--verbose" in raw
    args: argparse.Namespace | None = None
    try:
        args = _build_parser().parse_args(raw)
        json_mode, verbose = bool(args.json), bool(args.verbose)
        args.log = _run_log(args.project, str(args.command))  # one log per invocation
        run_command: Callable[[argparse.Namespace], int] = args.run_command
        return int(run_command(args))
    except SystemExit as exc:  # argparse --version / --help
        return _exit_code(exc)
    except InternalError as exc:
        return _internal(exc, exc.message_es, args, raw, json_mode, verbose)
    except KcutError as exc:
        _log_whole(args, exc)
        return _report(exc.exit_code, type(exc).__name__, exc.message_es, json_mode)
    except KeyboardInterrupt:
        return _report(
            _EXIT_INTERRUPTED, "KeyboardInterrupt", "Interrumpido por el usuario", json_mode
        )
    except Exception as exc:
        message = f"Error interno ({type(exc).__name__}): {exc}"
        return _internal(exc, message, args, raw, json_mode, verbose)


def _log_whole(args: argparse.Namespace | None, exc: KcutError) -> None:
    """What the console will not show goes to the log: the text `_report` cuts, and the message
    with the key of a file that kcut does not know (`log_detail`, spec 001.14 points 2 and 7)."""
    target = getattr(args, "log", None) if args is not None else None
    whole = exc.log_detail if exc.log_detail is not None else exc.message_es
    if target is not None and (exc.log_detail is not None or len(whole) > MAX_MESSAGE):
        append_log(target, f"[{type(exc).__name__}] {whole}\n")


def _cap(message: str, limit: int) -> str:
    """`message` cut to `limit` characters, the last one being `…` when something was left out."""
    return message if len(message) <= limit else message[: limit - 1] + "…"


def _backup(traceback_text: str) -> str:
    """The traceback with no log to hold it, in `MAX_MESSAGE` characters (spec 001.16, point 10):
    its first line and its last ones, where the error is, with `…` in the middle."""
    if len(traceback_text) <= MAX_MESSAGE:
        return traceback_text
    joint = "…\n"
    tail = MAX_MESSAGE - _BACKUP_HEAD - len(joint)
    return traceback_text[:_BACKUP_HEAD] + joint + traceback_text[-tail:]


def _run_log(explicit: str | None, command: str) -> Path | None:
    """Create this invocation's log (`.kcut/logs/<command>-<time>-<pid>.log`, exclusive) and
    return its path, or None without a usable project. Children and the traceback of an
    InternalError share it, and every append is checked against the real cache (spec 0.11). `main`
    removes it at the end if the run left it empty (001.7)."""
    root = locate_project(explicit)
    if root is None:
        return None
    layout = Layout(root)
    try:
        check_layout_inside(root, layout)
    except ProjectError:
        return None  # a `.kcut` that is a link or leaves the project is never written to
    log = log_path(layout.logs, command)
    created = create_run_log(log)
    if created is None:
        notice = f"[AVISO] no pude crear el log {log}; esta corrida no deja log"
        print(safe_text(notice), file=sys.stderr)
        return None
    _CREATED_LOGS.append(created)
    set_log_root(layout.cache)
    return log


def _internal(
    exc: BaseException,
    message: str,
    args: argparse.Namespace | None,
    raw: list[str],
    json_mode: bool,
    verbose: bool,
) -> int:
    """Unexpected failure: the full traceback is appended to the run log (or goes to stderr with
    -v when there is no project); the user only gets a short, scrubbed message."""
    text = scrub_media_metadata("".join(traceback.format_exception(exc)))  # whole: for the log
    suffix = ""
    target = getattr(args, "log", None) if args is not None else None
    if target is None and args is None:  # failed before parsing finished
        target = _run_log(_option_value(None, raw), "kcut")
    if target is not None:
        if append_log(target, f"[traceback]\n{text}"):
            suffix = f". Detalle técnico en {target}"  # only if it reached the log
    elif verbose or locate_project(_option_value(args, raw)) is not None:
        # no log could be made: a backup of 300 characters, not all of what the error quotes
        print(safe_text(_backup(mask_text(text, parts=False))), file=sys.stderr)
    else:
        suffix = ". Usa -v para ver el detalle"
    # The text is cleaned WHOLE and only then cut (001.17, point 1): cut first, a coordinate or a
    # number could be left in halves that no longer look like one. The error's own text gives way
    # to the suffix, so the path of the log is kept whole (001.16).
    cleaned = mask_text(scrub_media_metadata(message), parts=False).strip() or "Error interno"
    short = _cap(cleaned, max(_MIN_HEAD, MAX_MESSAGE - len(suffix))) + suffix
    return _report(InternalError.exit_code, InternalError.__name__, short, json_mode, cap=False)


def _option_value(args: argparse.Namespace | None, raw: list[str]) -> str | None:
    """`--project DIR` from the parsed args, or from the raw argv if parsing never finished."""
    if args is not None:
        value = getattr(args, "project", None)
        return None if value is None else str(value)
    for i, token in enumerate(raw):
        if token == "--project" and i + 1 < len(raw):
            return raw[i + 1]
        if token.startswith("--project="):
            return token.removeprefix("--project=")
    return None


def _exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(safe_text(str(code)), file=sys.stderr)
    return 1


def _report(exit_code: int, kind: str, message: str, json_mode: bool, cap: bool = True) -> int:
    message = _cap(message, MAX_MESSAGE) if cap else message
    if json_mode:
        Out(json_mode=True).result(
            {"ok": False, "error": {"exit_code": exit_code, "kind": kind, "message": message}}
        )
    else:
        print(safe_text(f"[ERROR] {message}"), file=sys.stderr)
    return exit_code
