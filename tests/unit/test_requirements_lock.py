"""requirements.lock: the exact runtime closure the reference venv runs (spec 0.1, 0.12)."""

import importlib.metadata as md
import re
import tomllib
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "requirements.lock"
FLOORS = {
    "numpy": (1, 26),
    "scipy": (1, 11),
    "opencv-python": (4, 9),
    "pillow": (12, 3),
    "faster-whisper": (1, 0),
    "playwright": (1, 55, 1),
}
DEV_TOOLS = {
    "pytest",
    "pytest-cov",
    "pytest-timeout",
    "ruff",
    "mypy",
    "coverage",
    "iniconfig",
    "pluggy",
    "mypy-extensions",
}


def _canon(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            name, _, version = line.partition("==")
            pins[_canon(name)] = version
    return pins


def _numeric(version: str) -> tuple[int, ...]:
    match = re.match(r"\d+(?:\.\d+)*", version)
    assert match is not None, version
    return tuple(int(part) for part in match.group().split("."))


def _runtime_closure() -> set[str]:
    seen: set[str] = set()
    pending = list(FLOORS)
    while pending:
        name = _canon(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        for raw in md.requires(name) or []:
            req = Requirement(raw)
            if req.marker is not None and ("extra" in str(req.marker) or not req.marker.evaluate()):
                continue
            pending.append(req.name)
    return seen


def test_header_and_line_format() -> None:
    lines = LOCK.read_text(encoding="utf-8").splitlines()
    assert re.fullmatch(
        r"# kcut runtime lock - \d{2}/\d{2}/\d{4} - Python \d+\.\d+\.\d+ - \S+", lines[0]
    )
    for line in lines[1:]:
        assert re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\-]*==\d[^\s=]*", line), line


def test_alphabetical_order_ignoring_case() -> None:
    names = [ln.partition("==")[0].lower() for ln in LOCK.read_text("utf-8").splitlines()[1:]]
    assert names == sorted(names)


def test_roots_are_pinned_above_their_floors() -> None:
    pins = _pins()
    for name, floor in FLOORS.items():
        assert name in pins, name
        assert _numeric(pins[name]) >= floor, (name, pins[name], floor)


def test_pyproject_declares_the_same_floors() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    declared = {}
    for dep in project["dependencies"]:
        name, _, floor = dep.partition(">=")
        declared[_canon(name)] = _numeric(floor)
    assert declared == FLOORS


def test_playwright_matches_the_chromium_already_on_disk() -> None:
    assert _pins()["playwright"] == "1.63.0"


def test_no_dev_tools_and_no_kcut() -> None:
    pins = _pins()
    assert not DEV_TOOLS & set(pins)
    assert "kcut" not in pins


def test_lock_is_exactly_the_runtime_closure() -> None:
    assert set(_pins()) == _runtime_closure()


def test_every_pin_is_the_installed_version() -> None:
    for name, version in _pins().items():
        assert md.version(name) == version, name
