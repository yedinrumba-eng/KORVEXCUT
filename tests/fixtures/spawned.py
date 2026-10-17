"""A spy on `subprocess.Popen`: which children did kcut start, and are they still alive?"""

import subprocess

import pytest


def spy_on_popen(monkeypatch: pytest.MonkeyPatch) -> list[subprocess.Popen[bytes]]:
    """Record every child started through `subprocess.Popen` (the real call still happens)."""
    spawned: list[subprocess.Popen[bytes]] = []
    real = subprocess.Popen

    def spy(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        child: subprocess.Popen[bytes] = real(*args, **kwargs)  # type: ignore[call-overload]
        spawned.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", spy)
    return spawned
