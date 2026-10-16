"""Locate ffmpeg/ffprobe safely: absolute, resolved, never from the cwd, never a script."""

import os
import shutil
import sys
from pathlib import Path
from typing import Literal

from kcut.errors import MissingDependency

_ENV_OVERRIDE = {"ffmpeg": "KCUT_FFMPEG", "ffprobe": "KCUT_FFPROBE"}
_NO_CWD_ENV = "NoDefaultCurrentDirectoryInExePath"
_WINDOWS_SUFFIXES = (".exe", ".com")


def tool_path(name: Literal["ffmpeg", "ffprobe"]) -> Path:
    """Locate ffmpeg/ffprobe. Resolve first (follow symlinks), then check .exe/.com on that path."""
    env_name = _ENV_OVERRIDE[name]
    override = os.environ.get(env_name)
    if override:
        label, candidate = env_name, override
        if not Path(candidate).is_absolute():
            raise MissingDependency(f"{env_name} debe ser una ruta absoluta (vino {override!r})")
    else:
        label = name
        if sys.platform == "win32":
            os.environ[_NO_CWD_ENV] = "1"
        found = shutil.which(name)
        if found is None:
            raise MissingDependency(
                f"no encuentro {name} en el PATH; instala el build full de gyan.dev o define "
                f"{env_name}"
            )
        if not Path(found).is_absolute():
            raise MissingDependency(
                f"{name} se encontró con una ruta relativa ({found}); no se usa"
            )
        candidate = found
    try:
        resolved = Path(candidate).resolve(strict=True)
    except (OSError, RuntimeError):
        raise MissingDependency(f"{label} no existe: {candidate}") from None
    if not resolved.is_file():
        raise MissingDependency(f"{label} no es un archivo: {resolved}")
    if sys.platform == "win32" and resolved.suffix.lower() not in _WINDOWS_SUFFIXES:
        raise MissingDependency(
            f"{label}: en Windows solo se aceptan .exe y .com, no "
            f"{resolved.suffix or 'sin extension'} ({resolved})"
        )
    return resolved
