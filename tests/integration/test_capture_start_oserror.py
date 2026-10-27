"""A driver of Playwright that is missing, or that an antivirus blocks, is a MissingDependency (exit
7), not an internal error (exit 10) (spec S1.6b row 32, 001.32 point 1). The failure is a real one:
`compute_driver_executable` points at an exe that does not exist, so `sync_playwright().start()`
raises the `FileNotFoundError` of the operating system, which is an `OSError` and not an `Error` of
Playwright. Nothing is invented: no test raises the exception by hand.
"""

import json
from pathlib import Path
from typing import Any

import playwright._impl._transport as playwright_transport
import pytest

from kcut.errors import MissingDependency
from kcut.gfx.capture import capture_stills
from tests.integration.capture_helpers import page_with
from tests.integration.render_small_cases import small, small_base
from tests.integration.view_frames_helpers import Run, project_args

__all__ = ["small", "small_base"]
HINT = "; corre kcut doctor para ver qué falta"


def _driver_that_is_not_there(monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    """Make Playwright start a driver that does not exist: the way it fails when the driver is
    missing or when an antivirus removed it."""
    missing = folder / "driver que no existe" / "node.exe"
    monkeypatch.setattr(
        playwright_transport,
        "compute_driver_executable",
        lambda: (str(missing), str(missing.with_name("cli.js"))),
    )


def _write_graphics(root: Path) -> None:
    document: dict[str, Any] = {
        "schema": "kcut.graphics/1",
        "captions": {"enabled": False},
        "cues": [{"id": "x", "component": "label", "start": 5, "end": 20, "params": {"text": "x"}}],
    }
    (root / "edit" / "graphics.json").write_text(json.dumps(document), encoding="utf-8")


def test_capture_playwright_start_oserror_the_module_gives_missing_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _driver_that_is_not_there(monkeypatch, tmp_path)
    with pytest.raises(MissingDependency) as info:
        capture_stills(page_with(""), tmp_path / "work", [0], 30, (100, 100), tmp_path / "o", None)
    assert info.value.exit_code == 7
    assert info.value.message_es.startswith("Chromium no arrancó (")
    assert info.value.message_es.endswith(f"){HINT}")
    assert not (tmp_path / "o").exists() or list((tmp_path / "o").iterdir()) == []


@pytest.mark.ffmpeg
@pytest.mark.slow
@pytest.mark.parametrize("command", ["capture", "render"])
def test_capture_playwright_start_oserror_is_exit_7_and_not_10_in_the_commands(
    small: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    _write_graphics(small)
    _driver_that_is_not_there(monkeypatch, small.parent)
    args = ("graphics", "capture") if command == "capture" else ("render",)
    code, doc, _ = kcut_json(*args, *project_args(small))
    assert code == 7 and doc["error"]["kind"] == "MissingDependency", doc
    message = doc["error"]["message"]
    assert message.startswith("Chromium no arrancó (") and message.endswith(f"){HINT}"), message


def test_capture_playwright_start_oserror_doctor_reports_chromium_as_missing(
    tmp_path: Path, kcut_json: Run, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The check of `kcut doctor` starts Playwright too: with the same failure it reports
    Chromium as missing (`ok` false, a fix to read) and the command ends with 1, never with 10."""
    _driver_that_is_not_there(monkeypatch, tmp_path)
    code, doc, _ = kcut_json("doctor", "--project", str(tmp_path))
    assert code == 1 and doc["ok"] is False, doc
    chromium = [check for check in doc["checks"] if check["id"] == "chromium"]
    assert len(chromium) == 1 and chromium[0]["ok"] is False and chromium[0]["required"] is True
    assert chromium[0]["fix_es"]
