"""The ear of `kcut qa` with the real model (spec S1.9a, row 7; 001.15).

The video is 6 s of black with flite's `slt` saying "hello world this is a test" after a second,
as an AAC track of 48 kHz in stereo, like the one `kcut build` joins. `hear` takes its audio to
`.kcut/qa_ear/v1.wav`, Whisper `medium` (the one on the machine: nothing is downloaded) writes it
down in English, and the second time nothing is transcribed again. Skipped (cleanly) when ffmpeg,
the flite filter or the local model are missing.
"""

import subprocess
from pathlib import Path

import pytest

from kcut import proc
from kcut.project import open_project
from kcut.qa import ear
from kcut.qa.ear import hear
from kcut.text.normalize import norm_token
from tests.conftest import run_kcut
from tests.unit.qa_fakes import NoModel

pytestmark = [pytest.mark.ffmpeg, pytest.mark.flite, pytest.mark.whisper, pytest.mark.slow]


def _video(dst: Path) -> None:
    args = [
        str(proc.tool_path("ffmpeg")),
        *("-hide_banner", "-nostdin", "-loglevel", "error", "-y"),
        *("-f", "lavfi", "-i", "color=c=black:s=216x384:r=30:d=6"),
        *("-f", "lavfi", "-i", "flite=text='hello world this is a test':voice=slt"),
        *("-af", "adelay=1000,apad", "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p"),
        *("-c:a", "aac", "-ar", "48000", "-ac", "2", str(dst)),
    ]
    subprocess.run(args, check=True, capture_output=True)


def test_qa_ear_real_hears_hello_and_world_and_then_reads_its_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proyecto ñandú"
    assert run_kcut("new", str(root)).returncode == 0
    _video(root / "salida" / "v1.mp4")
    project = open_project(str(root))
    first = hear(project, root / "salida" / "v1.mp4", "en", log=None)
    assert first is not None and first.language == "en"
    texts = {norm_token(w.text) for w in first.words}
    assert {"hello", "world"} <= texts, first.words
    assert all(0 <= w.s_ms < w.e_ms <= 6100 for w in first.words)
    assert (root / ".kcut" / "qa_ear" / "v1.wav").is_file()
    monkeypatch.setattr(ear, "Engine", NoModel)  # a second time the model is not even loaded
    second = hear(project, root / "salida" / "v1.mp4", "en", log=None)
    assert second is not None and second.words == first.words
    assert len(list((root / ".kcut" / "qa_ear").glob("*.json"))) == 1
