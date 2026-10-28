"""The ducking (spec S1.8b row 4, 001.15): with a voice in bursts, the music goes down at least
10 dB (RMS) while there is voice, and comes back when there is none. It runs `ffmpeg` with the
`duck_only_graph` of `mix_graph` and the default `duck` of `music.json`: threshold 0.03, ratio 10,
attack 15 ms, release 350 ms. The music is a steady tone and the voice is noise at a speech level
(RMS 0.3) in three bursts of one second, so what changes in the music is the compressor.
"""

from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut import proc
from kcut.audio.mix_graph import duck_only_graph
from kcut.audio.music_model import DEFAULT_DUCK

pytestmark = pytest.mark.ffmpeg
SR = 48000
BURSTS = ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0))  # seconds with voice
SECONDS = 7.5
ATTACK_SKIP_S = 0.2  # the first 0.2 s of a burst: the compressor is still closing
RELEASE_S = 1.0  # after a burst the music has come back in this time (release is 350 ms)


def _signals() -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    t = np.arange(int(SECONDS * SR)) / SR
    music = (0.2 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    rng = np.random.default_rng(3)
    voice = np.zeros(len(t), dtype=np.float32)
    for start, end in BURSTS:
        a, b = int(start * SR), int(end * SR)
        voice[a:b] = (0.3 * rng.standard_normal(b - a)).astype(np.float32)
    return music, voice


def _rms_db(x: NDArray[np.float32]) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(x.astype(np.float64) ** 2)) + 1e-12))


@pytest.fixture
def ducked(tmp_path: Path) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """`(music in, music out)` after `ffmpeg` ran the ducking graph over the music and the voice."""
    music, voice = _signals()
    paths = {"music": tmp_path / "music.f32", "voice": tmp_path / "voice.f32"}
    music.tofile(paths["music"])
    voice.tofile(paths["voice"])
    out = tmp_path / "out.f32"
    raw = ["-f", "f32le", "-ar", "48000", "-ac", "1"]
    args = [
        str(proc.tool_path("ffmpeg")), "-hide_banner", "-nostdin", "-loglevel", "error",
        *raw, "-i", str(paths["music"]), *raw, "-i", str(paths["voice"]),
        "-filter_complex", duck_only_graph(DEFAULT_DUCK), "-map", "[md]", *raw, str(out),
    ]  # fmt: skip
    proc.run(args)
    return music, np.fromfile(out, dtype="<f4")


def test_ducking_the_music_goes_down_at_least_10_db_rms_while_there_is_voice(
    ducked: tuple[NDArray[np.float32], NDArray[np.float32]],
) -> None:
    music, out = ducked
    for start, end in BURSTS:
        a, b = int((start + ATTACK_SKIP_S) * SR), int(end * SR)
        drop = _rms_db(music[a:b]) - _rms_db(out[a:b])
        assert drop >= 10.0, f"{drop:.1f} dB in the burst of {start} s"


def test_ducking_the_music_comes_back_when_the_voice_stops(
    ducked: tuple[NDArray[np.float32], NDArray[np.float32]],
) -> None:
    music, out = ducked
    for (_, end), (start, _) in zip(BURSTS, (*BURSTS[1:], (SECONDS - 0.1, SECONDS)), strict=True):
        a, b = int((end + RELEASE_S) * SR), int((start - 0.05) * SR)
        if b <= a:  # the gap between the bursts is 1 s: there is no room after the release
            a, b = int((end + 0.6) * SR), int((start - 0.05) * SR)
        assert abs(_rms_db(music[a:b]) - _rms_db(out[a:b])) < 1.0, f"after the burst of {end} s"
    quiet = int(0.5 * SR)  # before the first burst the music is as it came
    assert abs(_rms_db(music[:quiet]) - _rms_db(out[:quiet])) < 0.5
