"""Directory links for tests: a symlink, or a Windows junction when symlinks need a privilege."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def make_dir_link(link: Path, target: Path) -> None:
    """Make `link` point at the folder `target`; skip the test (with the reason) if impossible."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except OSError as exc:
        reason = str(exc)
    if sys.platform == "win32":
        made = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            check=False,
        )
        if made.returncode == 0:
            return
        reason += f"; mklink /J fallo con codigo {made.returncode}"
    pytest.skip(f"no se pudo crear un enlace de directorio: {reason}")


def remove_dir_link(link: Path) -> None:
    """Remove a link made by `make_dir_link` without touching its target."""
    if link.is_symlink() or os.path.isjunction(link):
        os.rmdir(link)


def make_hard_link(link: Path, target: Path) -> None:
    """Make `link` a second name of the file `target`; skip the test if the system refuses."""
    try:
        os.link(target, link)
    except OSError as exc:
        pytest.skip(f"no se pudo crear un hard link: {exc}")
