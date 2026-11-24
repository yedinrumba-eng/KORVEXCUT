"""A video with 300 s of audio and an EDL of 11.5 s: the wav that reaches the ear lasts at most
13.5 s (spec S1.9a row 27; 001.41, point 7). Real ffmpeg; the engine of Whisper is a double that
measures the wav it is given.
"""

from pathlib import Path
from typing import Any

import pytest

from kcut import proc
from kcut.qa import run as qa_run
from kcut.qa.ear import hear
from kcut.transcribe.cache import wav16_length_ms
from tests.unit.gfx_resolve_fakes import make_project
from tests.unit.qa_fakes import FakeEar, install_ear

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]


def _long_audio_video(path: Path) -> None:
    """11.5 s of picture and 300 s of audio in one mp4."""
    args = [
        str(proc.tool_path("ffmpeg")), "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=11.5",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=300:sample_rate=48000",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-b:a", "32k", str(path),
    ]  # fmt: skip
    proc.run(args, timeout_s=120)


def test_qa_ear_limit_300_s_of_audio_and_an_edl_of_11_s_give_a_wav_of_at_most_13_5_s(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path)
    video = project.root / "salida" / "v1.mp4"
    video.parent.mkdir()
    _long_audio_video(video)
    lengths: list[int] = []
    fake = install_ear(monkeypatch, [("Hola", 200, 600)])
    real = FakeEar.transcribe

    def transcribe(self: Any, wav16: Path, *args: Any) -> Any:
        lengths.append(wav16_length_ms(wav16))
        return real(self, wav16, *args)

    monkeypatch.setattr(fake, "transcribe", transcribe)
    hear(project, video, "es", log=None, limit_s=11.5 + qa_run.EAR_MARGIN_S)
    assert len(lengths) == 1 and 13_000 <= lengths[0] <= 13_500
