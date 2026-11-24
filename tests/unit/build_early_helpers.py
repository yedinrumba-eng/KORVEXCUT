"""A `kcut build` whose heavy steps are doubles (spec 001.52, rows 38, 39, 42 and 43).

What these tests look at is the order of the checks of `run_build` and what it does with what the
steps give back, so the project is a few files and the picture, the mix and the mux are doubles that
note they were called. `Early.reached` has the names of the heavy steps that ran, in order.
"""

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from kcut.console import Out, Progress
from kcut.issues import Issue
from kcut.pipeline import build as build_module
from kcut.pipeline.build import STEPS, BuildResult, run_build
from kcut.project import Project, open_project

__all__ = ["Early", "Reached", "early_build", "run"]


class Reached(Exception):
    """The picture step was called: every check before it passed."""


@dataclass
class Early:
    project: Project
    reached: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


def run(early: Early, *, force: bool = True) -> BuildResult:
    """`run_build` over the project, with no QA, as the command does."""
    return run_build(
        early.project,
        None,
        skip_qa=True,
        force=force,
        progress=Progress("build", STEPS, "pasos"),
        out=Out(json_mode=True),
    )


def early_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    frames: int = 250,
    fps: int = 25,
    layer: int = 0,
    stop_at_picture: bool = True,
) -> Early:
    """A project with an EDL, `edit/graphics.json` and `crudo/brief.txt`, and the doubles in
    `kcut.pipeline.build`. With `stop_at_picture` the picture raises `Reached`; without it the
    picture, the mix and the mux go on as doubles (the mux only calls `before_replace`)."""
    root = tmp_path / "proyecto"
    for name in ("edit", "crudo", "salida"):
        (root / name).mkdir(parents=True)
    (root / "kcut.toml").write_text("", encoding="utf-8")
    (root / "edit" / "edl-v1.json").write_text('{"edl": 1}', encoding="utf-8")
    (root / "edit" / "graphics.json").write_text('{"graphics": 1}', encoding="utf-8")
    (root / "crudo" / "brief.txt").write_text("brief", encoding="utf-8")
    early = Early(open_project(str(root)))
    edl = SimpleNamespace(frames=frames, fps=fps)

    def picture(*args: Any, **kwargs: Any) -> tuple[Path, int, None]:
        early.reached.append("make_video")
        if stop_at_picture:
            raise Reached
        return early.project.layout.build_dir(1) / "video.mp4", frames, None

    def mix(
        project: Project, _edl: Any, _version: int, _plan: Any, issues: list[Issue], *a: Any
    ) -> Path:
        early.reached.append("make_mix")
        issues.extend(early.issues)
        return early.project.layout.build_dir(1) / "mix.wav"

    def mux(*args: Any) -> None:
        early.reached.append("mux")
        args[-1]()  # `before_replace`: the second reading and the delete of the old report

    patches: dict[str, Any] = {
        "load_inventory": lambda *a: object(),
        "find_edl": lambda *a: ("edit/edl-v1.json", 1),
        "strategy_approved": lambda *a: SimpleNamespace(approved=True, reason_es=""),
        "check_edl_file": lambda *a: SimpleNamespace(issues=[], edl=edl),
        "_check_manifest": lambda *a: None,
        "resolve_graphics": lambda *a: object(),
        "audio_plan": lambda *a: (object(), []),
        "layer_bytes": lambda *a, **k: layer,
        "make_video": picture,
        "make_mix": mix,
        "_mux": mux,
    }
    for name, double in patches.items():
        monkeypatch.setattr(build_module, name, double)
    return early
