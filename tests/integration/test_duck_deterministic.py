"""The mix graph with ducking is deterministic (spec S1.8b row 24, 001.37 point 1).

`sidechaincompress` ends when one of its inputs reaches its end, and with the old graph (the music
and the voice straight in) the thread that got to the end first decided how much of the tail of
the other one was thrown away: 100 runs of ffmpeg 8.1.1 gave 5 different outputs and 61 of them
had lost up to 0.49 s of music. With `apad` on both inputs of the compressor nobody reaches an end
first, and `amix` (which closes with the voice) sets the length. Here the real graph runs 20 times
over the same fixed inputs (a voice in bursts, a music that is loud to the very last sample, no
effects) and the 20 outputs have to be the same to the byte, with the music alive in the last
sample.
"""

import hashlib
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from kcut import proc
from kcut.audio.mix_graph import build_graph
from kcut.audio.mixer import graph_args
from kcut.audio.music_model import DEFAULT_DUCK

pytestmark = [pytest.mark.ffmpeg, pytest.mark.slow]
SR = 48000
TOTAL = 345 * 1600  # 552 000 samples, 11.5 s: the example EDL
RUNS = 20
BURSTS = ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0))  # seconds with voice


def _inputs(folder: Path) -> list[Path]:
    """`voice.f32`, `music.f32` and `sfx.f32`, each `TOTAL` samples long, as `mixer` writes them."""
    t = np.arange(TOTAL) / SR
    rng = np.random.default_rng(3)
    voice = np.zeros(TOTAL, dtype=np.float32)
    for start, end in BURSTS:
        a, b = int(start * SR), int(end * SR)
        voice[a:b] = (0.3 * rng.standard_normal(b - a)).astype(np.float32)
    # the phase keeps every sample, the last one included, away from a zero crossing
    music = (0.2 * np.sin(2 * np.pi * 220.0 * t + 0.5)).astype(np.float32)
    sfx = np.zeros(TOTAL, dtype=np.float32)
    paths = []
    for name, track in (("voice", voice), ("music", music), ("sfx", sfx)):
        paths.append(folder / f"{name}.f32")
        track.tofile(paths[-1])
    return paths


def _run(sources: list[Path], dst: Path) -> NDArray[np.float32]:
    graph, _ = build_graph(True, True, DEFAULT_DUCK)
    dst.unlink(missing_ok=True)
    proc.run(graph_args(proc.tool_path("ffmpeg"), sources, graph, dst))
    return np.fromfile(dst, dtype="<f4")


def test_duck_deterministic_twenty_runs_give_the_same_bytes_and_keep_the_last_sample(
    tmp_path: Path,
) -> None:
    sources = _inputs(tmp_path)
    outputs = [_run(sources, tmp_path / "mix_pre.f32") for _ in range(RUNS)]
    digests = {hashlib.sha256(out.tobytes()).hexdigest() for out in outputs}
    assert len(digests) == 1, f"{len(digests)} different outputs in {RUNS} runs"
    assert {len(out) for out in outputs} == {TOTAL}
    last_alive = {int(np.flatnonzero(out)[-1]) for out in outputs}
    assert last_alive == {TOTAL - 1}, f"the music ends at {sorted(last_alive)}, not at {TOTAL - 1}"
