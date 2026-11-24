"""The finished video for the `kcut qa` integration tests (spec S1.9a, row 5).

`built` is the example EDL of the spec rendered with `kcut render --no-graphics`, mixed with
`kcut mix` (the plans of audio of the spec) and joined with `mux_args` into `salida/v1.mp4`, as
`kcut build` will do in S1.9b. It is made once for the module, from the render that the session
already has. `qa_run` runs `kcut qa` on it once in a fresh interpreter; nothing in it has a
transcript, so the check `transcript` is skipped there. `copy_of` gives a test its own project.
"""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.pipeline.mux import mux_args
from tests.conftest import run_kcut
from tests.fixtures.synth_audio import write_audio_plans

__all__ = [
    "VIDEO",
    "QaRun",
    "built",
    "check_of",
    "copy_of",
    "qa_run",
    "ramp_video",
    "sha256_of",
    "spy_on_ffmpeg",
]
VIDEO = "salida/v1.mp4"
QaRun = tuple[int, dict[str, Any], Path]


@pytest.fixture(scope="module")
def built(
    tmp_path_factory: pytest.TempPathFactory, rendered_example: tuple[Path, dict[str, Any]]
) -> Path:
    """A copy of the rendered example with its mix and `salida/v1.mp4`."""
    root = tmp_path_factory.mktemp("qabuilt") / "proyecto ñandú"
    shutil.copytree(rendered_example[0], root)
    write_audio_plans(root)
    done = run_kcut("mix", "--project", str(root), "--json")
    assert done.returncode == 0, done.stderr
    args = mux_args(
        proc.tool_path("ffmpeg"),
        root / ".kcut/build/v1/video.mp4",
        root / ".kcut/build/v1/mix.wav",
        root / VIDEO,
        audio_f32=False,
    )
    proc.run(args, timeout_s=300)
    assert (root / VIDEO).is_file()
    return root


@pytest.fixture(scope="module")
def qa_run(built: Path) -> QaRun:
    """`kcut qa salida/v1.mp4 --json` once, in a fresh interpreter: the exit code, the report
    that it printed and the project."""
    done = run_kcut("qa", VIDEO, "--project", str(built), "--json")
    return done.returncode, json.loads(done.stdout), built


def copy_of(built: Path, destination: Path) -> Path:
    """A project of its own with the finished video, for a test that changes something."""
    root = destination / "proyecto ñandú"
    shutil.copytree(built, root)
    return root


def check_of(doc: dict[str, Any], check_id: str) -> dict[str, Any]:
    """The one check `check_id` of a report."""
    found = [c for c in doc["checks"] if c["id"] == check_id]
    assert len(found) == 1, (check_id, [c["id"] for c in doc["checks"]])
    check: dict[str, Any] = found[0]
    return check


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def spy_on_ffmpeg(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Every command `proc.run` or `proc.popen` (the frame reader) is given from now on; the first
    thing a refusal must show is that this stays empty."""
    seen: list[list[str]] = []
    real_run, real_popen = proc.run, proc.popen

    def run(args: list[str], **kwargs: Any) -> Any:
        seen.append(args)
        return real_run(args, **kwargs)

    def popen(args: list[str], **kwargs: Any) -> Any:  # 001.41: the sheet reads with popen
        seen.append(args)
        return real_popen(args, **kwargs)

    monkeypatch.setattr(proc, "run", run)
    monkeypatch.setattr(proc, "popen", popen)
    return seen


def ramp_video(path: Path, frames: int = 345, size: tuple[int, int] = (216, 384)) -> None:
    """A video whose gray goes up one step in each frame: the frame `N` is `N / (frames - 1)` of
    the way from black to white, so a picture says which frame it is."""
    gray = f"geq=lum='16+N*219/{frames - 1}':cb=128:cr=128,format=yuv420p"
    args = [
        str(proc.tool_path("ffmpeg")), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=gray:s={size[0]}x{size[1]}:r=30:d={frames / 30:.4f}",
        "-vf", gray, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "ultrafast",
        "-qp", "0", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-color_range", "tv", str(path),
    ]  # fmt: skip
    proc.run(args, timeout_s=120)
