"""Synthetic audio for the sync tests: speech-like bursts and the spec's tone world."""

import numpy as np
from numpy.typing import NDArray

SR = 16000
Audio = NDArray[np.float32]


def speechlike(seconds: float, seed: int) -> Audio:
    """Band-limited noise bursts with random loudness, like words and pauses.

    Smoothing matters: raw white noise decorrelates after one sample, which no real microphone
    does, and the 4-sample step of the refine search would miss odd offsets.
    """
    rng = np.random.default_rng(seed)
    total = int(seconds * SR)
    out = np.zeros(total, dtype=np.float32)
    pos = 0
    while pos < total:
        length = int(rng.uniform(0.05, 0.4) * SR)
        amp = float(rng.choice([0.0, 0.0, 0.05, 0.15, 0.3, 0.5]))
        span = min(length, total - pos)
        out[pos : pos + span] = (rng.standard_normal(span) * amp).astype(np.float32)
        pos += length
    smooth = np.convolve(out, np.ones(8, dtype=np.float32) / 8, mode="same")
    return np.clip(smooth * 3.0, -1.0, 1.0).astype(np.float32)


def world(shift_s: float, noise: float = 0.0) -> Audio:
    """The spec's synthetic real-time signal R(t + shift), 12 s, tones and beeps only."""
    t = np.arange(12 * SR) / SR + shift_s
    mod = lambda period: t % period  # noqa: E731 - same shape as the ffmpeg expression
    x = (
        0.4 * np.sin(2 * np.pi * 440 * t) * (mod(1.7) <= 0.35)
        + 0.3 * np.sin(2 * np.pi * 660 * t) * ((mod(2.3) >= 1.1) & (mod(2.3) <= 1.4))
        + 0.6
        * np.sin(2 * np.pi * 2000 * t)
        * (((t >= 3.0) & (t <= 3.1)) | ((t >= 6.0) & (t <= 6.1)))
    )
    if noise:
        x = x + noise * np.random.default_rng(0).uniform(-1, 1, len(t))
    return x.astype(np.float32)
