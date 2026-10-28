"""Shared pieces of the `kcut mix` integration tests (spec S1.8b): a copy of the synthetic project
with the example EDL and the plans of audio, `ebur128` over a file, and a reader of `.f32`."""

import wave
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from kcut import proc
from kcut.audio.loudnorm import EburMeasure, ebur128_args, parse_ebur128
from tests.fixtures.synth_audio import write_audio_plans, write_music_plan, write_sfx_plan
from tests.fixtures.synth_edl import write_edl_v1

FRAMES, SPF = 345, 1600
SAMPLES = FRAMES * SPF  # 552 000
BUILD = ".kcut/build/v1"
__all__ = ["BUILD", "FRAMES", "SAMPLES", "SPF", "audio_project", "measure", "read_f32", "read_wav"]


def audio_project(root: Path, *, sfx: bool = True, music: bool = True) -> Path:
    """`root` (a copy of the synthetic project) with `edit/edl-v1.json` (the example, 345 frames at
    30 fps) and the plans of audio of the spec: both files, or only the ones asked for."""
    write_edl_v1(root)
    if sfx and music:
        write_audio_plans(root)
    elif sfx:
        write_sfx_plan(root)
    elif music:
        write_music_plan(root)
    return root


def measure(path: Path, raw: bool = False) -> EburMeasure:
    """`I`, `TP` and `LRA` of an audio file, with the `ebur128` of `kcut.audio.loudnorm`."""
    inputs = [*(["-f", "f32le", "-ar", "48000", "-ac", "1"] if raw else []), "-i", str(path)]
    result = proc.run(ebur128_args(proc.tool_path("ffmpeg"), inputs), capture_stderr=True)
    return parse_ebur128(result.stderr)


def read_f32(path: Path) -> NDArray[np.float32]:
    return np.frombuffer(path.read_bytes(), dtype="<f4").astype(np.float32)


def read_wav(path: Path) -> tuple[NDArray[np.float32], int, int, int]:
    """`(samples as float, channels, sample width in bytes, rate)` of a wav of 16 bits."""
    with wave.open(str(path), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
        shape = (handle.getnchannels(), handle.getsampwidth(), handle.getframerate())
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return samples, *shape
