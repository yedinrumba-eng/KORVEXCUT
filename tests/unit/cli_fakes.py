"""Helpers of the `cli.main` tests: a command that fails, the logs of a project, a safe python."""

import argparse
import re
import sys
from collections.abc import Callable
from pathlib import Path

LOG_NAME = re.compile(r"^doctor-\d{8}-\d{6}-\d+\.log$")


def raiser(exc: BaseException) -> Callable[[argparse.Namespace], int]:
    """A fake command that raises `exc`."""

    def run(_args: argparse.Namespace) -> int:
        raise exc

    return run


def logs_of(root: Path) -> list[Path]:
    """The `*.log` files in the project's `.kcut/logs/`."""
    return sorted((root / ".kcut" / "logs").glob("*.log")) if (root / ".kcut").exists() else []


def base_python() -> str:
    """The real interpreter, not the venv launcher (a launcher child can outlive a kill)."""
    return str(getattr(sys, "_base_executable", None) or sys.executable)
