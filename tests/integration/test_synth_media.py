"""The synthetic camera material is reproducible: same input, same decoded audio."""

import hashlib
import subprocess
from pathlib import Path

import pytest

from kcut import proc
from tests.fixtures import synth_media
from tests.fixtures.synth_media import make_media

pytestmark = pytest.mark.ffmpeg


def _decoded_audio_sha256(path: Path) -> str:
    """Hash of the decoded PCM of the first audio stream (no container or encoder metadata)."""
    done = subprocess.run(
        [
            str(proc.tool_path("ffmpeg")),
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "s16le",
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return hashlib.sha256(done.stdout).hexdigest()


def test_seed_makes_the_audio_of_cam_b_deterministic(tmp_path: Path) -> None:
    make_media(tmp_path / "primera")
    make_media(tmp_path / "segunda")
    first = _decoded_audio_sha256(tmp_path / "primera" / "cam b.mov")
    second = _decoded_audio_sha256(tmp_path / "segunda" / "cam b.mov")
    assert first == second


def test_seed_is_fixed_in_the_noise_source_itself() -> None:
    source = Path(synth_media.__file__).read_text(encoding="utf-8")
    assert "anoisesrc=a=0.01:r=48000:d=12:seed=42" in source
    assert source.count("anoisesrc") == 1
